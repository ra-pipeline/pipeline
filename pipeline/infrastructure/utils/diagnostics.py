"""Diagnostics module for profiling and monitoring pipeline execution.

This module provides utility functions to enable various diagnostic tools
for tracking resource usage during pipeline runs:

- **psrecord**: Monitor CPU, memory, and I/O usage over time
- **memstats**: Log memory usage before/after each pipeline task
- **fd_logs**: Track open file descriptors at regular intervals

Example usage::

    from pipeline.infrastructure.utils.diagnostics import enable_psrecord, enable_memstats

    # Enable process monitoring (writes to psrecord-*.log)
    enable_psrecord()

    # Enable memory statistics logging
    enable_memstats()

Note:
    Some features are platform-specific and may not work on macOS.
    MPI environments have special handling to avoid duplicate monitoring.
"""

import atexit
import functools
import os
import platform
import subprocess
import sys
import threading

import ps_mem

from pipeline.config import config

from .. import jobrequest, logging, mpihelpers

LOG = logging.get_logger(__name__)

__all__ = ['enable_fd_logs', 'enable_memstats', 'enable_psrecord', 'disable_psrecord']


def _cleanup_psrecord():
    """Terminate the psrecord subprocess if running."""
    if enable_psrecord.process is not None:
        LOG.info('Terminating psrecord subprocess')
        enable_psrecord.process.terminate()
        try:
            enable_psrecord.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            LOG.warning('psrecord did not terminate gracefully, killing')
            enable_psrecord.process.kill()
            enable_psrecord.process.wait()
        enable_psrecord.process = None
        enable_psrecord.enabled = False


def enable_psrecord():
    """Enable psrecord logging for the current process."""
    if mpihelpers.MPIEnvironment.is_mpi_enabled and not mpihelpers.MPIEnvironment.is_mpi_client:
        # disallow psrecord on MPI server processes
        return

    if enable_psrecord.enabled:
        LOG.warning('psrecord logging is already enabled')
        return

    casa_logfile = config['casaconfig']['logfile']
    LOG.info('Enabling psrecord logging')
    pid = os.getpid()
    # Use sys.executable to ensure we use the same Python interpreter
    try:
        psrecord_logfile = os.path.join(
            os.path.dirname(casa_logfile),
            f'psrecord-{os.path.basename(casa_logfile).replace("casa-", "")}',
        )
        enable_psrecord.process = subprocess.Popen([
            sys.executable, '-m', 'psrecord', str(pid),
            '--log', psrecord_logfile,
            '--interval', '1.0',
            '--include-children', '--include-io', '--include-cache',
            '--include-dir', os.getcwd(),
        ])
    except (OSError, ValueError) as exc:
        LOG.error('Failed to start psrecord subprocess: %s', exc)
        enable_psrecord.process = None
        enable_psrecord.enabled = False
        return
    enable_psrecord.enabled = True

    # Register cleanup handler
    atexit.register(_cleanup_psrecord)


enable_psrecord.enabled = False
enable_psrecord.process = None


def disable_psrecord():
    if not enable_psrecord.enabled:
        LOG.warning('psrecord logging is not enabled')
        return

    _cleanup_psrecord()
    try:
        atexit.unregister(_cleanup_psrecord)
    except ValueError:
        # _cleanup_psrecord was not registered with atexit; nothing to do
        LOG.debug('psrecord cleanup handler was not registered with atexit')
    LOG.info('psrecord logging disabled')


def enable_memstats():

    if platform.system() == 'Darwin':
        LOG.error('Cannot measure memory on OS X.')
        return

    if enable_memstats.enabled:
        LOG.error('enable_memstats() already enabled')
        return

    LOG.info('Enabling memory statistics logging')
    import pipeline.domain.measures as measures

    def get_hook_fn(msg):
        pid = os.getpid()

        def log_mem_usage(jobrequest):
            sorted_cmds, shareds, _, _ = ps_mem.get_memory_usage([pid, ], False, True)
            for cmd in sorted_cmds:
                private = measures.FileSize(cmd[1] - shareds[cmd[0]],
                                            measures.FileSizeUnits.KILOBYTES)
                shared = measures.FileSize(shareds[cmd[0]],
                                           measures.FileSizeUnits.KILOBYTES)
                total = measures.FileSize(cmd[1], measures.FileSizeUnits.KILOBYTES)

                LOG.info('%s%s: private=%s shared=%s total=%s' % (
                    msg, jobrequest.fn_name, str(private),
                    str(shared), str(total)))

            vm_accuracy = ps_mem.shared_val_accuracy()
            if vm_accuracy == -1:
                LOG.warning("Shared memory is not reported by this system. "
                            "Values reported will be too large, and totals "
                            "are not reported")
            elif vm_accuracy == 0:
                LOG.warning("Shared memory is not reported accurately by "
                            "this system. Values reported could be too "
                            "large, and totals are not reported.")
            elif vm_accuracy == 1:
                LOG.warning("Shared memory is slightly over-estimated by "
                            "this system for each program, so totals are "
                            "not reported.")

        return log_mem_usage

    jobrequest.PREHOOKS.append(get_hook_fn('Memory usage before '))
    jobrequest.POSTHOOKS.append(get_hook_fn('Memory usage after '))
    enable_memstats.enabled = True

    if mpihelpers.is_mpi_ready():
        mpi_server_list = mpihelpers.MPIEnvironment.mpi_server_rank_list()
        mpihelpers.mpiclient.push_command_request('pipeline.infrastructure.utils.enable_memstats()', block=True,
                                                  target_server=mpi_server_list)


enable_memstats.enabled = False


class Interval(object):
    def __init__(self, interval, function, args=None, kwargs=None):
        """
        Runs the function at a specified interval with given arguments.
        """
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}
        self.interval = interval
        self.function = functools.partial(function, *args, **kwargs)
        self.running = False
        self._timer = None

    def __call__(self):
        """
        Handler function for calling the partial and continuting.
        """
        self.running = False  # mark not running
        self.start()  # reset the timer for the next go
        self.function()  # call the partial function

    def start(self):
        """
        Starts the interval and lets it run.
        """
        if self.running:
            # Don't start if we're running!
            return

        # Create the timer object, start and set state.
        self._timer = threading.Timer(self.interval, self)
        self._timer.start()
        self.running = True

    def stop(self):
        """
        Cancel the interval (no more function calls).
        """
        if self._timer:
            self._timer.cancel()
        self.running = False
        self._timer = None


def enable_fd_logs(interval_secs=60):
    """
    Log file descriptors to the CASA log every n seconds.

    :param interval_secs: logging cadence in seconds (default=60)
    :return:
    """
    if platform.system() == 'Darwin':
        LOG.error('Cannot list file descriptors on macOS')
        return

    if enable_fd_logs.enabled:
        LOG.error('enable_memstats() already enabled')
        return

    LOG.info('Enabling file descriptor logging')
    import pipeline.infrastructure.jobrequest as jobrequest

    pid = os.getpid()

    def list_file_descriptors(msg, job_name):
        try:
            out = subprocess.check_output(['ls', '-l', '/proc/{}/fd'.format(pid)])
        except subprocess.CalledProcessError:
            LOG.info('Could not list file descriptors for PID {}'.format(pid))
        else:
            LOG.info('File descriptors {} {}:\n{}'.format(msg, job_name, out))

    def get_hook_fn(msg, start=False, cancel=False):
        def log_file_descriptors(jobrequest):
            job_name = jobrequest.fn_name
            if start:
                if enable_fd_logs.interval:
                    enable_fd_logs.interval.stop()
                LOG.info('Logging file descriptors every {} seconds during {}'.format(interval_secs, job_name))
                enable_fd_logs.interval = Interval(interval_secs, list_file_descriptors, args=['during', job_name])
                enable_fd_logs.interval.start()

            if cancel and enable_fd_logs.interval:
                enable_fd_logs.interval.stop()
                enable_fd_logs.interval = None

            list_file_descriptors(msg, job_name)

        return log_file_descriptors

    jobrequest.PREHOOKS.append(get_hook_fn('before', start=True))
    jobrequest.POSTHOOKS.append(get_hook_fn('after', cancel=True))
    enable_fd_logs.enabled = True

    if mpihelpers.is_mpi_ready():
        cmd = 'pipeline.infrastructure.utils.enable_fd_logs({})'.format(interval_secs)
        mpi_server_list = mpihelpers.MPIEnvironment.mpi_server_rank_list()
        mpihelpers.mpiclient.push_command_request(cmd, block=True, target_server=mpi_server_list)


enable_fd_logs.interval = None
enable_fd_logs.enabled = False
