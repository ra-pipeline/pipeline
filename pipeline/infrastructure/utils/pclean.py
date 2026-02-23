"""Utility module to run CASA's parallel tclean via subprocess.

Wraps CASA's ``tclean`` task with transparent support for both serial
(in-process) and parallel (subprocess/MPI) execution. The core motivation
is to enable MPI-parallel ``tclean`` runs even when the main pipeline
process is **not** launched under MPI, making it straightforward to
dispatch them as independent job requests across the computing cluster.

It achieves this by serializing the call arguments, spawning a subprocess
(optionally prefixed with an MPI launcher), and deserializing the result
(essentially the ``tclean`` return dictionary).

Parallel execution flow:

1. **Serialize** — ``args``, ``kwargs``, and ``parallel=True`` are pickled
   to a temporary input file.
2. **Build command** — An inline Python script is generated that:

   - Configures ``casaconfig`` (log file, console logging).
   - Initialises the MPI environment (``casampi``).
   - Loads the pickled arguments, calls ``tclean``, and writes the result
     (or error) to a temporary output file.

3. **Locate MPI launcher** — ``find_executable`` searches for ``mpicasa``
   (preferred) or ``mpirun``. If neither is found, execution falls back to
   a plain Python subprocess.
4. **Optional Xvfb** — If ``xvfb-run`` is on ``PATH``, the command is
   wrapped to avoid display issues.
5. **Run & collect** — ``subprocess.run`` executes the command. The pickled
   output file is read back; on failure a ``RuntimeError`` is raised with
   the remote traceback.
6. **Cleanup** — Temporary files are removed in a ``finally`` block.
"""
import os
import pickle
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Optional

import casaconfig.config
import casatasks
from pipeline.infrastructure import logging

LOG = logging.get_logger(__name__)


def find_executable(start_dir: Optional[str] = None) -> dict[str, Optional[str]]:
    """Search upward from start_dir for MPI-related executables.

    The function looks for 'bin/mpirun', 'bin/mpicasa' and 'bin/casa' in the
    current directory and each parent until the filesystem root is reached.

    Args:
        start_dir: Directory to start searching from. If None, use cwd.

    Returns:
        Mapping from executable name to absolute path or None if not found.
    """
    search_patterns = ['mpirun', 'mpicasa', 'casa']
    exe_dict: dict[str, Optional[str]] = dict.fromkeys(search_patterns)
    current = Path(start_dir or Path.cwd()).resolve()

    for pattern in search_patterns:
        cur = current
        found: Optional[str] = None
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


def pclean(
    *args: Any,
    parallel: bool | dict[str, int] = False,
    **kwargs: Any,
) -> Any:
    """Execute tclean and return the result.

    When ``parallel`` is False, tclean is invoked directly in-process.
    When ``parallel`` is True or a dict, the function serializes arguments
    to a temporary file and runs a Python subprocess (optionally under MPI).
    The subprocess writes a pickled result to a second temporary file which
    is read back here. This allows tclean to run in parallel mode even when
    the main process is not running under MPI.

    Args:
        *args: Positional arguments forwarded to tclean.
        parallel: Controls execution mode.
            False runs serially in-process.
            True spawns a subprocess with MPI (4 processes by default).
            A dict ``{'nproc': N}`` spawns a subprocess with N MPI processes.
        **kwargs: Keyword arguments forwarded to tclean.

    Returns:
        The (picklable) return value from tclean.

    Raises:
        RuntimeError: If the subprocess reports an error or the call fails.
    """
    if parallel is False:
        return casatasks.tclean(*args, parallel=parallel, **kwargs)

    # prepare temporary files
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pkl') as f_in:
        input_file = f_in.name
        pickle.dump({'args': args, 'parallel': True, 'kwargs': kwargs}, f_in)

    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.pkl') as f_out:
        output_file = f_out.name

    try:
        # Inline script to run inside the subprocess
        script = textwrap.dedent(
            f"""\

            import pickle
            import sys
            import traceback

            # casaconfig should be imported/updated first before importing casatasks
            # the statement order matters here
            import casaconfig.config
            casaconfig.config.logfile={casatasks.casalog.logfile()!r}
            casaconfig.config.log2term = {bool(getattr(casaconfig.config, 'log2term', False))}
            
            import casampi.private.start_mpi  # necessary if not executed via casashell
            import casatasks
            from casatasks import tclean
            casatasks.casalog.showconsole(onconsole={bool(getattr(casaconfig.config, 'log2term', False))})
            
            from casampi.MPIEnvironment import MPIEnvironment
            from casampi.MPICommandClient import MPICommandClient
            _client = MPICommandClient()
            _client.set_log_mode('redirect')
            _client.start_services()
            
            with open({input_file!r}, 'rb') as f:
                data = pickle.load(f)
                args = data['args']
                kwargs = data['kwargs']
                parallel = data['parallel']

            try:
                result = tclean(*args, parallel=parallel, **kwargs)
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

        # Base call: run the Python interpreter with the inline script
        # We intentionally avoid `casa` or `python -m casashell` here to reduce
        # dependencies and differential between monolithic and modular CASA6 environments.
        # casatasks should be importable directly from the standard Python environment.
        call_args = [sys.executable, '-c', script]

        # If an X virtual framebuffer wrapper exists, run with it
        xvfb_run = shutil.which('xvfb-run')
        xvfb_args = [xvfb_run, '-a'] if xvfb_run is not None else []

        # Environment variables controlling casa session behavior
        env_args = [
            'PYTHONNOUSERSITE=1',
            'OMP_DISPLAY_AFFINITY=true',
            'OMP_PLACES=threads',
            'OMP_PROC_BIND=false',
            'OPENBLAS_NUM_THREADS=1',
            'OMP_NUM_THREADS=1',
            'KOKKOS_DISABLE_WARNINGS=1',
        ]

        # If parallel is requested, prefix with an MPI launcher
        mpi_args = []
        if parallel:
            if isinstance(parallel, dict):
                nproc = int(parallel.get('nproc', 4))
            else:
                nproc = 4

            exe_dict = find_executable(Path(sys.executable).parent.as_posix())
            # mpicasa (monolithic env) takes precedence over mpirun (modular env)
            # note that shutil.which('mpirun') may also find a system-wide mpirun -- which usually does not work
            mpiexec = exe_dict.get('mpicasa') or exe_dict.get('mpirun')  # or shutil.which('mpirun')
            if not mpiexec:
                LOG.warning('No MPI launcher found; falling back to serial Python execution.')
            else:
                # build MPI launcher arguments
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

        # Copy current environment and modify as needed
        env_run = os.environ.copy()
        env_overrides: dict[str, str] = {}
        for env_arg in env_args:
            key, _, value = env_arg.partition('=')
            env_overrides[key] = value
            env_run[key] = value

        LOG.debug('Executing command: %s', ' '.join(cmd_args))
        LOG.debug(
            'With environment variables: %s',
            env_overrides,
        )

        try:
            subprocess.run(cmd_args, check=True, shell=False, capture_output=False, env=env_run)
        except subprocess.CalledProcessError as e:
            LOG.error('Subprocess failed; returncode=%s', e.returncode)
            raise RuntimeError('tclean subprocess execution failed') from e

        # read result
        try:
            with open(output_file, 'rb') as f:
                output = pickle.load(f)
        except (FileNotFoundError, OSError) as e:
            LOG.error('Failed to read output file %s: %s', output_file, e)
            raise RuntimeError(
                f"Failed to read output file '{output_file}'. "
                'This may be due to disk space issues, permission errors, or a problem in the subprocess.'
            ) from e

        if not output.get('success', False):
            raise RuntimeError(f'{output.get("type")}: {output.get("message")}')

        return output.get('result')

    finally:
        # cleanup temporary files
        try:
            Path(input_file).unlink(missing_ok=True)
            Path(output_file).unlink(missing_ok=True)
        except Exception:
            LOG.debug('Failed to remove temporary files', exc_info=True)


