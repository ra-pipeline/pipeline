"""Pipeline software package
"""
import atexit
import http.server
import os
import pathlib
import pkg_resources
import threading
import webbrowser

from . import domain
from . import environment
from . import infrastructure

from .infrastructure import Pipeline, Context

from . import h
from . import hif
from . import hifa
from . import hsd
from . import hifv
from . import hsdn

from .domain import measures
from casashell.private.stack_manip import find_frame
from casatasks import casalog

# Modify filter to get INFO1 message which the pipeline
# treats as ATTENTION level.
casalog.filter('INFO1')

LOG = infrastructure.get_logger(__name__)

__pipeline_documentation_weblink_alma__ = "http://almascience.org/documents-and-tools/pipeline-documentation-archive"


WEBLOG_LOCK = threading.Lock()
HTTP_SERVER = None


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

def initcli(user_globals=None):
    LOG.info('Initializing cli...')
    if user_globals is None:
        my_globals = find_frame()
    else:
        my_globals = user_globals

    for package in ['h', 'hif', 'hifa', 'hifas', 'hifv', 'hsd', 'hsdn']:
        abs_cli_package = 'pipeline.{package}.cli'.format(package=package)
        try:
            # Check the existence of the generated __init__ modules
            path_to_cli_init = pkg_resources.resource_filename(abs_cli_package, '__init__.py'.format(package))
        except ImportError as e:
            LOG.debug('Import error: {!s}'.format(e))
            LOG.info('No tasks found for package: {!s}'.format(package))
        else:
            # Instantiate the pipeline tasks for the given package
            exec('from {} import *'.format(abs_cli_package), my_globals)
            LOG.info('Loaded Pipeline commands from package: {!s}'.format(package))

revision = environment.pipeline_revision


def log_host_environment():
    LOG.info('Pipeline version {!s} running on {!s}'.format(environment.pipeline_revision, environment.hostname))
    try:
        host_summary = '{!s} memory, {!s} x {!s} running {!s}'.format(
            measures.FileSize(environment.memory_size, measures.FileSizeUnits.BYTES),
            environment.logical_cpu_cores,
            environment.cpu_type,
            environment.host_distribution)

        LOG.info('Host environment: {!s}'.format(host_summary))
        LOG.debug('Dependency details:')
        for dep_name, dep_detail in environment.dependency_details.items():
            if dep_detail is None:
                LOG.debug('  {!s} : {!s}'.format(dep_name, 'not found'))
            else:
                LOG.debug('  {!s} = {!s} : {!s}'.format(
                    dep_name, dep_detail['version'], dep_detail['path']))
    except NotImplemented:
        pass


log_host_environment()

# FINALLY import executeppr. Do so as late as possible in pipeline module
# because executeppr make use of a part of pipeline module.
from .infrastructure import executeppr