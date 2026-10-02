"""
This module contains a wrapper function for every CASA task. The signature of
each methods exactly matches that of the CASA task it mirrors. However, rather
than executing the task directly when these methods are called,
CASATaskJobGenerator returns a JobRequest for every invocation; these jobs
then be examined and executed at a later date.

The CASA task implementations are located at run-time and proxies for each
task attached to this class at runtime. The name and signature of each
method will match those of the tasks in the CASA environment when this
module was imported.
"""
import functools
import importlib.util
import inspect
import shutil
import subprocess
import sys

# NOTE: ``casaplotms`` and ``casatasks`` previously lived at module top.
# Importing them eagerly triggers CASA C++ session startup (``casa-*.log``
# creation, etc.) which we want to defer until an actual pipeline run
# (see :func:`pipeline.initialize`).  This module is loaded as part of
# ``pipeline.infrastructure``, so we install lightweight lazy proxies via
# ``importlib.util.LazyLoader`` that defer module execution until first
# attribute access.  The per-task wrappers below use
# ``casatasks.<task>`` / ``casaplotms.<task>`` at call time, so the import
# is deferred until a JobRequest is actually generated.

from . import logging
from .jobrequest import JobRequest
from .mpirunner import call_with_mpi

LOG = logging.get_logger(__name__)

__all__ = []


def _lazy_import(name: str):
    """Return a lazily-loaded module using :class:`importlib.util.LazyLoader`.

    The module's code is not executed until the first attribute access.
    If the module is already present in ``sys.modules`` (e.g. imported earlier
    by another code path), the existing module object is returned as-is so we
    never overwrite a fully-initialised module with an empty lazy shell.
    """
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.find_spec(name)
    if spec is None:
        raise ModuleNotFoundError(f'No module named {name!r}')
    loader = importlib.util.LazyLoader(spec.loader)
    spec.loader = loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


casatasks = _lazy_import('casatasks')
casaplotms = _lazy_import('casaplotms')


def register_task(func):
    """Register a JobRequest generator function."""
    __all__.append(func.__name__)
    return func


@register_task
def applycal(*v, **k) -> JobRequest:
    return JobRequest(casatasks.applycal, *v, **k)


@register_task
def bandpass(*v, **k) -> JobRequest:
    return JobRequest(casatasks.bandpass, *v, **k)


@register_task
def calstat(*v, **k) -> JobRequest:
    return JobRequest(casatasks.calstat, *v, **k)


@register_task
def clearcal(*v, **k) -> JobRequest:
    return JobRequest(casatasks.clearcal, *v, **k)


@register_task
def concat(*v, **k) -> JobRequest:
    return JobRequest(casatasks.concat, *v, **k)


@register_task
def delmod(*v, **k) -> JobRequest:
    return JobRequest(casatasks.delmod, *v, **k)


@register_task
def exportfits(*v, **k) -> JobRequest:
    return JobRequest(casatasks.exportfits, *v, **k)


@register_task
def gaincal(*v, **k) -> JobRequest:
    return JobRequest(casatasks.gaincal, *v, **k)


@register_task
def flagcmd(*v, **k) -> JobRequest:
    return JobRequest(casatasks.flagcmd, *v, **k)


@register_task
def flagdata(*v, **k) -> JobRequest:
    return JobRequest(casatasks.flagdata, *v, **k)


@register_task
def flagmanager(*v, **k) -> JobRequest:
    return JobRequest(casatasks.flagmanager, *v, **k)


@register_task
def fluxscale(*v, **k) -> JobRequest:
    return JobRequest(casatasks.fluxscale, *v, **k)


@register_task
def gencal(*v, **k) -> JobRequest:
    return JobRequest(casatasks.gencal, *v, **k)


def getantposalma(*v, **k) -> JobRequest:
    return JobRequest(casatasks.getantposalma, *v, **k)


@register_task
def getjyperkalma(*v, **k) -> JobRequest:
    return JobRequest(casatasks.getjyperkalma, *v, **k)


@register_task
def hanningsmooth(*v, **k) -> JobRequest:
    return JobRequest(casatasks.hanningsmooth, *v, **k)


@register_task
def imdev(*v, **k) -> JobRequest:
    return JobRequest(casatasks.imdev, *v, **k)


@register_task
def imval(*v, **k) -> JobRequest:
    return JobRequest(casatasks.imval, *v, **k)


@register_task
def imfit(*v, **k) -> JobRequest:
    return JobRequest(casatasks.imfit, *v, **k)


@register_task
def imhead(*v, **k) -> JobRequest:
    return JobRequest(casatasks.imhead, *v, **k)


@register_task
def immath(*v, **k) -> JobRequest:
    return JobRequest(casatasks.immath, *v, **k)


@register_task
def immoments(*v, **k) -> JobRequest:
    return JobRequest(casatasks.immoments, *v, **k)


@register_task
def imregrid(*v, **k) -> JobRequest:
    return JobRequest(casatasks.imregrid, *v, **k)


@register_task
def imsmooth(*v, **k) -> JobRequest:
    return JobRequest(casatasks.imsmooth, *v, **k)


@register_task
def impbcor(*v, **k) -> JobRequest:
    return JobRequest(casatasks.impbcor, *v, **k)


@register_task
def importasdm(*v, **k) -> JobRequest:
    return JobRequest(casatasks.importasdm, *v, **k)


@register_task
def imstat(*v, **k) -> JobRequest:
    return JobRequest(casatasks.imstat, *v, **k)


@register_task
def imsubimage(*v, **k) -> JobRequest:
    return JobRequest(casatasks.imsubimage, *v, **k)


@register_task
def initweights(*v, **k) -> JobRequest:
    return JobRequest(casatasks.initweights, *v, **k)


@register_task
def listobs(*v, **k) -> JobRequest:
    return JobRequest(casatasks.listobs, *v, **k)


@register_task
def mstransform(*v, **k) -> JobRequest:
    return JobRequest(casatasks.mstransform, *v, **k)


@register_task
def partition(*v, **k) -> JobRequest:
    return JobRequest(casatasks.partition, *v, **k)


@register_task
def plotants(*v, **k) -> JobRequest:
    return JobRequest(casatasks.plotants, *v, **k)


@register_task
def plotbandpass(*v, **k) -> JobRequest:
    return JobRequest(casatasks.plotbandpass, *v, **k)


def xvfb_plotms(self, *args, **kwargs):
    cmd = []
    xvfb_run = shutil.which('xvfb-run')
    python = sys.executable
    cmd = [xvfb_run, '-a', python, '-c']
    all_args = [f"{value!r}" for value in args] + [f"{name}={value!r}" for name, value in kwargs.items()]
    py_cmds = ['from casaplotms import plotms', 'import numpy as np', 'plotms({})'.format(', '.join(all_args))]
    py_cmd = '; '.join(py_cmds)
    cmd.append(f'"{py_cmd}"')
    cmd = ' '.join(cmd)
    try:
        LOG.debug(f'subprocess-cmd: {cmd}')
        ret = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode().strip()
        LOG.debug(f'subprocess-ret: {ret}')
    except (FileNotFoundError, subprocess.CalledProcessError) as ex:
        ret = "error"
    return ret

xvfb_plotms.__name__ = 'plotms'
# NOTE: copying ``casaplotms.plotms.{__doc__,__signature__,...}`` onto the
# wrapper used to happen here at module load.  That eagerly imports
# ``casaplotms`` (and transitively ``casatasks``/``casatools``), which we
# now avoid.  Instead, the metadata is copied on demand by
# :func:`_init_casa_signatures`, which is invoked from
# :func:`pipeline.initialize`.


@register_task
def plotms(*v, **k) -> JobRequest:
    xvfb_subprocess = False
    if xvfb_subprocess:
        return JobRequest(xvfb_plotms, *v, **k)
    else:
        return JobRequest(casaplotms.plotms, *v, **k)


@register_task
def plotweather(*v, **k) -> JobRequest:
    return JobRequest(casatasks.plotweather, *v, **k)


@register_task
def polcal(*v, **k) -> JobRequest:
    return JobRequest(casatasks.polcal, *v, **k)


@register_task
def polfromgain(*v, **k) -> JobRequest:
    return JobRequest(casatasks.polfromgain, *v, **k)


@register_task
def setjy(*v, **k) -> JobRequest:
    return JobRequest(casatasks.setjy, *v, **k)


@register_task
def split(*v, **k) -> JobRequest:
    return JobRequest(casatasks.split, *v, **k)


@register_task
def statwt(*v, **k) -> JobRequest:
    return JobRequest(casatasks.statwt, *v, **k)


def _with_tclean_signature(fn):
    """Tag ``fn`` for deferred tclean-signature substitution.

    Computing the signature requires importing ``casatasks``, so we only
    record the function here; the real signature is wired up later by
    :func:`_init_casa_signatures` (called from :func:`pipeline.initialize`).
    """
    _DEFERRED_TCLEAN_SIGS.append(fn)
    return fn


_DEFERRED_TCLEAN_SIGS: list = []
_CASA_SIGNATURES_INITIALIZED = False


def _init_casa_signatures() -> None:
    """Apply deferred CASA-derived metadata to wrapper functions.

    Idempotent.  Imports ``casatasks`` and ``casaplotms`` (triggering CASA
    startup as a side effect), so it must only be called once a real
    pipeline run has been requested.
    """
    global _CASA_SIGNATURES_INITIALIZED
    if _CASA_SIGNATURES_INITIALIZED:
        return
    _CASA_SIGNATURES_INITIALIZED = True

    # plotms wrapper metadata (was previously eager at module load).
    try:
        plotms_call = casaplotms.plotms.__call__
        xvfb_plotms.__doc__ = casaplotms.plotms.__doc__
        xvfb_plotms.__wrapped__ = plotms_call
        xvfb_plotms.__signature__ = inspect.signature(plotms_call)
        xvfb_plotms.__defaults__ = plotms_call.__defaults__
        xvfb_plotms.__kwdefaults__ = plotms_call.__kwdefaults__
    except Exception:  # pragma: no cover - best-effort metadata copy
        LOG.debug('Could not copy casaplotms.plotms metadata', exc_info=True)

    # tclean signature substitution (was previously eager at module load).
    for fn in _DEFERRED_TCLEAN_SIGS:
        try:
            params = [
                p for p in inspect.signature(casatasks.tclean).parameters.values()
                if p.name != 'parallel'
            ]
            params.append(
                inspect.Parameter(
                    'parallel',
                    inspect.Parameter.KEYWORD_ONLY,
                    default=False,
                    annotation='bool | dict[str, int]',
                )
            )
            fn.__signature__ = inspect.Signature(parameters=params)
        except (TypeError, ValueError):  # pragma: no cover
            LOG.debug('Could not derive tclean signature for %s', fn, exc_info=True)


@_with_tclean_signature
def _tclean(*args, parallel=False, **kwargs):
    """Execute casatasks.tclean with transparent serial/MPI dispatch.

    Args:
        *args: Positional arguments forwarded to tclean.
        parallel: False runs serially in-process. True or a dict ``{'nproc': N}``
            spawns an MPI subprocess (or delegates to the existing MPI client).
        **kwargs: Keyword arguments forwarded to tclean.
    """
    return call_with_mpi(casatasks.tclean, *args, parallel=parallel, **kwargs)


@register_task
def tclean(*v, **k) -> JobRequest:
    return JobRequest(_tclean, *v, **k)


@register_task
def uvcontsub(*v, **k) -> JobRequest:
    return JobRequest(casatasks.uvcontsub, *v, **k)


@register_task
def wvrgcal(*v, **k) -> JobRequest:
    return JobRequest(casatasks.wvrgcal, *v, **k)


@register_task
def visstat(*v, **k) -> JobRequest:
    return JobRequest(casatasks.visstat, *v, **k)


@register_task
def rerefant(*v, **k) -> JobRequest:
    return JobRequest(casatasks.rerefant, *v, **k)


@register_task
def sdatmcor(*v, **k) -> JobRequest:
    """Wrap casatasks.sdatmcor

    Returns:
        JobRequest instance
    """
    return JobRequest(casatasks.sdatmcor, *v, **k)


@register_task
def sdbaseline(*v, **k) -> JobRequest:
    return JobRequest(casatasks.sdbaseline, *v, **k)


@register_task
def sdcal(*v, **k) -> JobRequest:
    return JobRequest(casatasks.sdcal, *v, **k)


@register_task
def tsdimaging(*v, **k) -> JobRequest:
    return JobRequest(casatasks.tsdimaging, *v, **k)


@register_task
def copyfile(*v, **k) -> JobRequest:
    return JobRequest(shutil.copyfile, *v, **k)


@register_task
def copytree(*v, **k) -> JobRequest:
    return JobRequest(shutil.copytree, *v, **k)


@register_task
def rmtree(*v, **k) -> JobRequest:
    return JobRequest(shutil.rmtree, *v, **k)


@register_task
def move(*v, **k) -> JobRequest:
    return JobRequest(shutil.move, *v, **k)


class CasaTasks:
    """A class to represent a collection of JobRequest-wrapped callables from CASA or Python modules.

    CasaTasks wraps frequently-used CASA tasks and Python functions into individual class methods that
    can create and execute JobRequests on-the-fly. Then their calls will be properly
    logged and recorded by the Pipeline logging framework:
        * casacalls-*.txt records all JobRequest executions.
        * casa_commands.log records JobRequest executed by the PipelineTask Executor instances.

    The "immediate-execution" interface offered by this class could help adapt extern Python
    scripts/module into Pipeline with minimal changes.

    Example 1):

        from casatasks import tclean

            can be replaced by:

        from pipeline.infrastructure.casa_tasks import casa_tasks
        tclean=casa_tasks.tclean

    Example 2):

        from pipeline.infrastructure.casa_tasks import CasaTasks
        ct = CasaTasks()
        ct.listobs(vis='my.ms')
        help(ct.listobs) # this behaves like casatasks.listobs
    """

    def __init__(self, executor=None):
        self._tasklist = __all__
        self._executor = executor
        for _fn in self._tasklist:
            setattr(self, _fn, self._logged_fn(getattr(sys.modules[__name__], _fn)))

    def _logged_fn(self, fn):
        """Get the wrapper function that can immediately create and execute JobRequest of a callable."""
        if self._executor is None:
            # Executions will be logged in casacalls-.txt
            @functools.wraps(fn)
            def func(*args, **kwargs):
                return fn(*args, **kwargs).execute()
            return func
        else:
            # Executions will be logged in both casacalls-.txt and casa-command.txt
            @functools.wraps(fn)
            def func(*args, **kwargs):
                return self._executor.execute(fn(*args, **kwargs))
            return func


# add an instance of executor-free CasaTasks under the module namespace
casa_tasks = CasaTasks()
