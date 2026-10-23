"""Generic helpers for running callables in an MPI-enabled CASA subprocess."""

from __future__ import annotations

import functools
import importlib
import inspect
import os
import pickle
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Callable

import casaconfig.config

# NOTE: ``import casatasks`` previously lived here.  It is only needed by
# :func:`call_with_mpi` to format the launcher script; we defer it to that
# call site to avoid CASA C++ startup at ``pipeline`` import time.
from pipeline import infrastructure

LOG = infrastructure.logging.get_logger(__name__)


def find_executable(start_dir: str | None = None) -> dict[str, str | None]:
    """Search upward from start_dir for MPI-related executables.

    The function looks for 'bin/mpirun', 'bin/mpicasa' and 'bin/casa' in the
    current directory and each parent until the filesystem root is reached.

    Args:
        start_dir: Directory to start searching from. If None, use cwd.

    Returns:
        Mapping from executable name to absolute path or None if not found.
    """
    search_patterns = ['mpirun', 'mpicasa', 'casa']
    exe_dict: dict[str, str | None] = dict.fromkeys(search_patterns)
    current = Path(start_dir or Path.cwd()).resolve()

    for pattern in search_patterns:
        cur = current
        found: str | None = None
        while True:
            candidate = cur / 'bin' / pattern
            if candidate.is_file():
                found = str(candidate)
                break
            parent = cur.parent
            if cur == parent:
                break
            cur = parent
        exe_dict[pattern] = found

    return exe_dict


def _infer_mpi_nproc(fallback: int = 4) -> int:
    """Return a worker's CPU budget, active Dask workers plus a client, or a default.

    Inside a Parsl worker, divide explicitly allocated block CPUs by its worker
    count. One CPU selects serial execution; larger budgets include the MPI
    client rank. The orchestrator never infers its budget from Parsl pool sizes.
    """
    try:
        block_cores = int(os.environ.get('PARSL_CORES', '0'))
        worker_count = int(os.environ.get('PARSL_WORKER_COUNT', '0'))
        if block_cores > 0 and worker_count > 0:
            return max(1, block_cores // worker_count)
    except ValueError:
        pass

    from pipeline.infrastructure import daskhelpers

    client = daskhelpers.daskclient
    if client is not None:
        try:
            n = len(client.scheduler_info().get('workers', {}))
            return n + 1 if n > 0 else fallback
        except Exception:
            pass

    return fallback


def run_in_mpicasa(fn: Callable[..., Any] | None = None, /, *args: Any, nproc: int | None = None, **kwargs: Any):
    r"""Run a callable in an MPI-enabled CASA subprocess or decorate one to do so.

    Usages:
        1. Direct call:
           ``run_in_mpicasa(callable, *args, nproc=..., **kwargs)``

        2. Decorator (default settings):
           ``@run_in_mpicasa()``

        3. Decorator (configured):
           ``@run_in_mpicasa(nproc=8)``
    """

    def _decorate(target_fn: Callable[..., Any]):
        @functools.wraps(target_fn)
        def _wrapped(*wrapped_args: Any, **wrapped_kwargs: Any) -> Any:
            return _run_in_mpicasa_call(target_fn, *wrapped_args, nproc=nproc, **wrapped_kwargs)

        return _wrapped

    if fn is None:
        return _decorate

    # Direct execution path.
    return _run_in_mpicasa_call(fn, *args, nproc=nproc, **kwargs)


def call_with_mpi(
    fn: Callable[..., Any] | None = None,
    /,
    *args: Any,
    nproc: int | None = None,
    parallel: bool | dict = True,
    **kwargs: Any,
):
    r"""Call *fn* with MPI parallelism, delegating to a subprocess when needed.

    Dispatches across three execution paths:

    1. ``parallel is False`` — call *fn* in-process without the ``parallel``
       keyword (serial execution).
    2. Already inside an MPI client session — call *fn* in-process with
       ``parallel=True`` so CASA uses the existing worker pool.
    3. Otherwise — spawn an MPI subprocess via :func:`run_in_mpicasa`.

    Usages:
        1. Direct call:
           ``call_with_mpi(callable, *args, parallel=..., nproc=..., **kwargs)``

        2. Decorator (default settings):
           ``@call_with_mpi()``

        3. Decorator (configured):
           ``@call_with_mpi(nproc=8)`` or ``@call_with_mpi(parallel={'nproc': 8})``

    Args:
        fn: Callable to invoke (e.g. ``casatasks.tclean``).
        *args: Positional arguments forwarded to *fn*.
        nproc: Number of MPI processes for the subprocess path.  If ``None``,
            derived from an explicitly allocated Parsl worker CPU budget, then
            the active Dask client worker count, otherwise defaults to four.
            A one-CPU worker runs serially. MPI subprocess launches require at
            least two ranks, including the client.
        parallel: Controls which path is taken.  ``False`` forces in-process
            serial execution.  ``True`` or a dict triggers MPI dispatch.
            A dict may contain ``{'nproc': N}`` to override *nproc*.
        **kwargs: Keyword arguments forwarded to *fn*.

    Returns:
        The return value of *fn*, or a wrapped callable when used as a decorator.
    """

    def _decorate(target_fn: Callable[..., Any]):
        @functools.wraps(target_fn)
        def _wrapped(*wrapped_args: Any, **wrapped_kwargs: Any) -> Any:
            # The subprocess re-resolves fn by qualname (when cloudpickle isn't
            # used) and gets the decorated wrapper, so it calls _wrapped with
            # parallel=True in wrapped_kwargs. Pop it and prefer the caller's
            # value over the decorator's closure default; this avoids a
            # "multiple values for parallel" TypeError on the forward call.
            parallel_arg = wrapped_kwargs.pop('parallel', parallel)
            return _call_with_mpi_dispatch(
                target_fn, *wrapped_args, nproc=nproc, parallel=parallel_arg, **wrapped_kwargs
            )

        return _wrapped

    if fn is None:
        return _decorate

    # Direct execution path.
    return _call_with_mpi_dispatch(fn, *args, nproc=nproc, parallel=parallel, **kwargs)


def _accepts_parallel(fn: Callable[..., Any]) -> bool:
    """Return True if *fn*'s signature has a ``parallel`` parameter."""
    try:
        sig = inspect.signature(fn)
        return 'parallel' in sig.parameters
    except (TypeError, ValueError):
        return False


def _call_with_mpi_dispatch(
    fn: Callable[..., Any], /, *args: Any, nproc: int | None = None, parallel: bool | dict = True, **kwargs: Any
) -> Any:
    """Dispatch *fn* to in-process serial, in-process MPI, or MPI subprocess."""
    if parallel is False:
        return fn(*args, **kwargs)

    from pipeline.infrastructure.mpihelpers import MPIEnvironment

    if MPIEnvironment.is_mpi_enabled and MPIEnvironment.is_mpi_client:
        # In-process MPI: reuse the existing worker pool. nproc / parallel-dict
        # overrides are intentionally ignored here because the pool size is
        # fixed by the surrounding mpicasa/mpirun launch.
        extra = {'parallel': True} if _accepts_parallel(fn) else {}
        return fn(*args, **extra, **kwargs)

    if isinstance(parallel, dict) and 'nproc' in parallel and nproc is None:
        nproc = int(parallel['nproc'])
    extra = {'parallel': True} if _accepts_parallel(fn) else {}
    return run_in_mpicasa(fn, *args, nproc=nproc, **extra, **kwargs)


def _run_in_mpicasa_call(fn: Callable[..., Any], /, *args: Any, nproc: int | None = None, **kwargs: Any) -> Any:
    r"""Run *fn(\*args, \*\*kwargs)* inside a fresh MPI-enabled CASA subprocess."""
    if nproc is None:
        nproc = _infer_mpi_nproc()
        if nproc == 1:
            if _accepts_parallel(fn):
                kwargs['parallel'] = False
            return fn(*args, **kwargs)

    exe_dict = find_executable(Path(sys.executable).parent.as_posix())
    # Prefer the CASA launcher over the modular environment's mpirun.
    mpiexec = exe_dict.get('mpicasa') or exe_dict.get('mpirun')
    if not mpiexec:
        LOG.warning('No MPI launcher found; falling back to serial in-process execution.')
        if _accepts_parallel(fn):
            kwargs['parallel'] = False
        return fn(*args, **kwargs)

    if isinstance(nproc, bool) or not isinstance(nproc, int) or nproc < 2:
        raise ValueError('nproc must be an integer of at least 2 (one CASA MPI client and at least one worker)')

    # Resolve the import-path for fn so the subprocess can reconstruct it.
    # __qualname__ is absent on CASA task objects (e.g. casatasks.tclean is a
    # _tclean instance), so fall back to __name__, then scan the module namespace.
    fn_module = getattr(fn, '__module__', None)
    fn_qualname = getattr(fn, '__qualname__', None) or getattr(fn, '__name__', None)
    if fn_qualname is None and fn_module:
        _mod = importlib.import_module(fn_module)
        fn_qualname = next((k for k, v in vars(_mod).items() if v is fn), None)
    if fn_module is None or fn_qualname is None:
        raise ValueError(
            f'Cannot determine import path for {fn!r}; '
            'pass a module-level callable or a CASA task accessible via its module.'
        )

    # Serialize fn by value (bytecode) so the subprocess can reconstruct it
    # without importing its source module — avoids pulling in the full pipeline
    # package just to find the callable.
    # Fall back to module+qualname reference when cloudpickle is unavailable or
    # cannot serialize fn by value (e.g. SWIG-wrapped C++ objects like casatasks.tclean).
    _fn_module_obj = sys.modules.get(fn_module) if fn_module else None
    fn_bytes = None
    try:
        import cloudpickle as _cloudpickle

        if _fn_module_obj is not None:
            _cloudpickle.register_pickle_by_value(_fn_module_obj)
        try:
            fn_bytes = _cloudpickle.dumps(fn)
        except Exception:
            fn_bytes = None  # will fall back to module+qualname in the subprocess
        finally:
            if _fn_module_obj is not None:
                _cloudpickle.unregister_pickle_by_value(_fn_module_obj)
    except ImportError:
        pass  # cloudpickle not installed; module+qualname fallback used below

    payload: dict = {'args': args, 'kwargs': kwargs}
    if fn_bytes is not None:
        payload['fn_bytes'] = fn_bytes
    else:
        payload['fn_module'] = fn_module
        payload['fn_qualname'] = fn_qualname

    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pkl') as f_in:
        input_file = f_in.name
        pickle.dump(payload, f_in)

    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pkl') as f_out:
        output_file = f_out.name

    # Local import: defers casatasks (and CASA C++ startup) until an MPI
    # subprocess is actually launched.
    import casatasks

    try:
        script = textwrap.dedent(
            f"""\

            import pickle
            import sys
            import traceback

            # casaconfig must be updated before importing casatasks
            import casaconfig.config
            casaconfig.config.logfile = {casatasks.casalog.logfile()!r}
            casaconfig.config.log2term = {bool(getattr(casaconfig.config, 'log2term', False))}

            import casampi.private.start_mpi  # necessary if not executed via casashell
            import casatasks
            casatasks.casalog.showconsole(onconsole={bool(getattr(casaconfig.config, 'log2term', False))})

            from casampi.MPIEnvironment import MPIEnvironment
            from casampi.MPICommandClient import MPICommandClient
            _mpi_client = MPICommandClient()
            _mpi_client.set_log_mode('redirect')
            _mpi_client.start_services()

            with open({input_file!r}, 'rb') as f:
                data = pickle.load(f)

            if 'fn_bytes' in data:
                fn = pickle.loads(data['fn_bytes'])
            else:
                import importlib
                mod = importlib.import_module(data['fn_module'])
                fn = mod
                for attr in data['fn_qualname'].split('.'):
                    fn = getattr(fn, attr)

            try:
                result = fn(*data['args'], **data['kwargs'])
                with open({output_file!r}, 'wb') as f:
                    pickle.dump({{'success': True, 'result': result}}, f)
            except Exception as exc:
                traceback.print_exc()
                with open({output_file!r}, 'wb') as f:
                    pickle.dump({{'success': False,
                                'message': str(exc),
                                'type': type(exc).__name__,
                                'traceback': traceback.format_exc()}},
                                f)
                sys.exit(1)
            """
        )

        call_args = [sys.executable, '-c', script]

        xvfb_run = shutil.which('xvfb-run')
        # -e /dev/null silences xkbcomp keysym warnings written to Xvfb's stderr
        xvfb_args = [xvfb_run, '-a', '-e', '/dev/null'] if xvfb_run is not None else []

        env_args = [
            'PYTHONNOUSERSITE=1',
            'OMP_DISPLAY_AFFINITY=true',
            'OMP_PLACES=threads',
            'OMP_PROC_BIND=false',
            'OPENBLAS_NUM_THREADS=1',
            'OMP_NUM_THREADS=1',
            'KOKKOS_DISABLE_WARNINGS=1',
        ]

        mpi_args = [
            mpiexec,
            '-display-allocation',
            '-display-map',
            '-report-bindings',
            '--oversubscribe',
        ]
        for env_arg in env_args:
            mpi_args += ['-x', env_arg.split('=', 1)[0]]
        mpi_args += ['-n', str(nproc)]

        cmd_args = xvfb_args + mpi_args + call_args

        # cmd_args contains the full inline -c script; logging the joined form
        # produces an unparseable multi-line blob. Log the launcher prefix and
        # the script size separately so debug output stays readable.
        try:
            _c_idx = cmd_args.index('-c')
            LOG.debug(
                'Executing command: %s (+ %d-byte inline -c script)',
                ' '.join(cmd_args[:_c_idx]),
                len(cmd_args[_c_idx + 1]),
            )
        except ValueError:
            LOG.debug('Executing command: %s', ' '.join(cmd_args))

        env_run = os.environ.copy()
        # Strip coverage env vars so the subprocess does not produce a .coverage
        # file with a different measurement mode (branch vs statement), which
        # would cause pytest-cov's combine step to fail with DataError.
        for cov_var in (
            'COVERAGE_PROCESS_START',
            'COVERAGE_FILE',
            'COV_CORE_SOURCE',
            'COV_CORE_CONFIG',
            'COV_CORE_DATAFILE',
        ):
            env_run.pop(cov_var, None)
        env_overrides: dict[str, str] = {}
        for env_arg in env_args:
            key, _, value = env_arg.partition('=')
            env_overrides[key] = value
            env_run[key] = value

        LOG.debug('With environment variables: %s', env_overrides)

        try:
            subprocess.run(cmd_args, check=True, shell=False, capture_output=False, env=env_run)
        except subprocess.CalledProcessError as e:
            LOG.error('Subprocess failed; returncode=%s', e.returncode)
            raise RuntimeError(f'MPI subprocess execution of {fn_module}.{fn_qualname} failed') from e

        try:
            with open(output_file, 'rb') as f:
                output = pickle.load(f)
        except (FileNotFoundError, OSError, EOFError) as e:
            LOG.error('Failed to read output file %s: %s', output_file, e)
            raise RuntimeError(
                f"Failed to read output file '{output_file}'. "
                'This may be due to disk space issues, permission errors, or a problem in the subprocess.'
            ) from e

        if not output.get('success', False):
            raise RuntimeError(
                f'{output.get("type")}: {output.get("message")}\n'
                f'Remote traceback:\n{output.get("traceback", "<not available>")}'
            )

        return output.get('result')

    finally:
        try:
            Path(input_file).unlink(missing_ok=True)
            Path(output_file).unlink(missing_ok=True)
        except Exception:
            LOG.debug('Failed to remove temporary files', exc_info=True)
