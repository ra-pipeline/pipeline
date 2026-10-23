"""Offline regression tests for MPI dispatch and worker logging."""

from __future__ import annotations

import ast
import importlib.util
import inspect
import pickle
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from pipeline.infrastructure import casa_tasks, daskhelpers, mpihelpers, mpirunner, parslhelpers


@pytest.mark.parametrize(
    'block_cores, workers, expected',
    [('8', '1', 8), ('32', '4', 8), ('1', '1', 1), ('1', '2', 1), ('invalid', '1', 4), ('8', '0', 4)],
)
def test_parsl_worker_cpu_budget(
    block_cores: str, workers: str, expected: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each worker can use its share of allocated CPUs without counting pool slots as ranks."""
    monkeypatch.setattr(daskhelpers, 'daskclient', None)
    monkeypatch.setenv('PARSL_CORES', block_cores)
    monkeypatch.setenv('PARSL_WORKER_COUNT', workers)
    assert mpirunner._infer_mpi_nproc() == expected


def test_single_cpu_worker_runs_serially(monkeypatch: pytest.MonkeyPatch) -> None:
    """A one-CPU allocation must not launch an invalid or oversubscribed MPI job."""
    monkeypatch.setenv('PARSL_CORES', '1')
    monkeypatch.setenv('PARSL_WORKER_COUNT', '1')
    monkeypatch.setattr(mpihelpers, 'MPIEnvironment', SimpleNamespace(is_mpi_enabled=False))
    launch = Mock()
    monkeypatch.setattr(mpirunner.subprocess, 'run', launch)

    def fn(parallel: bool = True) -> bool:
        return parallel

    assert mpirunner.call_with_mpi(fn) is False
    launch.assert_not_called()


@pytest.mark.parametrize('nproc, expected', [(None, 8), (6, 6)])
def test_multiple_cpu_worker_launches_with_its_budget(
    nproc: int | None, expected: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Multicore workers use their CPU budget unless a caller explicitly overrides it."""
    monkeypatch.setenv('PARSL_CORES', '32')
    monkeypatch.setenv('PARSL_WORKER_COUNT', '4')
    monkeypatch.setattr(mpirunner, 'find_executable', lambda *args: {'mpirun': '/synthetic/mpirun'})

    def launch(cmd: list[str], **kwargs) -> None:
        assert cmd[cmd.index('-n') + 1] == str(expected)
        script = ast.parse(cmd[-1])
        output_path = next(
            node.args[0].value
            for node in ast.walk(script)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == 'open'
            and len(node.args) > 1
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == 'wb'
        )
        Path(output_path).write_bytes(pickle.dumps({'success': True, 'result': 42}))

    monkeypatch.setattr(mpirunner.subprocess, 'run', launch)
    assert mpirunner.run_in_mpicasa(abs, -42, nproc=nproc) == 42


@pytest.mark.parametrize('worker_limit', [1, 16])
def test_mpi_rank_count_is_independent_of_parsl_blocks(worker_limit: int, monkeypatch: pytest.MonkeyPatch) -> None:
    """Parsl block sizing must not determine the size of a separate MPI launch."""
    monkeypatch.setattr(daskhelpers, 'daskclient', None)
    monkeypatch.setattr(parslhelpers, 'is_parsl_ready', lambda: True)
    executor = SimpleNamespace(max_workers_per_node=worker_limit)
    parsl = ModuleType('parsl')
    parsl.dfk = lambda: SimpleNamespace(executors={'tier0_executor': executor})
    monkeypatch.setitem(sys.modules, 'parsl', parsl)
    assert mpirunner._infer_mpi_nproc() == 4
    assert mpirunner._infer_mpi_nproc(fallback=8) == 8


@pytest.mark.parametrize('workers, expected', [(0, 4), (1, 2), (3, 4)])
def test_dask_rank_count_includes_client(workers: int, expected: int, monkeypatch: pytest.MonkeyPatch) -> None:
    """Active Dask workers retain one extra rank for the CASA MPI client."""
    client = Mock()
    client.scheduler_info.return_value = {'workers': dict.fromkeys(range(workers))}
    monkeypatch.setattr(daskhelpers, 'daskclient', client)
    assert mpirunner._infer_mpi_nproc() == expected


@pytest.mark.parametrize('nproc', [0, 1, -1, True, 2.5])
def test_invalid_mpi_rank_count_fails_before_launch(nproc: object, monkeypatch: pytest.MonkeyPatch) -> None:
    """Invalid MPI process counts fail before serializing work or launching a process."""
    monkeypatch.setattr(mpirunner, 'find_executable', lambda *args: {'mpirun': '/synthetic/mpirun'})
    launch = Mock()
    monkeypatch.setattr(mpirunner.subprocess, 'run', launch)
    with pytest.raises(ValueError, match='at least 2'):
        mpirunner.run_in_mpicasa(lambda: 42, nproc=nproc)
    launch.assert_not_called()


def test_explicit_mpi_rank_count_is_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Callers can choose MPI ranks independently of the configured Parsl pools."""
    monkeypatch.setattr(mpihelpers, 'MPIEnvironment', SimpleNamespace(is_mpi_enabled=False))
    launch = Mock(return_value=42)
    monkeypatch.setattr(mpirunner, '_run_in_mpicasa_call', launch)
    fn = Mock()
    assert mpirunner.call_with_mpi(fn, nproc=8) == 42
    launch.assert_called_once_with(fn, nproc=8)


@pytest.mark.parametrize('helper_name', ['call_with_mpi', 'run_in_mpicasa'])
def test_zero_argument_direct_call(helper_name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A direct call executes immediately even without forwarded arguments."""
    monkeypatch.setattr(mpirunner, 'find_executable', lambda *args: {})
    monkeypatch.setattr(mpihelpers, 'MPIEnvironment', SimpleNamespace(is_mpi_enabled=False))
    fn = Mock(return_value=42)
    assert getattr(mpirunner, helper_name)(fn) == 42
    fn.assert_called_once_with()


@pytest.mark.parametrize('helper_name', ['call_with_mpi', 'run_in_mpicasa'])
def test_explicit_decorator(helper_name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit decorator factories defer execution until the wrapper is called."""
    monkeypatch.setattr(mpirunner, 'find_executable', lambda *args: {})
    monkeypatch.setattr(mpihelpers, 'MPIEnvironment', SimpleNamespace(is_mpi_enabled=False))
    fn = Mock(return_value=42)
    wrapped = getattr(mpirunner, helper_name)(nproc=2)(fn)
    fn.assert_not_called()
    assert wrapped() == 42
    fn.assert_called_once_with()


def test_no_launcher_forces_serial(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing MPI launchers use serial execution without spawning a process."""
    monkeypatch.setattr(mpirunner, 'find_executable', lambda *args: {})
    monkeypatch.setattr(mpihelpers, 'MPIEnvironment', SimpleNamespace(is_mpi_enabled=False))
    launch = Mock(side_effect=AssertionError('Unexpected subprocess'))
    monkeypatch.setattr(mpirunner.subprocess, 'run', launch)

    def fn(value: int, parallel: bool = True) -> tuple[int, bool]:
        return value, parallel

    assert mpirunner.call_with_mpi(fn, 42) == (42, False)
    launch.assert_not_called()


def test_existing_mpi_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """An active MPI client retains parallel task execution."""
    monkeypatch.setattr(mpihelpers, 'MPIEnvironment', SimpleNamespace(is_mpi_enabled=True, is_mpi_client=True))

    def fn(parallel: bool = False) -> bool:
        return parallel

    assert mpirunner.call_with_mpi(fn) is True
    assert mpirunner.call_with_mpi(fn, parallel=False) is False


def test_tclean_command_name_and_signature() -> None:
    """The MPI wrapper preserves public CASA command names and parameters."""
    job = casa_tasks.tclean(vis='test_small.ms', imagename='test_image', parallel=False)
    assert job.fn_name == 'tclean'
    assert str(job).startswith('tclean(')
    assert job.kw == {'vis': 'test_small.ms', 'imagename': 'test_image', 'parallel': False}
    assert 'imagename' in inspect.signature(job.fn).parameters


@pytest.mark.parametrize('previous_log', ['same', 'different', 'symlink'])
def test_worker_preserves_existing_logs(previous_log: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirecting worker output preserves both shared logs and earlier logs."""
    shared = tmp_path / 'shared.log'
    shared.write_text('shared history\n')
    old = shared
    if previous_log == 'different':
        old = tmp_path / 'previous.log'
        old.write_text('previous history\n')
    elif previous_log == 'symlink':
        old = tmp_path / 'alias.log'
        old.symlink_to(shared)

    casalog = Mock()
    casalog.logfile.return_value = str(old)
    monkeypatch.setattr(casa_tasks.casatasks, 'casalog', casalog)
    # Load the real adapter with a synchronous Parsl stub so this check also
    # runs in environments where the optional dependency is absent.
    parsl_stub = ModuleType('parsl')
    parsl_stub.dfk = lambda: SimpleNamespace(executors={})
    parsl_stub.python_app = lambda fn, **kwargs: fn
    monkeypatch.setitem(sys.modules, 'parsl', parsl_stub)
    spec = importlib.util.spec_from_file_location('test_parsl_adapter', parslhelpers.__file__)
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    # Restore process state changed by the worker invocation.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('PARSL_WORKER', '0')
    from casaconfig import config

    monkeypatch.setattr(config, 'logfile', config.logfile)
    executable = SimpleNamespace(get_executable=lambda: lambda: 42)
    app = adapter.get_parsl_exec('test_worker')
    assert app(executable, str(tmp_path), casalog_file='shared.log') == (42, executable)
    assert shared.read_text() == 'shared history\n'
    assert old.exists()
    if previous_log == 'different':
        assert old.read_text() == 'previous history\n'
        casalog.setlogfile.assert_called_once_with(str(shared))
    else:
        casalog.setlogfile.assert_not_called()
