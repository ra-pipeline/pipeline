"""Offline regression tests for MPI dispatch and worker logging."""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from pipeline.infrastructure import casa_tasks, mpihelpers, mpirunner, parslhelpers


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
