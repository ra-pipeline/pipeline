import abc
import importlib.util
import os
import pickle
import pprint
import tempfile
from inspect import signature

from pipeline.infrastructure import daskhelpers, exceptions, logging
from pipeline.infrastructure.utils import gen_hash, get_obj_size, human_file_size

casampi_spec = importlib.util.find_spec('casampi')
casalith_spec = importlib.util.find_spec('casalith')

if casampi_spec is None:
    # casampi not available
    class DummyMPIEnvironment:
        is_mpi_enabled = False
        is_mpi_client = False

    MPIEnvironment = DummyMPIEnvironment()
    # stub MPICommandClient too to keep IDE happy
    MPICommandClient = object
else:
    from casampi.MPICommandClient import MPICommandClient
    from casampi.MPIEnvironment import MPIEnvironment

# global variable for toggling MPI usage
USE_MPI = True
ENABLE_TIER0_PLOTMS = True
BUFFER_LIMIT = 100*1024*1024  # 100 MiB

LOG = logging.get_logger(__name__)


class AsyncTask(object):
    def __init__(self, executable):
        """
        Create a new AsyncTask.

        The referenced task will be immediately queued for asynchronous
        execution on an MPI server upon creation of an object.

        :param executable: the TierN executable class to run
        :return: an AsyncTask object

        Note that tier0_executable must be picklable.
        """
        LOG.debug(
            'pushing tier0executable {} from the MPI client: {}'.format(
                executable, human_file_size(get_obj_size(executable))
            )
        )
        self.__pid = mpiclient.push_command_request(
            'pipeline.infrastructure.mpihelpers.mpiexec(tier0_executable)',
            block=False,
            parameters={'tier0_executable': executable},
        )

    def get_result(self):
        """
        Get the result from the executed task.

        This method blocks until execution of the asynchronous task is
        complete.

        :return: the Result returned by the executing task
        :rtype: pipeline.infrastructure.api.Result
        :except PipelineException: if the task did not complete successfully.
        """
        response = mpiclient.get_command_response(self.__pid, block=True, verbose=True)
        LOG.debug(
            'Received the response (%s) from MPIserver-%s for command_request_id=%s executing %s; content:',
            human_file_size(get_obj_size(response)),
            response[0]['server'],
            response[0]['id'],
            response[0]['parameters']['tier0_executable'],
        )
        LOG.debug(pprint.pformat(response))

        response = response[0]
        if response['successful']:
            self._merge_casa_commands(response)
            ret, ret_file = response['ret']
            if ret_file is not None:
                LOG.debug('Retrieve the execution return of %s from %s',
                          response['parameters']['tier0_executable'], ret_file)
                with open(ret_file, 'rb') as pickle_file:
                    ret = pickle.load(pickle_file)
                os.unlink(ret_file)
            return ret
        else:
            err_msg = 'Failure executing job on MPI server {}, with traceback\n {}'.format(
                response['server'], response['traceback']
            )
            raise exceptions.PipelineException(err_msg)

    def _merge_casa_commands(self, response):
        """Merge the "casa_commands" log entries from a Tier0 AsyncTask into the client-side main logfile.

        This method is expected to run on the MPI client when retrieving the AsyncTask result.
        It will delete the individual tier0 casa command files created by MPI servers.

        Args:
            response:   the response of a MPI command request, returned from mpiclient.get_command_response().
                        Expected to be a dictionary containing the command execution details from the server-side.

        Note on the "response" dictionary structure:
            The following keys of "response" are used in this method:

                response['parameters']['tier0_executable']: a copy of the input tier0_executable object, with modifications from the MPI server
                response['server']: the MPI server rank
                response['id']: the command request id (same as self.__pid)
                response['command_start_time']: command start time
                response['command_stop_time']: command stop time

            The rest keys include:
                response['ret']: return from the server-side constructed PipelineTask/JobRequest executable
                response['command']: the input command request string
        """

        LOG.debug(
            'Received a successful response from MPIserver-{server} for command_request_id={id}'.format(**response)
        )
        LOG.debug('return request logs: {}'.format(response['parameters']['tier0_executable'].logs))

        response_logs = response['parameters']['tier0_executable'].logs
        client_cmdfile = response_logs.get('casa_commands')
        tier0_cmdfile = response_logs.get('casa_commands_tier0')

        if all(isinstance(cmdfile, str) and os.path.exists(cmdfile) for cmdfile in [client_cmdfile, tier0_cmdfile]):
            LOG.info(f'Merge {tier0_cmdfile} into {client_cmdfile}')
            with open(client_cmdfile, 'a') as client:
                with open(tier0_cmdfile, 'r') as tier0:
                    client.write('# MPIserver:           {}\n'.format(response['server']))
                    client.write(
                        '# Duration:            {:.2f}s\n'.format(
                            response['command_stop_time'] - response['command_start_time']
                        )
                    )
                    client.write('# CommandRequest ID:   {}\n'.format(response['id']))
                    client.write(tier0.read())
                os.remove(tier0_cmdfile)
        else:
            LOG.debug(
                'Cannot find Tier0 casa_commands.log for command_request_id={id}; no merge needed'.format(**response)
            )


class SyncTask(object):
    def __init__(self, task, executor=None):
        """
        Create a new SyncTask object.

        Creation of a SyncTask does not result in immediate execution of the
        given task. Execution is delayed until the result is requested.

        :param task: a pipeline task or JobRequest
        :param executor: a pipeline Executor (optional)
        :return: a SyncTask object
        :rtype: SyncTask
        """
        self.__task = task
        self.__executor = executor

    def get_result(self):
        """
        Get the result from the executed task.

        This method starts execution of the wrapped task and blocks until
        execution is complete.

        :return: the Result returned by the executing task
        :rtype: pipeline.infrastructure.api.Result
        :except pipeline.infrastructure.exceptions.PipelineException: if the
        task did not complete successfully.
        """
        try:
            if self.__executor:
                return self.__executor.execute(self.__task)
            else:
                if not callable(self.__task):
                    # for JobRequest or PipelineTask
                    return self.__task.execute()
                else:
                    # for FunctionCall
                    return self.__task()
        except Exception as e:
            import traceback

            err_msg = 'Failure executing job by an exception {} with the following traceback\n {}'.format(
                e.__class__.__name__, traceback.format_exc()
            )
            raise exceptions.PipelineException(err_msg)


class Executable(object):
    def __init__(self):
        self.logs = {}

    @abc.abstractmethod
    def get_executable(self):
        """Create and return an executable object, intended to run on the MPI server."""
        raise NotImplementedError


class Tier0PipelineTask(Executable):
    def __init__(self, task_cls, task_args, context_path):
        """
        Create a new Tier0PipelineTask representing a pipeline task to be
        executed on an MPI server.

        :param task_cls: the class of the pipeline task to execute
        :param task_args: any arguments to passed to the task Inputs
        :param context_path: the filesystem path to the pickled Context
        """
        super().__init__()
        self.__task_cls = task_cls
        self.__context_path = context_path

        # Assume that the path to the context pickle is safe to write the task
        # argument pickle too
        context_dir = os.path.dirname(context_path)
        # Use the tempfile module to generate a unique temporary filename,
        # which we use as the output path for our pickled context
        tmpfile = tempfile.NamedTemporaryFile(suffix='.task_args', dir=context_dir, delete=True)
        self.__task_args_path = tmpfile.name
        tmpfile.close()

        # write task args object to pickle
        with open(self.__task_args_path, 'wb') as pickle_file:
            LOG.info('Saving task arguments to {!s}'.format(self.__task_args_path))
            pickle.dump(task_args, pickle_file, protocol=-1)

    def get_executable(self):
        """Create and return a Pipeline task executable, intended to run on the MPI server.

        The construction is based on the content of Tier0PipelineTask instance pushed from the client.
        """
        try:
            with open(self.__context_path, 'rb') as context_file:
                context = pickle.load(context_file)

            self.logs['casa_commands'] = os.path.join(context.report_dir, context.logs['casa_commands'])
            tmpfile = tempfile.NamedTemporaryFile(suffix='.casa_commands.log', dir='', delete=True)
            tmpfile.close()
            self.logs['casa_commands_tier0'] = tmpfile.name

            # modify the context copy used on the MPI server
            context.logs['casa_commands'] = self.logs['casa_commands_tier0']

            with open(self.__task_args_path, 'rb') as task_args_file:
                task_args = pickle.load(task_args_file)

            inputs = self.__task_cls.Inputs(context, **task_args)
            task = self.__task_cls(inputs)

            return lambda: task.execute()

        finally:
            if self.__task_args_path and os.path.exists(self.__task_args_path):
                os.unlink(self.__task_args_path)

    def __str__(self):
        return 'Tier0PipelineTask(%s, %s, %s)' % (self.__task_cls, self.__task_args_path, self.__context_path)


class Tier0JobRequest(Executable):
    def __init__(self, creator_fn, job_args, executor=None):
        """
        Create a new Tier0JobRequest representing a JobRequest to be executed
        on an MPI server.

        :param creator_fn: the class of the CASA task to execute
        :param job_args: any arguments to passed to the task Inputs
        """
        super().__init__()
        self.__creator_fn = creator_fn
        self.__job_args = job_args
        if executor is None:
            self.__executor = None
        else:
            # Exclude the context reference inside the executor shallow copy before pushing from the client
            # to reduce the risk of reaching the MPI buffer size limit (150MiB as of CASA ver6.4.1,
            # see PIPE-13656/PIPE-1337).
            self.__executor = executor.copy(exclude_context=True)

    def get_executable(self):
        """Create and return a JobRequest executable, intended to run on the MPI server.

        The construction is based on the content of Tier0JobRequest instance pushed from the client.
        """
        job_request = self.__creator_fn(**self.__job_args)
        if self.__executor is None:
            return lambda: job_request.execute()
        else:
            # modify the executor copy used on the MPI server
            tmpfile = tempfile.NamedTemporaryFile(suffix='.casa_commands.log', dir='', delete=True)
            tmpfile.close()
            self.logs['casa_commands_tier0'] = tmpfile.name
            self.logs['casa_commands'] = self.__executor.cmdfile
            self.__executor.cmdfile = self.logs['casa_commands_tier0']
            return lambda: self.__executor.execute(job_request, merge=False)

    def __str__(self):
        return 'Tier0JobRequest({}, {})'.format(self.__creator_fn, self.__job_args)


class Tier0FunctionCall(Executable):
    def __init__(self, fn, *args, executor=None, use_pickle=False, **kwargs):
        """
        Create a new Tier0FunctionCall for a function to be executed on an MPI
        server. The functions and arguments must be picklable objects.
        """
        super().__init__()
        self.__fn = fn
        if use_pickle:
            # pass function arguments via local pickle I/O to workround the casampi bsend buffer
            # size restriction (CAS-13656).
            tmpfile = tempfile.NamedTemporaryFile(suffix='.func_args', dir='', delete=True)
            tmpfile.close()
            self.__func_args_path = tmpfile.name
            # write task args object to pickle
            with open(self.__func_args_path, 'wb') as pickle_file:
                LOG.info('Saving task arguments to %s', self.__func_args_path)
                pickle.dump((args, kwargs), pickle_file, protocol=-1)
        else:
            # pass function arguments directly via MPI messaging
            self.__func_args_path = None
            self.__args = args
            self.__kwargs = kwargs

        if executor is None:
            self.__executor = None
        else:
            # Exclude the context reference inside the executor shallow copy before pushing from the client
            # to reduce the risk of reaching the MPI buffer size limit (150MiB as of CASA ver6.4.1,
            # see PIPE-13656/PIPE-1337).
            self.__executor = executor.copy(exclude_context=True)

        # the following code is used to get a nice repr format
        arg_names = list(signature(fn).parameters)
        arg_count = len(arg_names)

        def format_arg_value(arg_val):
            arg, val = arg_val
            return '%s=%r' % (arg, val)

        self.__positional = list(map(format_arg_value, zip(arg_names, args)))
        self.__nameless = list(map(repr, args[arg_count:]))
        self.__keyword = list(map(format_arg_value, kwargs.items()))

    def get_executable(self):
        if self.__func_args_path is not None:
            with open(self.__func_args_path, 'rb') as func_args_file:
                args, kwargs = pickle.load(func_args_file)
        else:
            args = self.__args
            kwargs = self.__kwargs

        if self.__func_args_path is not None and os.path.exists(self.__func_args_path):
            os.unlink(self.__func_args_path)

        if self.__executor is None:
            return lambda: self.__fn(*args, **kwargs)
        else:
            tmpfile = tempfile.NamedTemporaryFile(suffix='.casa_commands.log', dir='', delete=True)
            tmpfile.close()
            self.logs['casa_commands_tier0'] = tmpfile.name
            self.logs['casa_commands'] = self.__executor.cmdfile
            self.__executor.cmdfile = self.logs['casa_commands_tier0']
            return lambda: self.__fn(*args, executor=self.__executor, **kwargs)

    def __repr__(self):
        args = self.__positional + self.__nameless + self.__keyword
        args.insert(0, self.__fn.__name__)
        return 'Tier0FunctionCall({!s})'.format(', '.join(args))


def mpiexec(tier0_executable):
    """
    Execute a pipeline task.

    This function is used to recreate and execute tasks/jobrequests on cluster nodes.

    :param tier0_executable: the Tier0Executable task to execute
    :return: the Result returned by executing the task
    """
    LOG.trace('rank%s@%s: mpiexec(%s)', MPIEnvironment.mpi_processor_rank, MPIEnvironment.hostname, tier0_executable)

    executable = tier0_executable.get_executable()
    LOG.info('Executing %s on rank%s@%s', tier0_executable, MPIEnvironment.mpi_processor_rank, MPIEnvironment.hostname)

    ret, ret_file = executable(), None
    ret_size = get_obj_size(ret)  # in Bytes
    if ret_size > BUFFER_LIMIT:
        tmpfile = tempfile.NamedTemporaryFile(suffix='.context',
                                              dir='',
                                              delete=True)
        tmpfile.close()
        LOG.debug('Saving the execution return from %s to %s due to its size of %s execeeding the MPI Buffer limit %s restricted by Pipeline',
                  tier0_executable, tmpfile.name, human_file_size(ret_size), human_file_size(BUFFER_LIMIT))
        with open(tmpfile.name, 'wb') as pickle_file:
            pickle.dump(ret, pickle_file, protocol=-1)
        ret, ret_file = None, os.path.abspath(tmpfile.name)
    else:
        LOG.debug('Buffering the execution return (%s) from %s', human_file_size(ret_size), tier0_executable)

    return ret, ret_file


def is_mpi_ready():
    # to allow MPI jobs, the executing pipeline code must be running as the
    # client node on an MPI cluster, with the MPICommandClient ready and the
    # no user override specified.
    return all([
        USE_MPI,  # User has not disabled MPI globally
        MPIEnvironment.is_mpi_enabled,  # running on MPI cluster
        MPIEnvironment.is_mpi_client,  # running as MPI client
        mpiclient,
    ])  # MPICommandClient ready


def is_mpi_server() -> bool:
    """Check if the current process is running on an MPI server.

    Determines whether this process is running as an MPI server by checking both that MPI is enabled
    and that this process is not specifically an MPI client.

    Returns:
        True if the process is an MPI server, False otherwise.
    """
    return MPIEnvironment.is_mpi_enabled and not MPIEnvironment.is_mpi_client


def exec_func(fn: callable, *args, include_client: bool = True, **kwargs) -> None:
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
    if include_client:
        fn(*args, **kwargs)

    # Prepare executable for server processes
    executable = Tier0FunctionCall(fn, *args, **kwargs)

    # Execute on all server processes if MPI is available
    if mpiclient is not None and mpi_server_list is not None:
        mpiclient.push_command_request(
            'pipeline.infrastructure.mpihelpers.mpiexec(tier0_executable)',
            block=True,
            target_server=mpi_server_list,
            parameters={'tier0_executable': executable},
        )


def _splitall(path):
    allparts = []
    while True:
        parts = os.path.split(path)
        if parts[0] == path:  # sentinel for absolute paths
            allparts.insert(0, parts[0])
            break
        elif parts[1] == path:  # sentinel for relative paths
            allparts.insert(0, parts[1])
            break
        else:
            path = parts[0]
            allparts.insert(0, parts[1])
    return allparts


def parse_mpi_input_parameter(input_arg):
    lowercase = str(input_arg).lower()
    if lowercase == 'automatic':
        return is_mpi_ready()
    elif lowercase == 'true':
        return True
    elif lowercase == 'false':
        return False
    else:
        raise ValueError('Arg must be one of true, false or automatic. Got %s' % input_arg)


def parse_parallel_input_parameter(input_arg):
    lowercase = str(input_arg).lower()
    if lowercase == 'automatic':
        return is_mpi_ready() or daskhelpers.is_dask_ready()
    elif lowercase == 'true':
        return True
    elif lowercase == 'false':
        return False
    else:
        raise ValueError('Arg must be one of true, false or automatic. Got %s' % input_arg)


mpiclient = None
mpi_server_list = None

if MPIEnvironment.is_mpi_enabled:
    try:
        if MPIEnvironment.is_mpi_client:
            __client = MPICommandClient()
            # PIPE-1757: use the 'redirect' mode to forward tier0 messages to console stdout.
            #   * checkout different log_mode options in casampi.private.server_run.run()
            #   * also see the log_mode example here:
            #       https://casadocs.readthedocs.io/en/latest/notebooks/parallel-processing.html#Advanced:-Interface-Framework
            __client.set_log_mode('redirect')
            __client.start_services()

            mpi_server_list = MPIEnvironment.mpi_server_rank_list()

            # get path to pipeline code and import it on the cluster nodes
            __client.push_command_request('import sys', block=True, target_server=mpi_server_list)
            __codepath = os.path.join(*_splitall(__file__)[0:-3])
            __client.push_command_request(
                'sys.path.insert(0, %r)' % __codepath, block=True, target_server=mpi_server_list
            )

            __client.push_command_request('import pipeline', block=True, target_server=mpi_server_list)
            # __client.push_command_request('pipeline.infrastructure.logging.set_logging_level(level="trace")', block=True, target_server=mpi_server_list)

            mpiclient = __client
            LOG.info('MPI environment detected. Pipeline operating in cluster mode.')
    except:
        LOG.warning('Problem initialising MPI. Pipeline falling back to single host mode.')
        mpiclient = None
else:
    if casalith_spec:
        LOG.info('Environment is not MPI enabled. Pipeline operating in single host mode')
    mpiclient = None


class TaskQueue:
    """A interface class that manages/executes tier0 PipelineTask, JobRquests, or FunctionaCalls in parallel.

    TaskQueue provides an API similar to multiprocessing.Pool, but use the casampi FIFO queue underneath.
    Note that the AsynTask-based queue (tier0) will only happen when the instance is run from the
    client node of an MPI cluster. Otherwise, the queue will just be executed in synchronous mode, essentially
    a loop over an iterator.

    Example 1:

        from pipeline.infrastructure.mpihelpers import TaskQueue
        q = TaskQueue()
        q.add_functioncall(test, 9, 8) # test is a function taking two arguments.
        for i in range(4):
            q.add_jobrequest(casa_tasks.plotms, {'vis': 'eb3_targets.04287+1801.spw16_18_20_22_24_26_28_30.selfcal.ms',
                            'xaxis': 'uvdist', 'yaxis': 'amp', 'coloraxis': 'spw', 'plotfile': 'test'+str(i)+'.png',
                            'overwrite': True})
        results = q.get_results()

    Example 2:

        from pipeline.infrastructure.mpihelpers import TaskQueue
        from pipeline.infrastructure.utils.math import round_up
        # A note on object serialization: The mapped object must be serializable (pickleable)
        # and resolvable by the server process, as it is passed through our MPI4py wrapper.
        # For reliable execution, define the function at the module level within the
        # Pipeline package or before the casampi queue is created.
        with TaskQueue() as tq:
            tq.map(round_up,[(1.1,),(1.2,),(1.2,),(1.5,),(1.6,)])
        results = tq.get_results()
        print(results)

    """

    def __init__(self, parallel=True, executor=None, unique=False):
        self.__queue = []
        self.__hash = []
        self.__returned = []        
        self.__results = []
        self.__executor = executor
        self.__mpi_server_list = mpi_server_list
        self.__is_async_ready = daskhelpers.is_dask_ready() or is_mpi_ready()
        self.__parallel_wanted = parallel
        self.__async = self.__parallel_wanted and self.__is_async_ready
        self.__unique = unique

        LOG.info('TaskQueue initialized: ')
        LOG.info('    MPI server list: %s', self.__mpi_server_list)
        LOG.info('    Dask client:     %s', daskhelpers.daskclient)
        LOG.info('    is_async  :      %s', self.__async)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.get_results(clear=False)
        if exc_type:
            LOG.error('Error in TaskQueue: %s', exc_val)
        else:
            LOG.info('TaskQueue completed successfully')

    def __call__(self):
        return self.get_results(clear=False)

    def done(self, clear=False):
        return self.get_results(clear=clear)

    def is_async(self):
        """Return True if the TaskQueue is running in parallel mode."""
        return self.__async

    def get_results(self, clear=False):
        """get all queue results in a block fashion."""
        for idx, task in enumerate(self.__queue):
            if not self.__returned[idx]:
                self.__results[idx] = task.get_result()
                self.__returned[idx] = True

        if clear:
            self.__queue = []
            self.__hash = []
            self.__returned = []
            results = self.__results[:]

            self.__queue.clear()
            self.__hash.clear()
            self.__returned.clear()
            self.__results.clear()
            return results
        else:
            return self.__results

    def map(self, fn, iterable):
        if not hasattr(iterable, '__len__'):
            iterable = list(iterable)

        for args in iterable:
            self.add_functioncall(fn, *args)

    def _register_task(self, task, task_hash):
        self.__queue.append(task)
        self.__hash.append(task_hash)
        self.__returned.append(False)
        self.__results.append(None)            

    def add_jobrequest(self, fn, job_args, executor=None):
        """Add a jobequest into the queue.

        fn should be a jobrequest generator function, which returns a JobRequest object.
        e.g.
            fn = casa_tasks.imdev
            job_args = {'imagename': 'myimage.fits'}
        """
        task_hash = gen_hash((fn, job_args))
        if self.__unique and task_hash in self.__hash:
            LOG.debug('Skipping duplicated JobRequest - fn: %s, job_args: %s', fn, job_args)
            return
                
        if executor is None:
            executor = self.__executor

        # try different parallelization arrangement:
        #   dask/futures -> casampi -> serial

        if self.__parallel_wanted and daskhelpers.is_dask_ready():
            executable = Tier0JobRequest(fn, job_args, executor=executor)
            task = daskhelpers.FutureTask(executable)
        elif self.__parallel_wanted and is_mpi_ready():
            executable = Tier0JobRequest(fn, job_args, executor=executor)
            task = AsyncTask(executable)
        else:
            task = SyncTask(fn(**job_args), executor)

        self._register_task(task, task_hash)

    def add_functioncall(self, fn, *args, use_pickle=False, **kwargs):
        """Add a function call into the queue."""
        task_hash = gen_hash((fn, args, kwargs))
        if self.__unique and task_hash in self.__hash:
            LOG.debug('Skipping duplicated JobRequest - fn: %s, args: %s, kwargs: %s', fn.__name__, args, kwargs)
            return        

        # try different parallelization arrangement:
        #   dask/futures -> casampi -> serial        
        if self.__parallel_wanted and daskhelpers.is_dask_ready():
            executable = Tier0FunctionCall(fn, *args, use_pickle=use_pickle, **kwargs)
            task = daskhelpers.FutureTask(executable)
        elif self.__parallel_wanted and is_mpi_ready():
            executable = Tier0FunctionCall(fn, *args, use_pickle=use_pickle, **kwargs)
            task = AsyncTask(executable)
        else:
            task = SyncTask(lambda: fn(*args, **kwargs))

        self._register_task(task, task_hash)

    def add_pipelinetask(self, task_cls, task_args, context, executor=None):
        """Add a PipelineTask into the queue."""
        task_hash = gen_hash((task_cls, task_args, context))
        if self.__unique and task_hash in self.__hash:
            LOG.debug(
                'Skipping duplicated PipelineTask - task_cls: %s, task_args: %s, content: %s',
                task_cls,
                task_args,
                context,
            )
            return
                
        if executor is None:
            executor = self.__executor

        # try different parallelization arrangement:
        #   dask/futures -> casampi -> serial

        if self.__parallel_wanted and daskhelpers.is_dask_ready():
            tmpfile = tempfile.NamedTemporaryFile(suffix='.context', dir=context.output_dir, delete=True)
            tmpfile.close()
            context_path = tmpfile.name
            context.save(context_path)
            executable = Tier0PipelineTask(task_cls, task_args, context_path)
            task = daskhelpers.FutureTask(executable)

        elif self.__parallel_wanted and is_mpi_ready():
            tmpfile = tempfile.NamedTemporaryFile(suffix='.context', dir=context.output_dir, delete=True)
            tmpfile.close()
            context_path = tmpfile.name
            context.save(context_path)
            executable = Tier0PipelineTask(task_cls, task_args, context_path)
            task = AsyncTask(executable)
        else:
            inputs = task_cls.Inputs(context, **task_args)
            task = task_cls(inputs)
            task = SyncTask(task, executor)

        self._register_task(task, task_hash)
