"""Helper functions for using Dask for parallel processing in the pipeline.

This module provides functions to start and stop a Dask cluster,
submit tasks to the cluster, and retrieve results.  It also includes
functions to determine if the current process is a Dask worker and
whether Dask is ready for use.  The module leverages Dask's `delayed`
functionality and `Future` objects for parallel task execution and
result management.  It also handles merging of CASA command logs from
distributed workers.

The module uses a custom `FutureTask` class to encapsulate the submission
and retrieval of results from Dask futures.  The `future_exec` function
is used by Dask workers to execute the actual pipeline tasks.  The
`is_dask_ready` function checks if a Dask client is available and
`tier0futures` is enabled, indicating readiness for parallel processing
using Dask.
"""

from __future__ import annotations

import atexit
import datetime
import importlib.util
import os
import socket
import subprocess
from contextlib import contextmanager
from importlib.resources import files
from pprint import pformat
from typing import TYPE_CHECKING

import casatasks

import pipeline.infrastructure as infrastructure
from pipeline.config import config
from pipeline.infrastructure.utils import get_obj_size, human_file_size

if TYPE_CHECKING:
    from typing import Callable

    from dask.distributed import Client, LocalCluster, Worker
    from dask_jobqueue import HTCondorCluster, SLURMCluster

# Check if all required dask modules are available
dask_spec = importlib.util.find_spec('dask')
distributed_spec = importlib.util.find_spec('distributed')
dask_jobqueue_spec = importlib.util.find_spec('dask_jobqueue')
dask_available = all([dask_spec, distributed_spec, dask_jobqueue_spec])


if importlib.util.find_spec('casampi'):
    from casampi.MPIEnvironment import MPIEnvironment
    from mpi4py import MPI
    is_mpi_session = MPIEnvironment.is_mpi_enabled
    is_mpi_worker = MPIEnvironment.is_mpi_enabled and not MPIEnvironment.is_mpi_client
    mpi_rank = MPI.COMM_WORLD.Get_rank()
else:
    is_mpi_session = False
    is_mpi_worker = False
    mpi_rank = 0

if dask_available and not is_mpi_worker:
    # Avoid importing Dask in MPI worker processes because some Python libraries (e.g., signal)
    # are restricted to the main thread of the main interpreter.
    import dask
    from dask.distributed import Client, LocalCluster
    from dask.distributed import Worker
    from dask_jobqueue import HTCondorCluster, SLURMCluster


daskclient: Client | None = None
tier0futures: bool = False

LOG = infrastructure.logging.get_logger(__name__)

__all__ = [
    'is_worker',
    'daskclient',
    'tier0futures',
    'dask_available',
    'is_dask_ready',
]


@contextmanager
def sanitized_env():
    """Temporarily remove OpenMPI/PMIx environment variables."""
    # Define the prefixes of variables to be removed
    mpi_prefixes = ('PMIX', 'PRTE', 'OMPI', 'PMIX_SERVER', 'PRTE_')

    # Save the original state of the variables to be removed
    original_env = {}
    for key in list(os.environ):
        for prefix in mpi_prefixes:
            if key.startswith(prefix):
                original_env[key] = os.environ.pop(key)
                break
    try:
        yield
    finally:
        # Restore the original environment
        os.environ.update(original_env)


def sanitize_env_for_children() -> None:
    """Remove MPI/PMIx environment variables that can confuse child processes.

    This function removes environment variables with specific MPI-related prefixes
    that can cause MPI_Init failures in child processes. These variables may confuse
    OpenMPI when child processes are not properly registered as ranks.

    Note:
        This should typically be called on rank 0 only, and only when removing
        these variables won't affect other MPI ranks.

    Warning:
        Child processes inheriting MPI environment variables may experience
        MPI_Init failures due to registration conflicts.
    """
    # MPI-related prefixes that should be removed from child process environments,
    # mainly relevant to LocalCluster which uses multiprocessing.
    # mpi_prefixes=("OMPI_", "PMI_", "PMIX", "PRTE", "SLURM_", 'OPAL_')
    mpi_prefixes = ('PMIX', 'PRTE', 'OMPI', 'PMIX_SERVER', 'PRTE_')

    for prefix in mpi_prefixes:
        for key in list(os.environ):
            if key.startswith(prefix):
                os.environ.pop(key, None)


def is_worker() -> bool:
    """Determine if the current process is running as a Dask worker or MPI-Server.

    This function checks if the current Python process is executing inside a Dask
    worker. It uses a reliable method that works even during the worker setup
    process, specifically by checking for active worker instances using weak
    references.

    See: https://stackoverflow.com/questions/78589634/what-is-the-cleanest-way-to-detect-whether-im-running-in-a-dask-worker

    Note that currently is it's running a mpicasa session, this will always return
    true before the hybride-mod (co-operating mpi cluster + dask cluster) is fully
    tested.

    Returns:
        True if the process is a Dask worker, False otherwise.
    """
    is_worker = False
    if (Worker and Worker._instances) or is_mpi_session:
        is_worker = True
    return is_worker


def is_daskclient_allowed() -> bool:
    """Check if Dask client/initialization is allowed in the current process.

    Returns:
        True if a Dask client/cluster initialization is permitted, False otherwise.
    """
    # Disallow starting dask client if running inside a MPI worker process.
    # This can be identified by both RANK or casampi APIs.
    if is_mpi_worker or mpi_rank != 0:
        return False

    # Disallow starting dask client if running inside a dask worker process,
    # identified by env variables.
    if any(os.getenv(var) for var in ['DASK_WORKER_NAME', 'DASK_PARENT']):
        return False

    # Disallow starting dask client if there are existing dask worker instances,
    # identified by weak references.
    return dask_available and not (Worker and Worker._instances)


def is_dask_worker() -> bool:
    """Check if the current process is a Dask worker.

    Since Dask worker processes may not have fully initialized the Worker
    instance at the time this function is called (e.g. Worker Plugin), we
    use environment variables and Worker object weak reference to reliably
    determine if the current process is functioning as a Dask worker.

    Note that get_worker() returns the specific Worker instance only after it is
    fully initialized and relies on thread-local Context variables. So calling
    it too early or from a new thread may lead to errors.

    Returns:
        True if the current process is a Dask worker, False otherwise.
    """
    return any(os.getenv(var) for var in ['DASK_WORKER_NAME', 'DASK_PARENT']) or bool(
        dask_available and Worker and Worker._instances
    )


class FutureTask:
    """Encapsulates the submission and retrieval of results from Dask futures.

    This class simplifies the interaction with Dask futures, providing a
    consistent interface for submitting tasks and retrieving results. It also
    handles merging of CASA command logs from distributed workers.
    """

    def __init__(self, executable):
        """Submits a task to the Dask cluster.

        Args:
            executable: The executable object to be run on a Dask worker.
        """
        LOG.debug(
            'submitting a FutureTask %s from the dask client: %s',
            executable,
            human_file_size(get_obj_size(executable)),
        )
        # pure=False to disable dask caching, as the same task with same args might be submitted multiple times
        # but with different underlying data (e.g. different MS files)
        #
        # see: https://distributed.dask.org/en/stable/client.html#pure-functions-by-default
        #
        # Note:
        # - The task (myfunc(arg1, arg2)) is sent to a Dask worker.
        # - The worker computes the result and stores it in memory on that worker.
        # - The future object (on the client) is just a reference to that in-memory result.
        self.future = daskclient.submit(future_exec, executable, pure=True)

    def get_result(self):
        """Retrieves the result from the Dask future and merges CASA logs.

        Returns:
            The result of the task execution.

        Raises:
            Exception: If an error occurs during task execution or log merging.
        """
        task_result, tier0_executable = self.future.result()
        LOG.debug(
            'Received the task execution result (%s) from a worker for executing %s; content:',
            human_file_size(get_obj_size(task_result)),
            tier0_executable,
        )
        LOG.debug(pformat(task_result))

        self._merge_casa_commands(tier0_executable.logs)

        return task_result

    def _merge_casa_commands(self, logs):
        """Merges CASA command logs from a worker into the client-side log."""
        LOG.debug('return request logs: %s', logs)

        response_logs = logs
        client_cmdfile = response_logs.get('casa_commands')
        tier0_cmdfile = response_logs.get('casa_commands_tier0')

        if all(isinstance(cmdfile, str) and os.path.exists(cmdfile) for cmdfile in [client_cmdfile, tier0_cmdfile]):
            LOG.info('Merge %s into %s', tier0_cmdfile, client_cmdfile)
            with open(client_cmdfile, 'a', encoding='utf-8') as client:
                with open(tier0_cmdfile, 'r', encoding='utf-8') as tier0:
                    client.write(tier0.read())
                os.remove(tier0_cmdfile)
        else:
            LOG.debug('Cannot find Tier0 casa_commands.log; no merge needed')


def future_exec(tier0_executable):
    """Execute a pipeline task on a Dask worker.

    This function is called by Dask workers to execute pipeline tasks. It
    retrieves the executable from the Tier0Executable object and executes it.
    The result and the Tier0Executable object are then returned.

    Args:
        tier0_executable: The Tier0Executable object containing the executable.

    Returns:
        A tuple containing the result of the task execution and the
        Tier0Executable object.
    """
    executable = tier0_executable.get_executable()

    ret = executable()
    LOG.debug(
        'Buffering the execution return (%s) of %s',
        human_file_size(get_obj_size(ret)),
        tier0_executable,
    )

    return ret, tier0_executable


def is_dask_ready():
    """Check if Dask is ready for parallel task execution.

    Returns:
        bool: True if a Dask client is available and tier0futures is enabled,
              False otherwise.
    """
    return bool(daskclient) and tier0futures


def session_startup(casa_config: dict[str, str | None], loglevel: str | None = None) -> tuple[str, str]:
    """Initializes a CASA session with custom configurations and log settings.

    This function updates the casaconfig attributes, sets the CASA log file, and adjusts
    the log filtering level for casalogsink.

    Args:
        casa_config: A dictionary containing CASA configuration attributes. Keys are
                     attribute names (e.g., 'logfile', 'nworkers'), and values are the
                     desired settings. Values can be None, in which case the attribute
                     is not modified.
        loglevel: Optional pipeline log level string:
                        critical, error, warning, attention, info, debug, todo, trace.
                  If provided, the CASA log filter level is adjusted accordingly. If None,
                  casa loglevel defaults to 'INFO1'.

    Returns:
        A tuple containing:
            - The path to the CASA log file .
            - The CASA log filter level .
    """
    from casaconfig import config

    print('setlogfile', casa_config)

    # Update casaconfig attributes
    for key, value in casa_config.items():
        if hasattr(config, key) and value is not None:
            setattr(config, key, value)
            if key == 'logfile':
                pass

    # Initialize casatasks and get log file

    casalogfile = casatasks.casalog.logfile()

    # Adjust log filtering level
    casaloglevel = 'INFO1'
    if loglevel is not None:
        # map pipeline loglevel to casa loglevel, e.g. PL-attention is eqauivelentt to INFO1
        casaloglevel = infrastructure.logging.CASALogHandler.get_casa_priority(infrastructure.logging.LOGGING_LEVELS[loglevel])

    casatasks.casalog.filter(casaloglevel)

    return casalogfile, casaloglevel


def start_daskcluster(
    dask_config: dict[str, str | int | bool] | None = None,
) -> Client | None:
    """Start a Dask cluster based on configuration settings.

    This function initializes a Dask cluster, either locally or via SLURM,
    based on the configuration provided. It also sets up a Dask client,
    registers a cleanup function, and initializes worker processes.

    Args:
        dask_config: Optional dictionary containing Dask configuration settings.
                     If None, the default configuration from `config['pipeconfig']['dask']` is used.

    Returns:
        Client: A Dask client instance if the cluster is successfully started,
                None otherwise.
    """
    from dask.distributed import WorkerPlugin

    global daskclient, tier0futures

    class SetupPlugin(WorkerPlugin):
        """A Dask WorkerPlugin to run custom setup code on each worker."""

        def __init__(self, config=None):
            self.config = config or {}

        def setup(self, worker):
            last_logfile = casatasks.casalog.logfile()
            if self.config.get('logfile'):
                logfile = self.config.get('logfile')
                if logfile != last_logfile:
                    casatasks.casalog.setlogfile(logfile)
                    try:
                        os.remove(last_logfile)
                    except FileNotFoundError:
                        pass
            else:
                logfile = last_logfile
            logfile = casatasks.casalog.logfile()
            LOG.info(
                f'Initialized {worker.id} @ {worker.address} - {socket.gethostname()} - PID: {os.getpid()}\n    logfile: {logfile}'
            )

    class RemoteCondorCluster(HTCondorCluster):
        def _submit_job(self, script_filename):
            # Override to call condor_submit remotely
            cmd = ['ssh', 'localhost', 'condor_submit', script_filename]
            print('condor_submit command:', ' '.join(cmd))
            return subprocess.check_output(cmd).decode().strip()

    if not dask_available:
        LOG.warning('dask[distributed] not installed; skipping...')
        return

    dask_config_session = config['pipeconfig']['dask']
    LOG.debug('dask config (session): \n %s', pformat(dask_config_session))
    # `dask.config` is the module containing the global configuration state.
    # we merge the session config with the package built-in defaults and then consolidate into `dask.config`.
    dask.config.update_defaults(dask_config_session)
    if dask_config is not None:
        LOG.debug('dask config (user): \n %s', pformat(dask_config))
        dask.config.update_defaults(dask_config)

    # attached the exect client casaconfig issue which can be used to help initialze workers
    dask.config.update_defaults({'casaconfig': config['casaconfig']})

    dashboard_address: str | None = dask.config.get('dashboard_address', default=None)
    host: str | None = dask.config.get('host', default=None)
    n_workers: int | None = dask.config.get('n_workers', default=None)
    clustertype: str | None = dask.config.get('clustertype', default=None)

    if is_daskclient_allowed():
        cluster: LocalCluster | SLURMCluster | None = None

        path_to_resources_pkg = str(files('pipeline'))
        preload_script = os.path.join(path_to_resources_pkg, 'cleanup_mpi_environment.py')
        pythonpath_pkg = os.path.abspath(os.path.join(path_to_resources_pkg, os.pardir))

        if clustertype == 'local':
            with sanitized_env():
                if n_workers is None or n_workers <= 0:
                    n_workers = default_n_workers()
                preload = []
                if os.path.exists(preload_script):
                    LOG.info('Using dask worker preload script: %s', preload_script)
                    preload.extend([preload_script])
                cluster = LocalCluster(
                    n_workers=n_workers,
                    host=host,
                    dashboard_address=dashboard_address,
                    processes=True,  # True to avoid GIL; False to use threads but casatools is not fully thread-safe.
                    threads_per_worker=1,
                    scheduler_port=0,  # random free port to avoid conflicts
                    preload=preload,
                )
        elif clustertype == 'slurm':
            if n_workers is None or n_workers <= 0:
                n_workers = default_n_workers()
            with sanitized_env():
                worker_extra_args = []
                if os.path.exists(preload_script):
                    LOG.info('Using dask worker preload script: %s', preload_script)
                    worker_extra_args.extend(['--preload', preload_script])
                cluster = SLURMCluster(
                    n_workers=n_workers,
                    job_name=default_worker_name('jobqueue.slurm.name'),
                    name=default_worker_name('jobqueue.slurm.name'),
                    queue=dask.config.get('jobqueue.slurm.queue', default=default_slurm_queue()),
                    silence_logs='debug',
                    host=host,
                    scheduler_options={'dashboard_address': dashboard_address},
                    death_timeout='60s',
                    worker_extra_args=worker_extra_args,
                    job_script_prologue=[f'export PYTHONPATH={pythonpath_pkg}:$PYTHONPATH'],
                )
                LOG.debug('dask SLURMCluster job script: \n %s', pformat(cluster.job_script()))
        elif clustertype == 'htcondor':
            with sanitized_env():
                if n_workers is None or n_workers <= 0:
                    n_workers = default_n_workers()
                worker_extra_args = []
                if os.path.exists(preload_script):
                    LOG.info('Using dask worker preload script: %s', preload_script)
                    worker_extra_args.extend(['--preload', preload_script])
                cluster = RemoteCondorCluster(
                    n_workers=n_workers,
                    job_name=default_worker_name('jobqueue.htcondor.name'),
                    name=default_worker_name('jobqueue.htcondor.name'),
                    host=host,
                    scheduler_options={'dashboard_address': dashboard_address},
                    worker_extra_args=worker_extra_args,
                    job_script_prologue=[f'export PYTHONPATH={pythonpath_pkg}:$PYTHONPATH'],
                )
                LOG.debug('dask HTCondorCluster job script: \n %s', pformat(cluster.job_script()))
        else:
            LOG.warning('dask cluster specification (%s) not valid, skipping!', clustertype)
            return None

        QUEUE_WAIT = 60

        daskclient = Client(cluster)

        # Wait for all workers to become available.
        # This is necessary on HTCondor/SLURM clusters where workers are spawned asynchronously.
        start_time = datetime.datetime.now(datetime.timezone.utc)
        LOG.info(
            'starting %s workers at %s (waiting up to %d seconds)',
            n_workers,
            start_time.strftime('%Y-%m-%d %H:%M:%S'),
            QUEUE_WAIT,
        )

        daskclient.wait_for_workers(n_workers, timeout=QUEUE_WAIT)

        end_time = datetime.datetime.now(datetime.timezone.utc)
        elapsed = (end_time - start_time).total_seconds()
        LOG.info(
            'Acquired %d workers at %s (waited %.2f seconds)',
            n_workers,
            end_time.strftime('%Y-%m-%d %H:%M:%S'),
            elapsed,
        )

        # prefer using plugin which automatically applied to new workers joined by scaling
        plugin = SetupPlugin(config={'logfile': casatasks.casalog.logfile()})
        daskclient.register_plugin(plugin)

        tier0futures = bool(dask.config.get('tier0futures', default=None))

        atexit.register(stop_daskcluster)

    else:
        if daskclient is not None:
            LOG.warning('dask cluster already started.')

    if daskclient:
        LOG.info('Cluster dashboard: %s', daskclient.dashboard_link)
        LOG.info('   client:  %s', daskclient)
        LOG.info('   cluster: %s', daskclient.cluster)

        def get_status(dask_worker: Worker) -> tuple[str, str]:
            return dask_worker.status, dask_worker.id

        status: dict[str, tuple[str, str]] = daskclient.run(get_status)
        if status:
            LOG.info('worker status: \n %s', pformat(status))

    return daskclient


def exec_func(fn: Callable, *args, include_client: bool = True, **kwargs) -> None:
    """Execute the same function on both client and MPI server processes.

    This function enables synchronized execution across MPI infrastructure. It's particularly useful
    for setup tasks that need consistent state across all processes, such as changing the working directory.

    Args:
        fn: The function to execute.
        *args: Positional arguments to pass to the function.
        include_client: If True, the function is also executed on the client process.
        **kwargs: Keyword arguments to pass to the function.
    """
    # Execute on client if requested

    global daskclient, tier0futures

    if include_client:
        fn(*args, **kwargs)

    # Execute on all server processes in a blocking operation
    if daskclient is not None:
        daskclient.run(fn, *args, **kwargs)


def stop_daskcluster() -> None:
    """Stop the Dask cluster and close the client.

    This function shuts down the Dask cluster and closes the associated client.
    It should be registered with `atexit` to ensure proper cleanup.
    """
    global daskclient

    if not dask_available:
        LOG.warning('DASK not installed; skipping')
        return

    if daskclient is not None:
        LOG.info('closing the dask cluster/client at %s', str(daskclient.dashboard_link))
        if daskclient.status == 'running':
            daskclient.close()
        else:
            LOG.warning('client already closed')
        if daskclient.cluster.status.value == 'running':
            daskclient.cluster.close()
        else:
            LOG.warning('cluster already closed')
        daskclient = None

    return


def default_n_workers():
    """Dynamically determins the optimal default n_worker."""
    from dask.system import CPU_COUNT

    # cape the fallback local/jobqueue worker number at 4
    default_n_workers_local = min(CPU_COUNT, 4)

    # discover the cores assigned to slurm/htcondor jobs
    num_slurm_core = int(os.getenv('SLURM_NTASKS', 0))
    if num_slurm_core > 0:
        default_n_workers_local = num_slurm_core
    num_condor_core = int(os.getenv('PYTHON_CPU_COUNT', 0))
    if num_condor_core > 0:
        default_n_workers_local = num_condor_core

    return default_n_workers_local


def default_worker_name(key: str, default: str | None = None, override_with: str | None = None) -> str:
    """Dynamically generates a default worker name.

    Retrieves a base name from Dask configuration, falling back to 'dask-worker'
    if not found. If the SLURM_JOB_NAME environment variable is set, it is
    prepended to the base name for better identification in job schedulers.

    See Dask documentation for configuration details:
    https://docs.dask.org/en/latest/configuration.html

    Args:
        key: The Dask configuration key for the worker name.
        default: The default value to use if the key is not found in the config.
        override_with: A value to override any existing configuration.

    Returns:
        The constructed default worker name.
    """
    base_name = dask.config.get(key, default=default, override_with=override_with) or 'dask-worker'

    if slurm_job_name := os.getenv('SLURM_JOB_NAME'):
        return f'{slurm_job_name}-{base_name}'

    return base_name


def default_slurm_queue(default: str | None = None, override_with: str | None = None) -> str | None:
    """Dynamically determines the SLURM queue (partition) to use.

    It determines the queue by checking the following sources in order:
    1. The `override_with` parameter.
    2. The Dask configuration value for 'SLURM_JOB_PARTITION'.
    3. The 'SLURM_JOB_PARTITION' environment variable.
    4. The `default` parameter provided to this function.

    Args:
        default: The fallback value to use if no other source provides a queue.
        override_with: A value to explicitly override any configuration.

    Returns:
        The name of the SLURM queue, or None if not found in any source.
    """
    queue = dask.config.get('jobqueue.slurm.queue', default=default, override_with=override_with)

    if queue is None:
        queue = os.getenv('SLURM_JOB_PARTITION')

    return queue or default
