import pickle
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Dict, Optional, Union

import casaconfig.config
import casatasks

from pipeline.infrastructure import logging

LOG = logging.get_logger(__name__)


def find_executable(start_dir: Optional[str] = None) -> Dict[str, Optional[str]]:
    """Search upward from start_dir for MPI-related executables.

    The function looks for 'bin/mpirun', 'bin/mpicasa' and 'bin/casa' in the
    current directory and each parent until the filesystem root is reached.

    Args:
        start_dir: Directory to start searching from. If None, use cwd.

    Returns:
        Mapping from executable name to absolute path or None if not found.
    """
    search_patterns = ['mpirun', 'mpicasa', 'casa']
    exe_dict: Dict[str, Optional[str]] = dict.fromkeys(search_patterns)
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
    parallel: Union[bool, Dict[str, int]] = False,
    **kwargs: Any,
) -> Any:
    """Execute tclean and return the result.

    When `parallel` is False, tclean is invoked directly in-process. When
    `parallel` is True or a dict, the function serializes arguments to a
    temporary file and runs a Python subprocess (optionally under MPI).
    The subprocess writes a pickled result to a second temporary file which
    is read back here. This allows tclean to run in parallel mode even when the
    main process is not running under MPI.

    Args:
        *args: Positional arguments forwarded to tclean.
        parallel: False to run serially, True or dict to run via subprocess/MPI.
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

            # casaconfig should be imported/updated first before importing casatasks
            # the statement order matters here
            import casaconfig.config
            casaconfig.config.logfile={casatasks.casalog.logfile()!r}
            casaconfig.config.log2term = {bool(getattr(casaconfig.config, 'log2term', False))}
            
            import casampi.private.start_mpi  # nescary if not executed via casashell
            import casatasks
            from casatasks import tclean
            casatasks.casalog.showconsole(onconsole={bool(getattr(casaconfig.config, 'log2term', False))})
            
            # from casampi.MPIEnvironment import MPIEnvironment
            # from casampi.MPICommandClient import MPICommandClient
            # __client = MPICommandClient()
            # __client.set_log_mode('redirect')
            # __client.start_services()
            

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
                with open({output_file!r}, 'wb') as f:
                    pickle.dump({{'success': False, 'error': str(exc), 'type': type(exc).__name__}}, f)
                sys.exit(1)
            """
        )

        # Base call: run the Python interpreter with the inline script
        # We intentionally avoid `casa` or `python -m casashell` here to reduce
        # dependencies and diffiencetial between monolithic and modular CASA6 environments.
        # casatasks should be importable directly from the standard Python environment.
        call_args = [sys.executable, '-c', script]

        # If parallel is requested, prefix with an MPI launcher
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
                mpi_args = [mpiexec, '-n', str(nproc), '-display-allocation', '-display-map', '-oversubscribe']
                call_args = mpi_args + call_args

        # If an X virtual framebuffer wrapper exists, run with it
        xvfb_run = shutil.which('xvfb-run')
        if xvfb_run:
            call_args = [xvfb_run, '-a'] + call_args

        LOG.debug('Executing command: %s', ' '.join(call_args))

        try:
            completed = subprocess.run(call_args, check=True, shell=False, capture_output=False, text=True)
            LOG.debug('Subprocess stdout: %s', completed.stdout)
            LOG.debug('Subprocess stderr: %s', completed.stderr)
        except subprocess.CalledProcessError as e:
            LOG.error('Subprocess failed; returncode=%s', e.returncode)
            LOG.error('stderr: %s', e.stderr)
            LOG.error('stdout: %s', e.stdout)
            raise RuntimeError('tclean subprocess execution failed') from e

        # read result
        with open(output_file, 'rb') as f:
            output = pickle.load(f)

        if not output.get('success', False):
            raise RuntimeError(f'{output.get("type")}: {output.get("error")}')

        return output.get('result')

    finally:
        # cleanup temporary files
        try:
            Path(input_file).unlink(missing_ok=True)
            Path(output_file).unlink(missing_ok=True)
        except Exception:
            LOG.debug('Failed to remove temporary files', exc_info=True)


