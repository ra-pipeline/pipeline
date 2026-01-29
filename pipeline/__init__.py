"""Pipeline software package."""
import atexit
import decimal
import http.server
import importlib
import importlib.util
import inspect
import os
import pathlib
import threading
import webbrowser
from typing import Any, Optional

import matplotlib
from astropy.utils.iers import conf as iers_conf

# import `pipeline.config` early to allow modifications of
# `casaconfig.config` attributes before importing casatasks/casatools
from . import config, domain, environment, infrastructure

__version__ = revision = environment.pipeline_revision


# PIPE-2195: Extend auto_max_age to reduce the frequency of IERS Bulletin-A table auto-updates.
# This change increases the maximum age of predictive data before auto-downloading is triggered.
# Note that the default auto_max_age value is 30 days as of Astropy ver 6.0.1:
# https://docs.astropy.org/en/stable/utils/iers.html
iers_conf.auto_max_age = 180

# set the loglevel of Pipeline Python loggers during the package initialization
LOG = infrastructure.logging.get_logger(__name__)

pipe_loglevel = config.config['pipeconfig'].get('loglevel', 'info')
infrastructure.logging.set_logging_level(level=pipe_loglevel)

__pipeline_documentation_weblink_alma__ = "http://almascience.org/documents-and-tools/pipeline-documentation-archive"


WEBLOG_LOCK = threading.Lock()
HTTP_SERVER = None
XVFB_DISPLAY = None


def show_weblog(index_path='',
                handler_class=http.server.SimpleHTTPRequestHandler,
                server_class=http.server.HTTPServer,
                bind='127.0.0.1'):
    """
    Locate the most recent web log and serve it via a HTTP server running on
    127.0.0.1 using a random port 30000-32768.

    The function arguments are not exposed in the CASA CLI interface, but are
    made available in case that becomes necessary.

    TODO:
    Ideally we'd serve just the html directory, but that breaks the weblog for
    reasons I don't have time to investigate right now. See
    https://gist.github.com/diegosorrilha/812787c01b65fde6dec870ab97212abd ,
    which is easily convertible to Python 3. These classes can be passed in as
    handler_class and server_class arguments.
    """
    global HTTP_SERVER

    if index_path in (None, ''):
        # find all t1-1.html files
        index_files = {p.name: p for p in pathlib.Path('.').rglob('t1-1.html')}

        # No web log, bail.
        if len(index_files) == 0:
            LOG.info('No weblog detected')
            return

        # sort files by date, newest first
        by_date = sorted(pathlib.Path('.').rglob('t1-1.html'),
                         key=os.path.getmtime,
                         reverse=True)
        LOG.info('Found weblogs at:%s', ''.join([f'\n\t{p}' for p in by_date]))

        if len(index_files) > 1:
            LOG.info('Multiple web logs detected. Selecting most recent version')

        index_path = by_date[0]

    if isinstance(index_path, str):
        index_path = pathlib.Path(index_path)

    with WEBLOG_LOCK:
        if HTTP_SERVER is None:
            httpd = None
            # find first available port in range 30000-32768
            port = 30000
            while httpd is None and port < 32768:
                server_address = (bind, port)
                try:
                    httpd = server_class(server_address, handler_class)
                except OSError as e:
                    # Errno 48 = port already taken
                    if e.errno == 48:
                        LOG.debug('Port %s already in use. Selecting a different port...', port)
                        port += 1
                    else:
                        raise

            if httpd is None:
                LOG.error('Could not start web server. All ports in use')
                return

            sa = httpd.socket.getsockname()
            serve_message = 'Serving web log on {host} port {port} (http://{host}:{port}/) ...'
            LOG.info(serve_message.format(host=sa[0], port=sa[1]))

            thread = threading.Thread(target=httpd.serve_forever)
            thread.daemon = True
            thread.start()

            HTTP_SERVER = httpd

        else:
            sa = HTTP_SERVER.socket.getsockname()
            LOG.info('Using existing HTTP server at %s port %s ...', sa[0], sa[1])

    atexit.register(stop_weblog)

    sa = HTTP_SERVER.socket.getsockname()
    url = 'http://{}:{}/{}'.format(sa[0], sa[1], index_path)
    LOG.info('Opening {}'.format(url))

    # Get controller for Firefox if possible, otherwise use whatever the
    # webbrowser module determines to be best
    try:
        browser = webbrowser.get('firefox')
    except webbrowser.Error:
        browser = webbrowser.get()
    browser.open(url)


def stop_weblog():
    global HTTP_SERVER
    with WEBLOG_LOCK:

        if HTTP_SERVER is not None:
            sa = HTTP_SERVER.socket.getsockname()

            HTTP_SERVER.shutdown()

            serve_message = "HTTP server on {host} port {port} shut down"
            LOG.info(serve_message.format(host=sa[0], port=sa[1]))
            HTTP_SERVER = None


def _find_caller_globals() -> dict[str, Any]:
    """Finds the globals dictionary of the top-level IPython calling frame.

    This function walks up the call stack to find the frame corresponding to the
    interactive IPython session. It identifies this frame by checking for the
    presence of the `get_ipython` function in its global namespace, which is a
    reliable indicator of an interactive IPython environment (e.g., Jupyter).

    This implementation is adapted from the `find_frame()` function in
    `casashell/src/scripts/stack_manip`.

    Returns:
        The globals dictionary of the IPython interactive session frame, or an
        empty dictionary if no such frame is found.
    """
    frame = inspect.currentframe()
    while frame:
        # 'get_ipython' is a sentinel for the main interactive session's global scope.
        if 'get_ipython' in frame.f_globals:
            return frame.f_globals
        frame = frame.f_back
    return {}


def _import_module_contents(module_name: str, target_globals: dict[str, Any]) -> bool:
    """Import all public contents from a module into the target globals dictionary.
    
    Args:
        module_name: The full name of the module to import from
        target_globals: The globals dictionary to import into
        
    Returns:
        bool: True if import was successful, False otherwise
    """
    try:
        # Check if the module exists
        if importlib.util.find_spec(module_name) is None:
            LOG.info(f"Module {module_name} does not exist")
            return False

        # Import the module
        module = importlib.import_module(module_name)

        # Get the list of public names to import
        names_to_import = getattr(module, '__all__', [name for name in dir(module) if not name.startswith('_')])

        # Import each name into the target globals
        for name in names_to_import:
            target_globals[name] = getattr(module, name)

        return True

    except ImportError as e:
        LOG.error('Import error for %s: %s', module_name, e)
        return False


def initcli(user_globals: Optional[dict[str, Any]] = None) -> None:
    """Initialize CLI by importing pipeline commands from various packages.
    
    Args:
        user_globals: Optional globals dictionary to import into.
                     If None, the caller's globals will be used.
    """
    LOG.info('Initializing cli...')

    # Get the globals dictionary to populate
    globals_dict = user_globals if user_globals is not None else _find_caller_globals()

    # List of sub-packages to import from
    packages = ['h', 'hif', 'hifa', 'hifv', 'hsd', 'hsdn']

    for package in packages:
        cli_package = f"pipeline.{package}.cli"
        if _import_module_contents(cli_package, globals_dict):
            LOG.info("Loaded Pipeline commands from package: %s", package)
        else:
            LOG.info("No tasks found for package: %s", package)


def log_host_environment():
    env = environment.ENVIRONMENT
    LOG.info('Pipeline version {!s} running on {!s}'.format(revision, env.hostname))

    ram = domain.measures.FileSize(env.ram, domain.measures.FileSizeUnits.BYTES)
    try:
        swap = domain.measures.FileSize(env.swap, domain.measures.FileSizeUnits.BYTES)
    except decimal.InvalidOperation:
        swap = 'unknown'

    if env.cgroup_mem_limit != 'N/A':
        cgroup_mem_limit = domain.measures.FileSize(env.cgroup_mem_limit, domain.measures.FileSizeUnits.BYTES)
    else:
        cgroup_mem_limit = 'N/A'

    try:
        LOG.info(
            'Host environment:\n'
            f'\tCPU: {env.cpu_type} '
            f'(physical cores: {env.physical_cpu_cores}, logical cores: {env.logical_cpu_cores})\n'
            f'\tMemory: {ram} RAM, {swap} swap\n'
            f'\tOS: {env.host_distribution}\n'
            f'\tcgroup limits: {env.cgroup_cpu_bandwidth} of {env.cgroup_num_cpus} CPU cores, '
            f'memory limits={cgroup_mem_limit}\n'
            f'\tulimit limits: CPU time={env.ulimit_cpu}, memory={env.ulimit_mem}, files={env.ulimit_files}'
        )

        LOG.info(
            'Environment as detected by CASA:\n'
            f'\tCPUs reported by CASA: {env.casa_cores} cores, '
            f'max {env.casa_threads} OpenMP thread{"s" if env.casa_threads > 1 else ""}\n'
            f'\tAvailable memory: {domain.measures.FileSize(env.casa_memory, domain.measures.FileSizeUnits.BYTES)}'
        )

        if infrastructure.daskhelpers.is_daskclient_allowed():
            LOG.debug('Dependency details:')
            for dep_name, dep_detail in environment.dependency_details.items():
                if dep_detail is None:
                    LOG.debug('  {!s} : {!s}'.format(dep_name, 'not found'))
                else:
                    LOG.debug('  {!s} = {!s} : {!s}'.format(
                        dep_name, dep_detail['version'], dep_detail['path']))
    except NotImplemented:
        pass


def start_xvfb():
    global XVFB_DISPLAY
    try:
        from pyvirtualdisplay import Display
        current_process_pid = os.getpid()
        if XVFB_DISPLAY is not None and XVFB_DISPLAY.is_alive():
            LOG.warning('A Xvfb Server is already attached to the current process: %s', current_process_pid)
        else:
            XVFB_DISPLAY = Display(visible=0, size=(2048, 2048))
            XVFB_DISPLAY.start()
            LOG.debug("disp.start() executed successfully from PID: %s", current_process_pid)
            atexit.register(stop_xvfb)
    except ImportError:
        LOG.warning('Required package pyvirtualdisplay is not installed, '
                    'which is required to creating virtual displays for '
                    'GUI applications in headless environments')


def stop_xvfb():
    global XVFB_DISPLAY
    if XVFB_DISPLAY is not None and XVFB_DISPLAY.is_alive():
        XVFB_DISPLAY.stop()


def inherit_docstring_and_type_hints():
    """Complement docstring and type hints of CLI tasks.

    This function complements docstring of CLI tasks, and
    adds type hints for parameters and return value for them.

    Type hint for return value is taken from Task.prepare or
    Task.execute methods where Task is underlying implementation
    class. Other information, docstring and type hits for
    parameters, are taken from Task.Inputs class.

    For docstring, parameter description (Args section) is
    merged into existing docstring. To make this function work
    properly, all docstring must be in google style.
    """
    import pipeline.cli as cli
    import pipeline.infrastructure.doctools as doctools

    task_registry = infrastructure.task_registry
    for task_name, cli_task in cli.__dict__.items():
        try:
            task_class = task_registry.get_pipeline_class_for_task(task_name)
        except KeyError:
            continue

        doctools.inherit_docstring(task_class, cli_task)
        doctools.inherit_annotations(task_class, cli_task)


inherit_docstring_and_type_hints()

if infrastructure.daskhelpers.is_daskclient_allowed():
    log_host_environment()


if config.config['pipeconfig'].get('xvfb', False) or infrastructure.daskhelpers.is_dask_worker():
    # Either xvfb is explicitly requested, or any Dask worker process, which should stay headless.
    if os.getenv('XVFB_RUN') != '1' and not infrastructure.mpihelpers.is_mpi_server():
        # Avoid starting another Xvfb instance if already running under xvfb-run.
        # Avoid starting Xvfb in the MPI server process to prevent multiple nested instances.
        # By design, casampi already starts Xvfb for all MPI worker processes.
        start_xvfb()

# Use the `agg` backend for any process.
# Tkinter (which Matplotlib often uses by default) are not thread-safe.
matplotlib.use('agg')
LOG.debug('Matplotlib backend set to %s', matplotlib.get_backend())

if config.config['pipeconfig']['dask']['autostart'] and infrastructure.daskhelpers.is_daskclient_allowed():
    # Automatically start a Dask cluster if allowed.
    # However, this is generally discouraged because it can cause:
    #   - Accidental recursive process creation
    #   - Unintended Dask configurations in interactive sessions
    #   - Slower import times due to Dask and distributed initialization
    #   - Limited flexibility in cluster configuration
    #     (we rely on configuration files and environment variables)
    #   - Increased difficulty in testing
    #   - etc.
    # Therefore, it is recommended to start the Dask cluster explicitly
    # within the main program when needed.
    infrastructure.daskhelpers.start_daskcluster()
