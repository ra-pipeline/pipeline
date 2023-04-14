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
import shutil

import almatasks
import casaplotms
import casatasks

from . import logging
from .jobrequest import JobRequest

LOG = logging.get_logger(__name__)


def applycal(*v, **k):
    return _get_job(casatasks.applycal, *v, **k)


def bandpass(*v, **k):
    return _get_job(casatasks.bandpass, *v, **k)


def calstat(*v, **k):
    return _get_job(casatasks.calstat, *v, **k)


def clearcal(*v, **k):
    return _get_job(casatasks.clearcal, *v, **k)


def delmod(*v, **k):
    return _get_job(casatasks.delmod, *v, **k)


def exportfits(*v, **k):
    return _get_job(casatasks.exportfits, *v, **k)


def gaincal(*v, **k):
    return _get_job(casatasks.gaincal, *v, **k)


def flagcmd(*v, **k):
    return _get_job(casatasks.flagcmd, *v, **k)


def flagdata(*v, **k):
    return _get_job(casatasks.flagdata, *v, **k)


def flagmanager(*v, **k):
    return _get_job(casatasks.flagmanager, *v, **k)


def fluxscale(*v, **k):
    return _get_job(casatasks.fluxscale, *v, **k)


def gencal(*v, **k):
    return _get_job(casatasks.gencal, *v, **k)


def hanningsmooth(*v, **k):
    return _get_job(casatasks.hanningsmooth, *v, **k)


def imdev(*v, **k):
    return _get_job(casatasks.imdev, *v, **k)


def imhead(*v, **k):
    return _get_job(casatasks.imhead, *v, **k)


def immath(*v, **k):
    return _get_job(casatasks.immath, *v, **k)


def immoments(*v, **k):
    return _get_job(casatasks.immoments, *v, **k)


def imregrid(*v, **k):
    return _get_job(casatasks.imregrid, *v, **k)

def imsmooth(*v, **k):
    return _get_job(casatasks.imsmooth, *v, **k)

def impbcor(*v, **k):
    return _get_job(casatasks.impbcor, *v, **k)


def importasdm(*v, **k):
    return _get_job(casatasks.importasdm, *v, **k)


def imstat(*v, **k):
    return _get_job(casatasks.imstat, *v, **k)


def imsubimage(*v, **k):
    return _get_job(casatasks.imsubimage, *v, **k)


def initweights(*v, **k):
    return _get_job(casatasks.initweights, *v, **k)


def listobs(*v, **k):
    return _get_job(casatasks.listobs, *v, **k)


def mstransform(*v, **k):
    return _get_job(casatasks.mstransform, *v, **k)


def partition(*v, **k):
    return _get_job(casatasks.partition, *v, **k)


def plotants(*v, **k):
    return _get_job(casatasks.plotants, *v, **k)


def plotbandpass(*v, **k):
    return _get_job(casatasks.plotbandpass, *v, **k)


def plotms(*v, **k):
    return _get_job(casaplotms.plotms, *v, **k)


def plotweather(*v, **k):
    return _get_job(casatasks.plotweather, *v, **k)


def polcal(*v, **k):
    return _get_job(casatasks.polcal, *v, **k)


def setjy(*v, **k):
    return _get_job(casatasks.setjy, *v, **k)


def split(*v, **k):
    return _get_job(casatasks.split, *v, **k)


def statwt(*v, **k):
    return _get_job(casatasks.statwt, *v, **k)


def tclean(*v, **k):
    return _get_job(casatasks.tclean, *v, **k)


def wvrgcal(*v, **k):
    return _get_job(almatasks.wvrgcal, *v, **k)


def visstat(*v, **k):
    return _get_job(casatasks.visstat, *v, **k)


def uvcontfit(*v, **k):
    # Note this is pipeline CASA style task not a CASA task
    import pipeline.hif.cli.uvcontfit as uvcontfit
    return _get_job(uvcontfit, *v, **k)


def sdatmcor(*v, **k) -> JobRequest:
    """Wrap casatasks.sdatmcor

    Returns:
        JobRequest instance
    """
    return _get_job(casatasks.sdatmcor, *v, **k)


def sdbaseline(*v, **k):
    return _get_job(casatasks.sdbaseline, *v, **k)


def sdcal(*v, **k):
    return _get_job(casatasks.sdcal, *v, **k)


def sdimaging(*v, **k):
    return _get_job(casatasks.sdimaging, *v, **k)


def tsdimaging(*v, **k):
    return _get_job(casatasks.tsdimaging, *v, **k)


def copyfile(*v, **k):
    return _get_job(shutil.copyfile, *v, **k)


def copytree(*v, **k):
    return _get_job(shutil.copytree, *v, **k)


def rmtree(*v, **k):
    return _get_job(shutil.rmtree, *v, **k)


def move(*v, **k):
    return _get_job(shutil.move, *v, **k)


def _get_job(task, *v, **k):
    return JobRequest(task, *v, **k)
