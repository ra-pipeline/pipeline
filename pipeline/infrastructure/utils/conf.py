from __future__ import annotations

import contextlib
import logging
import os
import platform
import shutil
import sys
import traceback
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import casaplotms
import casatasks
import casatasks.private.tec_maps as tec_maps

from .. import casa_tools, daskhelpers, mpihelpers
from .. import logging as pipeline_logging

if TYPE_CHECKING:
    from collections.abc import Generator
    from io import IOBase

old_stdout, old_stderr = sys.stdout, sys.stderr

__all__ = [
    'shutdown_plotms',
    'get_casa_session_details',
    'request_omp_threading',
    'reset_logfiles',
    'work_directory',
    'capture_output',
    'exec_func',
    'change_stream_for_all_streamhandlers',
]


LOG = pipeline_logging.get_logger(__name__)


def change_stream_for_all_streamhandlers(new_stream: IOBase, package_prefix: str | None = None) -> None:
    """Iterates over existing loggers and updates the stream of their StreamHandlers to the given new_stream.

    If package_prefix is provided, only loggers whose names start with the specified prefix will be modified.

    Args:
        new_stream: A file-like object (e.g., an open file, sys.stdout, sys.stderr) to set as the new output stream.
        package_prefix: Optional string. If provided, only loggers whose names start with this prefix are considered.

    Note: all `pipeline`-namespace logger are attached to a streamhandler by default, so to capture all
    debug level logging messages, we ovied the streamhadnler targets here.
    """
    # this module has a delayed import in the codebase, originatally code as an workaround from circular importing.
    try:
        import pipeline.infrastructure.renderer.htmlrenderer
    except ImportError:
        pass

    # Access the dictionary of existing logger instances managed by the logging module
    logger_dict: dict = logging.Logger.manager.loggerDict

    modified_handlers_count = 0
    inspected_loggers_count = 0

    # Iterate over all named loggers and the root logger
    for name in logger_dict:
        # Retrieve the logger instance
        if name == 'root':
            logger = logging.getLogger()  # Special handling for the root logger
        else:
            logger = logging.getLogger(name)
            if not isinstance(logger, logging.Logger):
                # Skip placeholder entries in the logger dictionary
                continue

        # If package_prefix is specified, only process loggers that match the prefix
        if package_prefix and not name.startswith(package_prefix):
            continue

        inspected_loggers_count += 1

        # Iterate over handlers directly attached to the logger
        for handler in logger.handlers:
            # Only consider handlers that are StreamHandlers
            if isinstance(handler, logging.StreamHandler):
                # Update the stream if it is different from the new_stream
                if handler.stream is not new_stream:
                    handler.stream = new_stream
                    modified_handlers_count += 1


def capture(fd):
    # note: casa-*log from pipeline session are all written by casalogsink (always in info1)
    # Python logger always:
    #   1) entries to steamhandlers
    #   2) foreward to casalosink (then go to files)
    # capture at the Python level and C level
    # as ipython+notebook will put them in ipykernel.iostream.OutStream,
    # you might only get CASA c++ logsink messages.

    # * pipes() will capture C output / to 'f' filedescriptor
    # * sys.stdout is also being directed to f filedescriotor
    # clean out

    import casatasks
    from wurlitzer import STDOUT, pipes

    casatasks.casalog.showconsole(onconsole=False)

    pipes(fd, stderr=STDOUT)
    sys.stdout, sys.stderr = fd, fd


def capture_start(file_path, package_prefix='pipeline'):
    fd = open(file_path, 'a', buffering=1)
    sys.stdout, sys.stderr = fd, fd
    from wurlitzer import sys_pipes_forever
    sys_pipes_forever(bufsize=0)
    casatasks.casalog.showconsole(onconsole=False)
    change_stream_for_all_streamhandlers(fd, package_prefix)


def capture_stop(package_prefix='pipeline'):
    from wurlitzer import stop_sys_pipes
    stop_sys_pipes()
    sys.stdout.close()
    sys.stderr.close()
    sys.stdout, sys.stderr = old_stdout, old_stderr
    casatasks.casalog.showconsole(onconsole=True)
    change_stream_for_all_streamhandlers(old_stdout, package_prefix)


@contextlib.contextmanager
def capture_output(file_path=None):
    # note: casa-*log from pipeline session are all written by casalogsink (always in info1)
    # Python logger always:
    #   1) entries to steamhandlers
    #   2) foreward to casalosink (then go to files)
    # capture at the Python level and C level
    # as ipython+notebook will put them in ipykernel.iostream.OutStream,
    # you might only get CASA c++ logsink messages.

    # * pipes() will capture C output / to 'f' filedescriptor
    # * sys.stdout is also being directed to f filedescriotor
    # clean out

    from wurlitzer import pipes
    casatasks.casalog.showconsole(onconsole=False)

    if file_path is None:
        file_path = casatasks.casalog.logfile()

    from wurlitzer import STDOUT
    with open(file_path, 'a', buffering=1) as f, pipes(f, stderr=STDOUT):
        old_stdout, old_stderr = sys.stdout, sys.stderr
        # old_stdout, old_stderr = sys.__stdout__, sys.__stderr__
        try:
            # the original stdout/stderr filedescriptor have been attached to individual Pipeline
            # named loggers, so override sys.stout is not sufficient to change their behavior.
            # make a short-term override
            change_stream_for_all_streamhandlers(f, 'pipeline')
            sys.stdout, sys.stderr = f, f
            yield
        finally:
            # revert back
            sys.stdout.flush()
            change_stream_for_all_streamhandlers(old_stdout, 'pipeline')
            sys.stdout, sys.stderr = old_stdout, old_stderr


def exec_func(fn: callable, *args, include_client: bool = True, **kwargs) -> None:
    """Execute the same function on both client and worker (dask-worker or mpiserver) processes.

    This function enables synchronized execution across MPI infrastructure. It's particularly useful
    for setup tasks that need consistent state across all processes, such as changing the working directory.

    Args:
        fn: The function to execute.
        *args: Positional arguments to pass to the function.
        include_client: If True, the function is also executed on the client process.
        **kwargs: Keyword arguments to pass to the function.
    """
    if include_client:
        fn(*args, **kwargs)
    mpihelpers.exec_func(fn, *args, include_client=False, **kwargs)
    daskhelpers.exec_func(fn, *args, include_client=False, **kwargs)


@contextlib.contextmanager
def work_directory(
    workdir: str,
    create: bool = False,
    cleanup: bool = False,
    reset: bool = True,
    capture_log: bool | str = False,
    subdir: bool = False,
    reraise_on_error: bool = True,
) -> Generator[str, None, None]:
    """A context manager to temporarily change the working directory.

    Changes the current working directory for a Pipeline session to the specified path.
    Optionally, it can restore the original directory upon exiting the context, create the
    directory, clean its contents, and manage CASA-specific configurations (e.g. casalog files)

    Args:
        workdir: The path to the target directory.
        create: If True, creates the directory (and subdirectories if `subdir`
            is True) if it does not already exist.
        cleanup: If True, recursively removes all files and directories within
            the target working directory before execution.
        reset: If True, resets CASA log files and other modules before execution
            and upon exit.
        capture_log: If True, captures CASA logs to a new timestamped log file. If
            a string is provided, it is used as the log file path.
        subdir: If True, creates and uses a standard subdirectory structure
            (products, working, rawdata) within `workdir`. The context will
            change into the 'working' subdirectory.
        reraise_on_error: If True, exceptions will be re-raised instead of just being logged.

    Yields:
        The absolute path to the CASA log file being used within the context.

    Example:
        with work_directory('/tmp/my_analysis', create=True, cleanup=True) as log_file:
            print(f"Working in directory. Logs are being saved to {log_file}")
            # Your code runs here, in the '/tmp/my_analysis' directory
    """
    last_path = os.getcwd()
    if subdir:
        # Define the standard pipeline processing subdirectory structure
        dir_checklist = [os.path.join(os.path.abspath(workdir), name) for name in ['working', 'rawdata', 'products']]
    else:
        dir_checklist = [os.path.abspath(workdir)]
    work_path = dir_checklist[0]

    if create:
        # Create directory structure if it doesn't exist
        # From a mpicasa-enabled CASA session, only the client process should create directories.
        for dir_to_create in dir_checklist:
            os.makedirs(dir_to_create, exist_ok=True)

    if cleanup and os.path.isdir(work_path):
        # Clean up the target directory's contents
        for item in os.listdir(work_path):
            item_path = os.path.join(work_path, item)
            if os.path.isfile(item_path) or os.path.islink(item_path):
                os.unlink(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)

    last_casa_logfile = casa_tools.casalog.logfile()
    ret_casa_logfile = last_casa_logfile

    if capture_log:
        if isinstance(capture_log, str):
            ret_casa_logfile = os.path.abspath(os.path.join(work_path, capture_log))
        else:
            now_str = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
            ret_casa_logfile = os.path.abspath(os.path.join(work_path, f'casa-{now_str}.log'))

    # The following operations are performed on all processes (using exec_func) to maintain consistency

    try:
        exec_func(os.chdir, work_path)
        if reset:
            exec_func(reset_logfiles, casa_logfile=ret_casa_logfile, prepend=False)
            # PIPE-1301: Shut down existing plotms to avoid side-effects from changing CWD.
            # This is a workaround for CAS-13626.
            exec_func(shutdown_plotms)
            exec_func(reset_tec_maps_module)
        if capture_log:
            exec_func(capture_start, ret_casa_logfile)
        yield ret_casa_logfile
    except Exception as ex:
        if reraise_on_error:
            # re-raises the caught exception, preserving its traceback
            raise
        else:
            LOG.info(
                'An error occurred while setting up the environment (e.g., changing directory to %s): %s - %s',
                work_path,
                type(ex).__name__,
                ex,
            )
            LOG.debug(traceback.format_exc())
    finally:
        exec_func(os.chdir, last_path)
        if reset:
            exec_func(reset_logfiles, casa_logfile=last_casa_logfile, prepend=False)
            exec_func(shutdown_plotms)
            exec_func(reset_tec_maps_module)
        if capture_log:
            exec_func(capture_stop)


def reset_logfiles(
    casacalls_logfile: str | None = None, casa_logfile: str | None = None, prepend: bool = False
) -> None:
    """Reset CASA/Pipeline logfiles for the current CASA/Pipeline session.

    This function is intended to be used at the beginning of each processing session after the CASA process
    switches to a new working directory. It configures both the casacalls and casa log files with optional
    content preservation from previous logs.

    Args:
        casacalls_logfile: Custom filename for the casacalls log. If None, a default name based on the hostname is used.
        casa_logfile: Custom filename for the casa log. If None, a timestamped name is generated.
        prepend: If True, content from the previous casa logfile is copied to the beginning of the new logfile.
    """
    # Configure casacalls log file
    if casacalls_logfile is None:
        casacalls_logfile = f'casacalls-{platform.node().split(".")[0]}.txt'

    pipeline_logging.get_logger(
        'CASACALLS', stream=None, format='%(message)s', addToCasaLog=False, filename=casacalls_logfile
    )

    # Configure casa log file
    if casa_logfile is None:
        now_str = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
        casa_logfile = os.path.abspath(f'casa-{now_str}.log')
    else:
        casa_logfile = os.path.abspath(casa_logfile)

    last_casa_logfile = casa_tools.casalog.logfile()
    casa_tools.casalog.setlogfile(casa_logfile)

    # Prepend previous log content if requested and not running as MPI server
    # We only run this from the client side to avoid a race condition.
    if (
        prepend
        and not mpihelpers.is_mpi_server()
        and os.path.exists(last_casa_logfile)
        and casa_logfile != last_casa_logfile
    ):
        with open(last_casa_logfile, 'r') as infile:
            with open(casa_logfile, 'a') as outfile:
                outfile.write(infile.read())


@contextlib.contextmanager
def request_omp_threading(num_threads: int | None = None):
    """A context manager to override the session-wise OMP threading setting on CASA MPI client.

    This function improves certain CASAtask/tool call performance on the MPI client by
    temporarily enabling OpenMP threading while the MPI servers are idle. The feature only
    takes effect under restricted circumstances to avoid competing with MPI server processes
    from tier0 or tier1 parallelization.

    This function can be used as both a decorator and context manager:

    Example usage as decorator:
        @request_omp_threading(4)
        def do_something():
            ...

    Example usage as context manager:
        with request_omp_threading(4):
            immoments(..)

    Note:
        * Use with caution and carefully examine computing resource allocation at the execution point.
        * The casalog.ompGet/SetNumThreads() API doesn't work as expected on macOS as of CASA ver6.6.1,
          although runtime env var (i.e. OMP_NUM_THREADS) is respected.
    """
    session_num_threads = casa_tools.casalog.ompGetNumThreads()
    LOG.debug(f'session_num_threads = {session_num_threads}')
    is_mpi_ready = mpihelpers.is_mpi_ready()  # Returns True if MPI is ready and we are on the MPI client

    num_threads_limits = []

    # This is generally inherited from cgroup, but might be sub-optimal (too large) for high core-count
    # workstations when cgroup limit is not applied
    casa_num_cpus = casa_tools.casalog.getNumCPUs()
    LOG.debug(f'casalog.getNumCPUs() = {casa_num_cpus}')
    num_threads_limits.append(casa_num_cpus)

    # Check against MPI.UNIVERSE_SIZE, which is another way to limit the number of threads
    # See https://www.mpi-forum.org/docs/mpi-4.0/mpi40-report.pdf (Sec. 11.10.1, Universe Size)
    try:
        from mpi4py import MPI

        if MPI.UNIVERSE_SIZE != MPI.KEYVAL_INVALID:
            universe_size = MPI.COMM_WORLD.Get_attr(MPI.UNIVERSE_SIZE)
            LOG.debug(f'MPI.UNIVERSE_SIZE = {universe_size}')
            if isinstance(universe_size, int) and universe_size > 1:
                num_threads_limits.append(universe_size)
        world_size = MPI.COMM_WORLD.Get_size()
        LOG.debug(f'MPI.COMM_WORLD.Get_size() = {world_size}')
        if isinstance(world_size, int) and world_size > 1:
            num_threads_limits.append(world_size)
    except ImportError:
        pass

    max_num_threads = min(num_threads_limits)

    context_num_threads = None
    if is_mpi_ready and session_num_threads == 1 and max_num_threads > 1:
        if num_threads is not None:
            if 0 < num_threads <= max_num_threads:
                max_num_threads = num_threads
            else:
                LOG.warning(
                    f'The requested num_threads ({num_threads}) is larger than the optimal number of logical CPUs '
                    f'({max_num_threads}) assigned for this CASA session.'
                )

        context_num_threads = max_num_threads
    try:
        if context_num_threads is not None:
            casa_tools.casalog.ompSetNumThreads(context_num_threads)
            LOG.info(f'adjust openmp threads to {context_num_threads}')
        yield
    finally:
        if context_num_threads is not None:
            casa_tools.casalog.ompSetNumThreads(session_num_threads)
            LOG.info(f'restore openmp threads to {session_num_threads}')


def shutdown_plotms() -> None:
    """Shutdown the existing plotms process in the current CASA session.

    This utility function shuts down the persistent plotms process in the current CASA session, allowing the next plotms call
    to start from a fresh process. It's implemented as a short-term workaround for two issues related to plotms persistence:
        1. A plotms process always uses the initial working directory for output paths with relative filenames (CAS-13626),
            even after the Python working directory has changed.
        2. A plotms process continues using the same casa logfile it started with, even after the casa log file
            location has been changed.

    Note: This implementation follows the approach used in casaplotms.private.plotmstool.__stub_check()
    """
    plotmstool = casaplotms.plotmstool

    if plotmstool.__proc is not None:
        plotmstool.__proc.kill()  # Terminate the plotms process
        plotmstool.__proc.communicate()  # Wait for process to exit completely
        plotmstool.__proc = None  # Reset process reference
        plotmstool.__stub = None  # Reset stub reference
        plotmstool.__uri = None  # Reset URI reference


def reset_tec_maps_module():
    # PIPE-1432: reset casatasks/tec_maps.workDir as it's unaware of a CWD change.
    if hasattr(tec_maps, 'workDir'):
        tec_maps.workDir = os.getcwd() + '/'


def get_casa_session_details() -> dict[str, any]:
    """Get the current CASA session details.

    Collects and returns information about the current CASA environment, including paths, thread configuration,
    and system resource allocation.

    Returns:
        A dictionary containing the following information:
        - casa_dir: Root directory of the monolithic CASA distribution
        - omp_num_threads: Number of OpenMP threads in the current parallel region
        - data_path: CASA data paths currently in use
        - numa_mem: Memory properties from the NUMA software perspective
        - numa_cpu: CPU properties from the NUMA software perspective

        Note: The CPU/memory properties reported here reflect the NUMA software view, which may differ from
        hardware specifications obtained through standard Python functions (e.g., os.cpu_count()) or pipeline.environment.
        For details on the distinction between software and hardware nodes, see:
        https://www.kernel.org/doc/html/latest/vm/numa.html
    """
    casa_session_details = casa_tools.utils.hostinfo()
    casa_session_details['casa_dir'] = casa_tools.utils.getrc()  # Add CASA installation directory
    casa_session_details['omp_num_threads'] = casa_tools.casalog.ompGetNumThreads()  # Add OpenMP thread count
    casa_session_details['data_path'] = casa_tools.utils.defaultpath()  # Add CASA data path
    casa_session_details['numa_cpu'] = casa_session_details.pop('cpus')  # Rename cpus key for clarity
    casa_session_details['numa_mem'] = casa_session_details.pop('memory')  # Rename memory key for clarity

    return casa_session_details
