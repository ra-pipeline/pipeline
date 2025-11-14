"""
Classes of Regression Framework.

The regression module contains base classes and plugin registry for the
pipeline's regression test value extractor framework.

This module contains two classes:

    * RegressionExtractor: the base class for extractor plug-ins
    * RegressionExtractorRegistry: the registry and manager for plug-ins

Tasks provide and register their own extractors that each extends
RegressionExtractor. These extractor plug-ins analyse the results of a task,
extracting pertinent values and writing them to a dict. The keys of the
output dict identify the value; the values of the dict are the extracted
values themselves.

The pipeline QA framework is activated whenever a Results instance is accepted
into the pipeline context. The pipeline QA framework operates by calling
is_handler_for(result) on each registered QAPlugin, passing it the the accepted
Results instance for inspection. QAPlugins that claim to handle the Result are
given the Result for processing. In this step, the QA framework calls
QAPlugin.handle(context, result), the method overridden by the task-specific
QAPlugin.
"""
import abc
import collections
import glob
import os.path
import random
import re
from collections import OrderedDict

from pipeline.hifv.tasks.finalcals.applycals import Applycals
from pipeline.hifv.tasks.finalcals.finalcals import Finalcals, FinalcalsResults
from pipeline.hifv.tasks.flagging.checkflag import Checkflag, CheckflagResults
from pipeline.hifv.tasks.flagging.flagdetervla import FlagDeterVLA, FlagDeterVLAResults
from pipeline.hifv.tasks.flagging.targetflag import Targetflag, TargetflagResults
from pipeline.hifv.tasks.fluxscale.fluxboot import Fluxboot, FluxbootResults
from pipeline.hifv.tasks.fluxscale.solint import Solint, SolintResults
from pipeline.hifv.tasks.importdata.importdata import VLAImportData, VLAImportDataResults
from pipeline.hifv.tasks.priorcals import Priorcals
from pipeline.hifv.tasks.priorcals.resultobjects import PriorcalsResults
from pipeline.hifv.tasks.semiFinalBPdcals.semiFinalBPdcals import semiFinalBPdcals, semiFinalBPdcalsResults
from pipeline.hifv.tasks.setmodel.vlasetjy import VLASetjy
from pipeline.hifv.tasks.statwt.statwt import Statwt, StatwtResults
from pipeline.hifv.tasks.testBPdcals.testBPdcals import testBPdcals, testBPdcalsResults
from pipeline.hsd.tasks.applycal.applycal import SDApplycal
from pipeline.hsd.tasks.baselineflag.baselineflag import SDBLFlag, SDBLFlagResults
from pipeline.hsd.tasks.imaging.imaging import SDImaging
from pipeline.hsd.tasks.imaging.resultobjects import SDImagingResults
from pipeline.hsd.tasks.restoredata.restoredata import SDRestoreData, SDRestoreDataResults
from pipeline.hsdn.tasks.restoredata.restoredata import NRORestoreData, NRORestoreDataResults
from pipeline.infrastructure import logging
from pipeline.infrastructure.basetask import Results, ResultsList, StandardTaskTemplate
from pipeline.infrastructure.launcher import Context
from pipeline.infrastructure.taskregistry import task_registry

LOG = logging.get_logger(__name__)


class RegressionExtractor(object, metaclass=abc.ABCMeta):
    """The mandatory base class for all regression test result extractors."""

    # the Results class this handler is expected to handle
    result_cls = None
    # if result_cls is a list, the type of classes it is expected to contain
    child_cls = None
    # the task class that generated the results, or None if it should handle
    # all results of this type regardless of which task generated it
    generating_task = None

    def is_handler_for(self, result: Results | ResultsList) -> bool:
        """
        Return True if this RegressionExtractor can process the Result.

        :param result: the task Result to inspect
        :return: True if the Result can be processed
        """
        # if the result is not a list or the expected results class,
        # return False
        if not isinstance(result, self.result_cls):
            return False

        # this is the expected class and we weren't expecting any
        # children, so we should be able to handle the result
        if self.child_cls is None and (self.generating_task is None
                                       or result.task is self.generating_task
                                       or ( hasattr(self.generating_task, 'Task') and result.task is self.generating_task.Task) ):
            return True

        try:
            if all([isinstance(r, self.child_cls) and
                    (self.generating_task is None or r.task is self.generating_task)
                    for r in result]):
                return True
            return False
        except:
            # catch case when result does not have a task attribute
            return False

    @abc.abstractmethod
    def handle(self, result:Results) -> OrderedDict:
        """
        [Abstract] Extract values for testing.

        This method should return a dict of

        {'applycal.new_flags.science': 0.34,
         'applycal.new_flags.bandpass': 0.53}

        :param result:
        :return:
        """
        raise NotImplemented


class RegressionExtractorRegistry(object):
    """
    The registry and manager of the regression result extractor framework.

    The responsibility of the RegressionResultRegistry is to pass Results to
    RegressionExtractors that can handle them.
    """

    def __init__(self):
        """Constractor of this class."""
        self.__plugins_loaded = False
        self.__handlers = []

    def add_handler(self, handler: RegressionExtractor) -> None:
        """
        Push RegressionExtractor into handlers list __handler.

        Args:
            handler: RegressionExtractor
        """
        task = handler.generating_task.__name__ if handler.generating_task else 'all'
        child_name = ''
        if hasattr(handler.child_cls, '__name__'):
            child_name = handler.child_cls.__name__
        elif isinstance(handler.child_cls, collections.abc.Iterable):
            child_name = str([x.__name__ for x in handler.child_cls])
        container = 's of %s' % child_name
        s = '{}{} results generated by {} tasks'.format(handler.result_cls.__name__, container, task)
        LOG.debug('Registering {} as new regression result handler for {}'.format(handler.__class__.__name__, s))
        self.__handlers.append(handler)


    def handle(self, result: Results | ResultsList) -> OrderedDict:
        """
        Extract values from corresponding Extractor object of Result object.

        Args:
            result: Results or ResultsList[Results]
        Return:
            Dict of extracted values
        """
        if not self.__plugins_loaded:
            for plugin_class in get_all_subclasses( RegressionExtractor ):
                self.add_handler(plugin_class())
            self.__plugins_loaded = True

        # this is the list which will contain extracted values tuples
        extracted = {}

        # Process leaf results first
        if isinstance(result, collections.abc.Iterable):
            for r in result:
                d = self.handle(r)
                extracted = union(extracted, d)

        # process the group-level results.
        for handler in self.__handlers:
            if handler.is_handler_for(result):
                LOG.debug('{} extracting regression results for {}'.format(handler.__class__.__name__,
                                                                           result.__class__.__name__))
                d = handler.handle(result)
                extracted = union(extracted, d)

        return extracted


def union(d1: dict, d2: dict) -> OrderedDict:
    """
    Return the union of two dicts.
    
    It raises an exception if duplicate keys are detected in the input dicts.

    Args:
        d1, d2: dict for unioning
    Returns:
        OrderedDict unioned two dict
    """
    intersection = key_intersection(d1, d2)
    if intersection:
        raise ValueError('Regression keys are duplicated: {}'.format(intersection))
    # dict keys and values should be strings, so ok to shallow copy
    # OrderedDict is used to store results in processing order.
    u = OrderedDict(d1)
    u.update(d2)
    return u


def key_intersection(d1: dict, d2: dict) -> set:
    """
    Compare keys of two dicts, returning duplicate keys.

    Args:
        d1, d2: dict for comparison
    Returns:
        duplicated keys dict
    """
    d1_keys = set(d1.keys())
    d2_keys = set(d2.keys())
    return d1_keys.intersection(d2_keys)


# default RegressionExtractorRegistry initialization
registry = RegressionExtractorRegistry()


def get_prefix(result:Results, task:StandardTaskTemplate) -> str:
    """
    Return a string used to prefix string of rows of result text.

    Args:
        result: Result object
        task: Task object
    
    Returns:
        prefix string
    """
    # A value of result.inputs['vis'] of some classes (ex: SDImagingResults) is a list object
    res_vis = result.inputs['vis'][0] if isinstance(result.inputs['vis'], list) else result.inputs['vis']
    vis, _ = os.path.splitext(os.path.basename(res_vis))
    casa_task = task_registry.get_casa_task(task)
    prefix = 's{}.{}.{}'.format(result.stage_number, casa_task, vis)
    return prefix


def extract_regression_results(context: Context) -> list[str]:
    """
    Extract regression result and return logs.

    Args:
        context: Context object
    
    Returns:
        String list for logging
    """
    unified = OrderedDict()
    for results_proxy in context.results:
        results = results_proxy.read()
        unified = union(unified, registry.handle(results))

    # return unified
    return ['{}={}'.format(k, v)for k, v in unified.items()]


def missing_directories(context: Context, include_rawdata: bool = False) -> list[str]:
    """
    Check whether working/ and and products/ are present, and rawdata/ if
    applicable (see include_rawdata argument.)

    Args:
        context: Context object
        include_rawdata: whether to include the rawdata directory in the check
    Returns:
        True if all directories are present, False otherwise
    """
    missing = []

    if include_rawdata:
        directories = ['rawdata', 'working', 'products']
    else:
        directories = ['working', 'products']

    for directory in directories:
        if not os.path.exists(os.path.join(context.output_dir, '..', directory)):
            missing.append(directory)

    return missing


def manifest_present(context: Context) -> bool:
    """
    Check if pipeline_manifest.xml is present under products/

    Args:
        context: Context object

    Returns:
        True if *pipeline_manifest.xml is present, False otherwise
    """
    manifest_path = os.path.join(context.products_dir, '*pipeline_manifest.xml')
    manifest_files = glob.glob(manifest_path)
    return len(manifest_files) > 0


def errorexit_present(context: Context) -> bool:
    """
    Check if any errorexit-*.txt files are present in the working directory

    Args:
        context: Context object

    Returns:
        True if any errorexit-*.txt is present, False otherwise
    """
    errorexit_path = os.path.join(context.products_dir, 'errorexit-*.xml')
    errorexit_files = glob.glob(errorexit_path)
    return len(errorexit_files) > 0


def is_iterable(obj):
    try:
        iter(obj)
        return True
    except TypeError:
        return False


# def negative_qa(context: Context) -> bool:
#     all_results = [r.read() for r in context.results]
#     for result_list in all_results:
#         if is_iterable(result_list):
#             for result in result_list:
#                 for qa_score in result.qa.pool:
#                     if qa_score.score < 0:
#                         return False
#         else:
#             for qa_score in result.qa.pool:
#                 if qa_score.score < 0:
#                     return False
#     return True


def get_all_subclasses(cls: RegressionExtractor) -> list[RegressionExtractor]:
    """
    Get all subclasses from RegressionExtractor classes tree recursively.

    Args:
        cls: root class of subclasses
    
    Returns:
        list of RegressionExtractor
    """
    subclasses = cls.__subclasses__()
    for subclass in subclasses:
        subclasses += get_all_subclasses(subclass)
    return subclasses


# TODO enable runtime comparisons?
