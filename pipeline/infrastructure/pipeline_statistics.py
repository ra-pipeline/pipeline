import abc
import collections
import copy
import datetime
import enum
import re

from typing import Dict, List, Set, Union

import numpy as np
from pipeline import environment
from pipeline.domain import measures
from pipeline.h.tasks.applycal.applycal import ApplycalResults
from pipeline.hif.tasks.applycal.ifapplycal import IFApplycal
from pipeline.h.tasks.common.commonfluxresults import FluxCalibrationResults
from pipeline.hifa.tasks.flagging.flagdeteralma import FlagDeterALMAResults
from pipeline.hifa.tasks.fluxscale.gcorfluxscale import GcorFluxscale
from pipeline.hifa.tasks.gfluxscaleflag import Gfluxscaleflag
from pipeline.hifa.tasks.gfluxscaleflag.resultobjects import GfluxscaleflagResults
from pipeline.infrastructure.basetask import Results, ResultsList
from pipeline.infrastructure.launcher import Context
import pipeline.infrastructure.renderer.htmlrenderer as htmlrenderer
from pipeline.domain.datatype import DataType
from pipeline.infrastructure.launcher import Context
from pipeline.domain.measurementset import MeasurementSet
from pipeline.domain.measures import FluxDensityUnits
from pipeline.h.tasks.common import flagging_renderer_utils as flagutils
from pipeline.infrastructure.renderer import regression
import pipeline.infrastructure.utils as utils

# Additional imports for VLA and SD extractors
from pipeline.hsd.tasks.applycal.applycal import SDApplycal
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
from pipeline.hsd.tasks.baselineflag.baselineflag import SDBLFlag, SDBLFlagResults
from pipeline.hsd.tasks.imaging.imaging import SDImaging
from pipeline.hsd.tasks.imaging.resultobjects import SDImagingResults
from pipeline.hsd.tasks.restoredata.restoredata import SDRestoreData, SDRestoreDataResults
from pipeline.hsdn.tasks.restoredata.restoredata import NRORestoreData, NRORestoreDataResults

from . import logging

LOG = logging.get_logger(__name__)


# useful helper functions:
def determine_import_program(context: Context, ms: MeasurementSet) -> str:
    """
    Returns the name of the import program used to create the MS
    """
    if ms.antenna_array.name == 'ALMA':
        if utils.contains_single_dish(context):
            return "hsd_importdata"
        else:
            return "hifa_importdata"
    elif ms.antenna_array.name == "VLA":
        return "hifv_importdata"
    else:
        return "unknown"


def strip_html(text: str):
    pattern = re.compile('<.*?>')
    clean_text = re.sub(pattern, '', text)
    return clean_text


class PipelineStatisticLevel(enum.Enum):
    """
    An enum to specify which "level" of information an individual pipeline statistic applies to:
    SPW, EB, SOURCE, or MOUS.
    """
    MOUS = enum.auto()
    EB = enum.auto()
    SPW = enum.auto()
    SOURCE = enum.auto()


class PipelineStatistic:
    """A single unit of pipeline statistics information.

    Attributes:
        name: The name of this pipeline statistic
        value: The value for this pipeline statistic
        longdesc: A long description of the value
        origin: The stage that this value was calculated or populated in (Optional)
        units: The units associated with the value (Optional)
        level: A PipelineStatisticLevel that specifies whether this value applies to a MOUS, EB, or SPW
    """
    def __init__(self, name: str, value: Union[str, int, float, List, Dict, Set, np.int64, np.ndarray],
                 longdesc: str, origin: str = '', units: str = '',
                 level: PipelineStatisticLevel = None):

        self.name = name
        self.value = value
        self.longdesc = longdesc
        self.units = units
        # The level indicates whether a given quantity applies to the whole MOUS, EB, or SPW
        self.level = level
        self.origin = origin

        # Convert initial value from the pipeline to a value that can be serialized by JSON
        # In the future, it may make sense to move this conversion to when the data is written out.
        if type(value) is set:
            self.value = list(self.value)
        elif type(value) is np.int64:
            self.value = int(self.value)
        elif type(value) is np.ndarray:
            self.value = list(self.value)

    def __str__(self) -> str:
        return 'PipelineStatistic({!s}, {!r}, {!r}, {!s})'.format(self.name, self.value, self.origin, self.units)

    def to_dict(self) -> Dict:
        """
        Convert an individual pipeline statistics item to a dictionary
        representation
        """
        stats_dict = {}

        if self.value not in ["", None]:
            stats_dict['value'] = self.value

        if self.units not in ["", None]:
            stats_dict['units'] = self.units

        if self.longdesc not in ["", None]: 
            stats_dict['longdescription'] = self.longdesc

        if self.origin not in ["", None]:
            stats_dict['origin'] = self.origin

        return stats_dict


class PipelineStatsCollection:
    """
    A collection of PipelineStatistics.
    """
    def __init__(self):
        self.stats_collection_mous = {}

        self.stats_collection_eb = {}
        # {eb_name: [stat, stat, stat]}

        self.stats_collection_spw = {}

        self.stats_collection_source = {}

    def add_stat(self, stat: PipelineStatistic, level: PipelineStatisticLevel,
                 mous: str = None, source: str = None, eb: str = None, spw: str = None):

        # deal with situation in which eb level is specificed but not eb
        if level == PipelineStatisticLevel.MOUS:
            if mous not in self.stats_collection_mous:
                self.stats_collection_mous[mous] = []
            self.stats_collection_mous[mous].append(stat)

        elif level == PipelineStatisticLevel.EB:
            if eb not in self.stats_collection_eb:
                self.stats_collection_eb[eb] = []
            self.stats_collection_eb[eb].append(stat)

        elif level == PipelineStatisticLevel.SPW:
            if spw not in self.stats_collection_spw:
                self.stats_collection_spw[spw] = []
            self.stats_collection_spw[spw].append(stat)

        elif level == PipelineStatisticLevel.SOURCE:
            if source not in self.stats_collection_source:
                self.stats_collection_source[source] = []
            self.stats_collection_source[source].append(stat)
        else:
            LOG.warning(f"Unknown pipeline statistics level: {level}")

    def add_stats(self, stats: List[PipelineStatistic], mous: str = None, source: str = None, 
                  level: PipelineStatisticLevel = None, eb: str = None, spw: str = None):
        for stat in stats:
            self.add_stat(stat, level=level, mous=mous, source=source, eb=eb, spw=spw)

    def to_dict(self) -> Dict:
        """
        Generates a nested output dict with EBs, SPWs, TARGETs, MOUSs
        Each level is represented in the structure of the output.
        """
        # new version, using dicts
        final_dict = {}
        for mous_name, mous_stats in self.stats_collection_mous.items():
            final_dict[mous_name] = {stat.name: stat.to_dict() for stat in mous_stats}
            # okay I get it, mous_stats is a list of Pipeline stats object
            # I need to get from [stats, stats, stats]
            # to {stat.name: stat.to_dict()}

        final_dict[mous_name]["EB"] = {}
        for eb_name, eb_stats in self.stats_collection_eb.items():
            final_dict[mous_name]["EB"][eb_name] = {stat.name: stat.to_dict() for stat in eb_stats}

        final_dict[mous_name]["SPW"] = {}
        for spw_name, spw_stats in self.stats_collection_spw.items():
            final_dict[mous_name]["SPW"][spw_name] = {stat.name: stat.to_dict() for stat in spw_stats}

        final_dict[mous_name]["TARGET"] = {}
        for source_name, source_stats in self.stats_collection_source.items():
            final_dict[mous_name]["TARGET"][source_name] = {stat.name: stat.to_dict() for stat in source_stats}
        LOG.info(f"Final dict: {final_dict}")

        # # Step through the collected statistics values and construct
        # # a dictionary representation. The output format is as follows:
        # # { mous_name: {
        # #    mous_property: { ...
        # #    }
        # #    "EB": {
        # #       eb_name: {
        # #           eb_property: {...
        # #           }
        # #       }
        # #    }
        # #    "SPW": {
        # #       spw_id: {
        # #           spw_property: {...
        # #           }
        # #       }
        # #    }
        # #    "TARGET": {
        # #       source_name: {
        # #           source_property: {...
        # #           }
        # #       }
        # #    }
        # #  }
        # #  header: {version: 0.1, creation_date: YYMMDD-HH:MM:SS Z}
        # # }

        # Generate and append a header with information about statistics file version and date created
        version_dict = _generate_header()
        final_dict['header'] = version_dict

        return final_dict


def _generate_header() -> Dict:
    """
    Creates a header with information about the pipeline stats file
    """
    LOG.info("Generating header")
    version_dict = {}
    version_dict["version"] = 1.0
    now = datetime.datetime.now(datetime.timezone.utc)
    dt_string = now.strftime("%Y/%m/%d %H:%M:%S %Z")
    version_dict["stats_file_creation_date"] = dt_string
    return version_dict


# MOUS helper functions
def project_id(context):
    return next(iter(context.observing_run.project_ids))


def pipeline_version(environment) -> str:
    return environment.pipeline_revision


def pipeline_recipe(context) -> str:
    return context.project_structure.recipe_name


def casa_version(environment) -> str:
    return environment.casa_version_string


def mous_uid(context) -> str: 
    return context.get_oussid()


def n_eb(context) -> str:
    return len(context.observing_run.execblock_ids)


def stage_duration(context) -> list:
    #TODO: copied from htmlrenderer.py. Should be pulled out into a common function.

    ## Obtain time duration of tasks by the difference of start times from successive tasks.
    ## The end time of the last task is tentatively defined as the time of current time.

    timestamps = [r.read().timestamps.start for r in context.results]
    
    # tentative task end time stamp for the last stage
    timestamps.append(datetime.datetime.utcnow())
    task_duration = []
    for i in range(len(context.results)):
        # task execution duration
        dt = timestamps[i+1] - timestamps[i]
        # remove unnecessary precision for execution duration
        task_duration.append(dt.total_seconds() / 3600.0)
    return task_duration


def execution_duration(context) -> float:
    """
    Return the execution duration as reported in the aquareport. 
    This is the difference between the time the first stage was
    run in the pipeline and the time the last stage was completed. 
    """

    # Processing time
    exec_start = context.results[0].read().timestamps.start
    exec_end = context.results[-1].read().timestamps.end
    # remove unnecessary precision for execution duration
    dt = exec_end - exec_start
    exec_duration = dt.total_seconds() / 3600.0
    return exec_duration


def stage_info(context) -> dict:
    info = {}
    for i in range(len(context.results)):
        info[context.results[i].read().stage_number] = strip_html(htmlrenderer.get_task_description(context.results[i].read(), context))
    return info


def _get_mous_values(context, mous: str, ms_list: List[MeasurementSet],
                     stats_collection: PipelineStatsCollection):
    """
    Get the statistics values for a given MOUS
    """
    LOG.info("Getting MOUS values")
    level = PipelineStatisticLevel.MOUS
    stats_collection_list = []
    first_ms = ms_list[0]
    LOG.info(f"First ms: {first_ms}")
    import_program = determine_import_program(context=context, ms=first_ms)

    p1 = PipelineStatistic(
        name='project_id',
        value=project_id(context),
        longdesc='Proposal id number',
        origin=import_program,
        level=level,
        )
    stats_collection_list.append(p1)

    p2 = PipelineStatistic(
        name='pipeline_version',
        value=pipeline_version(environment),
        longdesc="pipeline version string",
        origin=import_program,
        level=level,
        )
    stats_collection_list.append(p2)

    p3 = PipelineStatistic(
        name='pipeline_recipe',
        value=pipeline_recipe(context),
        longdesc="recipe name",
        origin=import_program,
        level=level,
        )
    stats_collection_list.append(p3)

    p4 = PipelineStatistic(
        name='casa_version',
        value=casa_version(environment),
        longdesc="casa version string",
        origin=import_program,
        level=level,
        )
    stats_collection_list.append(p4)

    p5 = PipelineStatistic(
        name='mous_uid',
        value=mous_uid(context),
        longdesc="Member Obs Unit Set ID",
        origin=import_program,
        level=level,
        )
    stats_collection_list.append(p5)

    p6 = PipelineStatistic(
        name='n_EB',
        value=n_eb(context),
        longdesc="number of execution blocks",
        origin=import_program,
        level=level,
    )

    stats_collection_list.append(p6)

    all_bands = sorted({spw.band for spw in ms_list[0].get_all_spectral_windows()})
    p7 = PipelineStatistic(
        name='bands',
        value=all_bands,
        longdesc="Band(s) used in observations.",
        origin=import_program,
        level=level,
        )
    stats_collection_list.append(p7)

    science_source_names = sorted({source.name for source in ms_list[0].sources if 'TARGET' in source.intents})

    p8 = PipelineStatistic(
        name='n_target',
        value=len(science_source_names),
        longdesc="total number of science targets in the MOUS",
        origin=import_program,
        level=level,
    )

    stats_collection_list.append(p8)

    p9 = PipelineStatistic(
        name='target_list',
        value=science_source_names,
        longdesc="list of science target names",
        origin=import_program,
        level=PipelineStatisticLevel.MOUS)
    stats_collection_list.append(p9)

    p10 = PipelineStatistic(
        name='rep_target',
        value=first_ms.representative_target[0],
        longdesc="representative target name",
        origin=import_program,
        level=PipelineStatisticLevel.MOUS)
    stats_collection_list.append(p10)

    p11 = PipelineStatistic(
        name='n_spw',
        value=len(first_ms.get_all_spectral_windows()),
        longdesc="number of spectral windows",
        origin=import_program,
        level=PipelineStatisticLevel.MOUS)
    stats_collection_list.append(p11)

    stats_collection_list.append(
        PipelineStatistic(
            name='total_time',
            value=execution_duration(context),
            longdesc="total processing time",
            units="hours",
            origin=import_program,
            level=PipelineStatisticLevel.MOUS,
        )
    )

    stats_collection_list.append(
        PipelineStatistic(
            name='stage_info',
            value=stage_info(context),
            longdesc="stage number and name",
            origin=import_program,
            level=PipelineStatisticLevel.MOUS,
        )
    )

    stats_collection_list.append(
        PipelineStatistic(
            name='stage_duration',
            value=stage_duration(context),
            longdesc="time spent in each stage",
            units="hours",
            origin=import_program,
            level=PipelineStatisticLevel.MOUS,
        )
    )

    stats_collection.add_stats(stats_collection_list, level=PipelineStatisticLevel.MOUS, mous=mous)


# MS helper functions (only EB so far)
def n_ant(ms: MeasurementSet) -> int:
    return len(ms.antennas)


def n_scan(ms: MeasurementSet) -> int:
    return len(ms.get_scans())


def l80(ms: MeasurementSet) -> float:
    return np.percentile(ms.antenna_array.baselines_m, 80)


def _get_eb_values(context, mous: str, ms_list: List[MeasurementSet],
                   stats_collection: PipelineStatsCollection):
    """
    Get the statistics values for a given EB
    """
    LOG.info("Getting EB values")
    level = PipelineStatisticLevel.EB
    import_program = determine_import_program(context, ms_list[0])

    for ms in ms_list:
        eb = ms.name
        stats_collection_list = []
        p1 = PipelineStatistic(
            name='n_ant',
            value=n_ant(ms),
            longdesc="Number of antennas per execution block",
            origin=import_program,
            level=level,
        )
        stats_collection_list.append(p1)

        p2 = PipelineStatistic(
            name='n_scan',
            value=n_scan(ms),
            longdesc="number of scans per EB",
            origin=import_program,
            level=level,
        )
        stats_collection_list.append(p2)

        p3 = PipelineStatistic(
            name='L80',
            value=l80(ms),
            longdesc="80th percentile baseline",
            origin=import_program,
            units="m",
            level=level,
        )

        stats_collection_list.append(p3)
        stats_collection.add_stats(stats_collection_list, level=level, mous=mous, eb=eb)


# SPW helper functions
def spw_width(spw) -> float:
    return float(spw.bandwidth.to_units(measures.FrequencyUnits.MEGAHERTZ))


def spw_freq(spw) -> float:
    return float(spw.centre_frequency.to_units(measures.FrequencyUnits.GIGAHERTZ))


def n_chan(spw) -> int:
    return spw.num_channels


def nbin_online(spw) -> int:
    return spw.sdm_num_bin


def chan_width(spw) -> float:
    chan_width_MHz = [chan * 1e-6 for chan in spw.channels.chan_widths]
    return chan_width_MHz[0]


def n_pol(spw, ms) -> int:
    dd = ms.get_data_description(spw=int(spw.id))
    numpols = dd.num_polarizations
    return numpols


def _get_spw_values(context, mous: str, ms_list: List[MeasurementSet],
                    stats_collection: PipelineStatsCollection):
    """
    Get the statistics values for a given SPW
    """
    LOG.info("Getting SPW values")
    level = PipelineStatisticLevel.SPW
    stats_collection_list = []
    ms = ms_list[0]
    spw_list = ms.get_all_spectral_windows()
    import_program = determine_import_program(context, ms)

    for spw in spw_list:
        p1 = PipelineStatistic(
            name='spw_width',
            value=spw_width(spw),
            longdesc="width of the spectral window",
            origin=import_program,
            units="MHz",
            level=level,
        )
        stats_collection_list.append(p1)

        p2 = PipelineStatistic(
            name='spw_freq',
            value=spw_freq(spw),
            longdesc="central frequency of the spectral window in TOPO",
            origin=import_program,
            units="GHz",
            level=level,
        )
        stats_collection_list.append(p2)

        p3 = PipelineStatistic(
            name='n_chan',
            value=n_chan(spw),
            longdesc="number of channels in the spectral window",
            origin=import_program,
            level=level,
        )
        stats_collection_list.append(p3)

        p4 = PipelineStatistic(
            name='nbin_online',
            value=nbin_online(spw),
            longdesc="online nbin factor",
            origin=import_program,
            level=level,
        )
        stats_collection_list.append(p4)

        p5 = PipelineStatistic(
            name='chan_width',
            value=chan_width(spw),
            longdesc="frequency width of the channels in the spectral window",
            origin=import_program,
            units="MHz",
            level=level,
        )
        stats_collection_list.append(p5)

        p6 = PipelineStatistic(
            name='n_pol',
            value=n_pol(spw, ms),
            longdesc="number of polarizations in the spectral window",
            origin=import_program,
            level=level,
        )
        stats_collection_list.append(p6)
        stats_collection.add_stats(stats_collection_list, level=PipelineStatisticLevel.SPW, spw=spw.id, mous=mous)


# source helper functions
def pointings(ms, source):
    pointings = len([f for f in ms.fields if f.source_id == source.id])
    return pointings


def _get_source_values(context, mous: str, ms_list: List[MeasurementSet],
                       stats_collection: PipelineStatsCollection):
    """
    Get the statistics values for a given source
    """
    LOG.info("Getting source values")
    level = PipelineStatisticLevel.SOURCE
    first_ms = ms_list[0]
    import_program = determine_import_program(context, first_ms)

    science_sources = sorted({source for source in first_ms.sources
                              if 'TARGET' in source.intents}, key=lambda source: source.name)

    for source in science_sources:
        LOG.info(f"Getting source values for {source.name}")
        p1 = PipelineStatistic(
            name='n_pointings',
            value=pointings(first_ms, source),
            longdesc="number of mosaic pointings for the science target",
            origin=import_program,
            level=level,
        )
        stats_collection.add_stat(p1, level=level, mous=mous, source=source.name)


def get_stats_from_context(context) -> PipelineStatsCollection:
    """
    Gather statistics results for the pipleline run information and pipeline product information
    These can be directly obtained from the context.
    """
    LOG.info("Getting pipeline statistics from context")
    mous = context.get_oussid()

    # List of datatypes to use (in order) for fetching EB-level information.
    # The following function call will fetch all the MSes for only the first
    # datatype it finds in the list. This is needed so that information is
    # not repeated for the ms and _targets.ms when both are present.
    datatypes = [DataType.REGCAL_CONTLINE_ALL, DataType.REGCAL_CONTLINE_SCIENCE, DataType.SELFCAL_CONTLINE_SCIENCE,
                 DataType.REGCAL_LINE_SCIENCE, DataType.SELFCAL_LINE_SCIENCE, DataType.RAW]
    ms_list = context.observing_run.get_measurement_sets_of_type(datatypes)

    stats_collection = PipelineStatsCollection()
    # TODO: If keeping this pattern, update all names to _add_mous_values, etc...
    # Don't *want* to pass stats_collection around, but leave it for now.

    # Add MOUS-level information
    _get_mous_values(context, mous, ms_list, stats_collection)

    # Add per-EB information
    _get_eb_values(context, mous, ms_list, stats_collection)

    # # Add per-SPW stats information
    # The spw ids from the first MS are used so the information will be included once per MOUS.
    _get_spw_values(context, mous, ms_list, stats_collection)

    # # Add per-SOURCE stats information
    _get_source_values(context, mous, ms_list, stats_collection)

    return stats_collection


# Used to be in stats_extractor.py
class ResultsStatsExtractor(object, metaclass=abc.ABCMeta):
    """
    Adapted from the RegressisonExtractor,
    this class is the base class for a pipeline statistics extractor
    which uses a result to extract statistics information.
    """
    # the Results class this handler is expected to handle
    result_cls = None
    # if result_cls is a list, the type of classes it is expected to contain
    child_cls = None
    # the task class that generated the results, or None if it should handle
    # all results of this type regardless of which task generated it
    generating_task = None

    def is_handler_for(self, result: Union[Results, ResultsList]) -> bool:
        """
        Return True if this StatsExtractor can process the Result.

        result: the task Result to inspect
        returns: True if the Result can be processed
        """
        # if the result is not a list or the expected results class,
        # return False
        if not isinstance(result, self.result_cls):
            return False

        # this is the expected class and we weren't expecting any
        # children, so we should be able to handle the result
        if self.child_cls is None and (self.generating_task is None
                                       or result.task is self.generating_task
                                       or (hasattr(self.generating_task, 'Task') and result.task is self.generating_task.Task)):
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
    def handle(self, result: Results, context=None) -> PipelineStatistic:
        """
        [Abstract] Extract pipeline statistics values

        This method should return a PipelineStatistic object

        :param result:
        :return:
        """
        raise NotImplementedError


class StatsExtractorRegistry(object):
    """
    The registry and manager of the stats result extractor framework.

    The responsibility of the StatsResultRegistry is to pass Results to
    Extractors that can handle them.
    """
    def __init__(self):
        """Constractor of this class."""
        self.__plugins_loaded = False
        self.__handlers = []

    def add_handler(self, handler: ResultsStatsExtractor) -> None:
        """
        Push ResultsStatsExtractor into handlers list __handler.

        Args:
            handler: ResultsStatsExtractor
        """
        task = handler.generating_task.__name__ if handler.generating_task else 'all'
        child_name = ''
        if hasattr(handler.child_cls, '__name__'):
            child_name = handler.child_cls.__name__
        elif isinstance(handler.child_cls, collections.abc.Iterable):
            child_name = str([x.__name__ for x in handler.child_cls])
        container = 's of %s' % child_name
        s = '{}{} results generated by {} tasks'.format(handler.result_cls.__name__, container, task)
        LOG.debug('Registering {} as new pipeline stats handler for {}'.format(handler.__class__.__name__, s))
        self.__handlers.append(handler)

    def handle(self, result: Union[Results, ResultsList], context=None):
        """
        Extract values from corresponding StatsExtractor object of Result object.
        """
        if not self.__plugins_loaded:
            for plugin_class in regression.get_all_subclasses(ResultsStatsExtractor):
                self.add_handler(plugin_class())
            self.__plugins_loaded = True

        extracted = []

        # Process leaf results first
        if isinstance(result, collections.abc.Iterable):
            LOG.info("Result type: {}".format(type(result)))
            for r in result:
                LOG.info("Extracting stats for {}".format(r.__class__.__name__))
                LOG.info("Descending... calling self with result: {}".format(r))
                d = self.handle(r, context)
                extracted = union(extracted, d)

        # process the group-level results.
        for handler in self.__handlers:
            if handler.is_handler_for(result):
                LOG.info('{} extracting stats results for {}'.format(handler.__class__.__name__,
                                                                           result.__class__.__name__))
                d = handler.handle(result, context)
                extracted = union(extracted, d)

        return extracted


# default StatsExtractorRegistry initialization
registry = StatsExtractorRegistry()


class FlagDeterALMAResultsExtractor(ResultsStatsExtractor):
    result_cls = FlagDeterALMAResults
    child_cls = None

    def handle(self, result: FlagDeterALMAResults, context) -> Dict:
        value = self.calculate_value(result, context)
        ps = self.create_stat(value)
        return ps

    def calculate_value(self, result: FlagDeterALMAResults, context: Context) -> Dict:
        intents_to_summarise = flagutils.intents_to_summarise(context)
        flag_table_intents = ['TOTAL', 'SCIENCE SPWS']
        flag_table_intents.extend(intents_to_summarise)

        flag_totals = {}
        flag_totals = utils.dict_merge(flag_totals,
                      flagutils.flags_for_result(result, context, intents_to_summarise=intents_to_summarise))

        reasons_to_export = ['online', 'shadow', 'qa0', 'qa2', 'before', 'template']

        output_dict = {}
        for ms in flag_totals:
            output_dict[ms] = {}
            for reason in flag_totals[ms]:
                for intent in flag_totals[ms][reason]:
                    if reason in reasons_to_export:
                        if "TOTAL" in intent:
                            new = float(flag_totals[ms][reason][intent][0])
                            total = float(flag_totals[ms][reason][intent][1])
                            percentage = new/total * 100
                            output_dict[ms][reason] = percentage
        return output_dict

    def create_stat(self, value_dict: dict) -> Dict:
        longdescription = "dictionary giving percentage of data newly flagged by the following intents: online, shadow, qa0, qa2 before and template flagging agents"
        stats = {}
        for ms in value_dict:
            ps = PipelineStatistic(name="flagdata_percentage",
                                   value=value_dict[ms],
                                   longdesc=longdescription,
                                   units='%',
                                   level=PipelineStatisticLevel.EB)
            stats[ms] = ps
        return stats


class FluxcalflagResultsStatsExtractor(ResultsStatsExtractor):
    """Regression test result extractor for hifa_gfluxscaleflag.

    The extracted values are:
       - the number of flagged rows before this task
       - the number of flagged rows after this task
       - QA score
    """

    result_cls = GfluxscaleflagResults
    child_cls = None
    generating_task = Gfluxscaleflag

    def handle(self, result: GfluxscaleflagResults, context) -> Dict:
        before, after = self.calculate_value(result, context)
        vis = result.inputs['vis']
        ps = self.create_stat(before, after, vis)
        return ps

    def calculate_value(self, result: GfluxscaleflagResults, context):
        """Extract values for testing.

        Args:
            result: GfluxscaleflagResults object
        
        Returns:
            OrderedDict[str, float]
        """
        summaries_by_name = {s['name']: s for s in result.cafresult.summaries}

        print("THIS HERE: ")
        print(result)
        print(result.cafresult.summaries)

        num_flags_before = summaries_by_name['before']['flagged']

        if 'after' in summaries_by_name:
            num_flags_after = summaries_by_name['after']['flagged']
        else:
            num_flags_after = num_flags_before

        qa_entries = extract_qa_score_regression(prefix, result)
        d.update(qa_entries)

        return int(num_flags_before), int(num_flags_after)

    def create_stat(self, before, after, vis) -> Dict:
        longdescription = "Added for regression tests: number of flags before gfluxscaleflag."
        ps1 = PipelineStatistic(name="gfluxscaleflag_before",
                               value=before,
                               longdesc=longdescription,
                               level=PipelineStatisticLevel.EB)
        longdescription = "Added for regression tests: number of flags after gfluxscaleflag."
        ps2 = PipelineStatistic(name="gfluxscaleflag_after",
                               value=after,
                               longdesc=longdescription,
                               level=PipelineStatisticLevel.EB)
        dct1 = {}
        dct2 = {}
        dct1[vis] = ps1
        dct2[vis] = ps2
        # oof that won't do it
        return [dct1, dct2]


class GcorFluxscaleResultsStatsExtractor(ResultsStatsExtractor):
    """
    Regression test result extractor for hifa_gcorfluxscale.

    The extracted values are:
       - Stokes I for each field and spw, in Jy
    """

    result_cls = FluxCalibrationResults
    child_cls = None
    generating_task = GcorFluxscale

    def handle(self, result:FluxCalibrationResults, context) -> Dict:
        val = self.calculate_value(result)
        vis = result.inputs['vis']
        ps = self.create_stat(vis, val)
        return ps

    def calculate_value(self, result:FluxCalibrationResults) -> Dict:
        """
        Extract values for testing.

        Args:
            result: FluxCalibrationResults object
        
        Returns:
            OrderedDict[str, float]
        """
        d = {}
        for field_id, measurements in result.measurements.items():
            for m in measurements:
                key = 'field_{}.spw_{}.I'.format(field_id, m.spw_id)
                d[key] = str(m.I.to_units(FluxDensityUnits.JANSKY))

        qa_entries = extract_qa_score_regression(prefix, result)
        d.update(qa_entries)

        return d

    def create_stat(self, vis, val):
        longdescription = "Added for regression tests: flux density results from flux calibration."
        ps1 = PipelineStatistic(name="fluxcal_I",
                                value=val,
                                longdesc=longdescription,
                                level=PipelineStatisticLevel.EB)
        d = {}
        d[vis] = ps1
        return d


class ApplycalResultsStatsExtractor(ResultsStatsExtractor):
    """
    Regression test result extractor for applycal tasks.

    The extracted values are:
       - the number of flagged and scanned rows before this task
       - the number of flagged and scanned rows after this task
       - QA score
    """

    result_cls = ApplycalResults
    child_cls = None
    generating_task = IFApplycal

    def handle(self, result:FluxCalibrationResults, context) -> Dict:
        val = self.calculate_value(result)
        vis = result.inputs['vis']
        ps = self.create_stat(vis, val)
        return ps

    def calculate_value(self, result:ApplycalResults) -> Dict:
        """
        Extract values for testing.

        Args:
            result: ApplycalResults object
        
        Returns:
            OrderedDict[str, float]
        """
        d = {}

        try:
            summaries_by_name = {s['name']: s for s in result.summaries}
            num_flags_before = summaries_by_name['before']['flagged']
            num_flags_after = summaries_by_name['applycal']['flagged']
            
            d['num_rows_flagged.before'] = int(num_flags_before)
            d['num_rows_flagged.after'] = int(num_flags_after)

            flag_summary_before = summaries_by_name['before']
            for scan_id, v in flag_summary_before['scan'].items():
                d['scan_{}.num_rows_flagged.before'.format(scan_id)] = int(v['flagged'])

            flag_summary_after = summaries_by_name['applycal']
            for scan_id, v in flag_summary_after['scan'].items():
                d['scan_{}.num_rows_flagged.after'.format(scan_id)] = int(v['flagged'])

            qa_entries = extract_qa_score_regression(prefix, result)
            d.update(qa_entries)
        except:
            LOG.info("Some information missing from ApplycalResults. Omitting from resgression comparison.")
            d = {}
        return d

    def create_stat(self, vis, val):
        longdescription = "Added for regression tests: applycal flags before and after"
        ps1 = PipelineStatistic(name="applycal_flagging",
                                value=val,
                                longdesc=longdescription,
                                level=PipelineStatisticLevel.EB)
        d = {}
        d[vis] = ps1
        return d


class SDApplycalResultsStatsExtractor(ApplycalResultsStatsExtractor):
    """
    Pipeline statistics extractor for sd_applycal.
    
    It extends ApplycalResultsStatsExtractor to use the same extraction logic.
    """
    result_cls = ApplycalResults
    child_cls = None
    generating_task = SDApplycal


class VLAApplycalResultsStatsExtractor(ApplycalResultsStatsExtractor):
    """
    Pipeline statistics extractor for hifv_applycals.
    
    It extends ApplycalResultsStatsExtractor to use the same extraction logic.
    """
    result_cls = ApplycalResults
    child_cls = None
    generating_task = Applycals


class CheckflagResultsStatsExtractor(ResultsStatsExtractor):
    """
    Pipeline statistics extractor for hifv_checkflag.
    
    Extract flagging summaries from CheckflagResults.
    """
    result_cls = CheckflagResults
    child_cls = None
    generating_task = Checkflag

    def handle(self, result: CheckflagResults, context) -> Dict:
        val = self.calculate_value(result)
        vis = result.inputs['vis']
        ps = self.create_stat(vis, val)
        return ps

    def calculate_value(self, result: CheckflagResults) -> Dict:
        """
        Extract values for pipeline statistics.

        Args:
            result: CheckflagResults object

        Returns:
            Dict[str, Union[int, Dict]]
        """
        d = {}
        try:
            summaries_by_name = {s['name']: s for s in result.summaries}
            
            if 'before' in summaries_by_name:
                num_flags_before = summaries_by_name['before']['flagged']
                d['num_rows_flagged.before'] = int(num_flags_before)
                
                flag_summary_before = summaries_by_name['before']
                scan_before = {}
                for scan_id, v in flag_summary_before['scan'].items():
                    scan_before[f'scan_{scan_id}'] = int(v['flagged'])
                if scan_before:
                    d['scan.num_rows_flagged.before'] = scan_before
            else:
                d['num_rows_flagged.before'] = None

            if 'after' in summaries_by_name:
                num_flags_after = summaries_by_name['after']['flagged']
                d['num_rows_flagged.after'] = int(num_flags_after)
                
                flag_summary_after = summaries_by_name['after']
                scan_after = {}
                for scan_id, v in flag_summary_after['scan'].items():
                    scan_after[f'scan_{scan_id}'] = int(v['flagged'])
                if scan_after:
                    d['scan.num_rows_flagged.after'] = scan_after
            else:
                d['num_rows_flagged.after'] = None

        except Exception as e:
            LOG.info(f"Some information missing from CheckflagResults: {e}")
            d = {}

        return d

    def create_stat(self, vis, val):
        longdescription = "Added for pipeline statistics: checkflag flagging summaries."
        ps1 = PipelineStatistic(name="checkflag_flagging",
                                value=val,
                                longdesc=longdescription,
                                level=PipelineStatisticLevel.EB)
        d = {}
        d[vis] = ps1
        return d


class TargetflagResultsStatsExtractor(ResultsStatsExtractor):
    """
    Pipeline statistics extractor for hifv_targetflag.
    
    Extract flagging summaries from TargetflagResults.
    """
    result_cls = TargetflagResults
    child_cls = None
    generating_task = Targetflag

    def handle(self, result: TargetflagResults, context) -> Dict:
        val = self.calculate_value(result)
        vis = result.inputs['vis']
        ps = self.create_stat(vis, val)
        return ps

    def calculate_value(self, result: TargetflagResults) -> Dict:
        """
        Extract values for pipeline statistics.

        Args:
            result: TargetflagResults object

        Returns:
            Dict[str, Union[int, Dict]]
        """
        d = {}
        try:
            summaries_by_name = {s['name']: s for s in result.summarydict}
            
            if 'Summary' in summaries_by_name:
                num_flags_summary = summaries_by_name['Summary']['flagged']
                d['num_rows_flagged.summary'] = int(num_flags_summary)
                
                flag_summary = summaries_by_name['Summary']
                scan_summary = {}
                for scan_id, v in flag_summary['scan'].items():
                    scan_summary[f'scan_{scan_id}'] = int(v['flagged'])
                if scan_summary:
                    d['scan.num_rows_flagged.summary'] = scan_summary

        except Exception as e:
            LOG.info(f"Some information missing from TargetflagResults: {e}")
            d = {}

        return d

    def create_stat(self, vis, val):
        longdescription = "Added for pipeline statistics: targetflag flagging summaries."
        ps1 = PipelineStatistic(name="targetflag_flagging",
                                value=val,
                                longdesc=longdescription,
                                level=PipelineStatisticLevel.EB)
        d = {}
        d[vis] = ps1
        return d


class FluxbootResultsStatsExtractor(ResultsStatsExtractor):
    """
    Pipeline statistics extractor for hifv_fluxboot.

    The extracted values are:
       - the flux_densities value (single spw)
       - spectral index list values (spix, curvature, delta, gamma coefficients)
    """
    result_cls = FluxbootResults
    child_cls = None
    generating_task = Fluxboot

    def handle(self, result: FluxbootResults, context) -> Dict:
        val = self.calculate_value(result)
        vis = result.inputs['vis']
        ps = self.create_stat(vis, val)
        return ps

    def calculate_value(self, result: FluxbootResults) -> Dict:
        """
        Extract values for pipeline statistics.

        Args:
            result: FluxbootResults object

        Returns:
            Dict[str, Union[float, Dict]]
        """
        d = {}
        try:
            flux_densities = result.flux_densities
            spindex = result.spindex_results

            # Extract flux densities per spw
            flux_dict = {}
            for i, spw in enumerate(sorted(result.spws)):
                flux_dict[f'spw_{spw}'] = flux_densities[i][0]
            if flux_dict:
                d['flux_densities'] = flux_dict

            # Extract spectral index parameters
            if spindex:
                d['spindex.spix'] = float(spindex[0]['spix'])
                d['spindex.curvature'] = float(spindex[0]['curvature'])
                d['spindex.delta'] = float(spindex[0]['delta'])
                d['spindex.gamma'] = float(spindex[0]['gamma'])

        except Exception as e:
            LOG.info(f"Some information missing from FluxbootResults: {e}")
            d = {}

        return d

    def create_stat(self, vis, val):
        longdescription = "Added for pipeline statistics: fluxboot flux densities and spectral index."
        ps1 = PipelineStatistic(name="fluxboot_results",
                                value=val,
                                longdesc=longdescription,
                                level=PipelineStatisticLevel.EB)
        d = {}
        d[vis] = ps1
        return d


class SolintResultsStatsExtractor(ResultsStatsExtractor):
    """
    Pipeline statistics extractor for hifv_solint.

    The extracted values are:
       - long solution interval per band
       - short solution interval per band
       - shortsol2 variable interval per band
    """
    result_cls = SolintResults
    child_cls = None
    generating_task = Solint

    def handle(self, result: SolintResults, context) -> Dict:
        val = self.calculate_value(result)
        vis = result.inputs['vis']
        ps = self.create_stat(vis, val)
        return ps

    def calculate_value(self, result: SolintResults) -> Dict:
        """
        Extract values for pipeline statistics.

        Args:
            result: SolintResults object

        Returns:
            Dict[str, Dict[str, float]]
        """
        d = {}
        try:
            solint_dict = {}
            for band, value in result.longsolint.items():
                solint_dict[f'{band}-band'] = {
                    'longsolint': value,
                    'short_solint': result.short_solint[band],
                    'shortsol2': result.shortsol2[band]
                }
            if solint_dict:
                d['solution_intervals'] = solint_dict

        except Exception as e:
            LOG.info(f"Some information missing from SolintResults: {e}")
            d = {}

        return d

    def create_stat(self, vis, val):
        longdescription = "Added for pipeline statistics: solint solution intervals per band."
        ps1 = PipelineStatistic(name="solint_intervals",
                                value=val,
                                longdesc=longdescription,
                                level=PipelineStatisticLevel.EB)
        d = {}
        d[vis] = ps1
        return d


class PriorcalsResultsStatsExtractor(ResultsStatsExtractor):
    """
    Pipeline statistics extractor for hifv_priorcals.

    The extracted values are:
       - Opacities per spw
    """
    result_cls = PriorcalsResults
    child_cls = None
    generating_task = Priorcals

    def handle(self, result: PriorcalsResults, context) -> Dict:
        val = self.calculate_value(result)
        vis = result.inputs['vis']
        ps = self.create_stat(vis, val)
        return ps

    def calculate_value(self, result: PriorcalsResults) -> Dict:
        """
        Extract values for pipeline statistics.

        Args:
            result: PriorcalResults object

        Returns:
            Dict[str, Dict[str, float]]
        """
        d = {}
        try:
            opacity_dict = {}
            for idx, opacity in enumerate(result.oc_result.opacities):
                spw = result.oc_result.spw[idx]
                opacity_dict[f'spw_{spw}'] = opacity
            if opacity_dict:
                d['opacity'] = opacity_dict

        except Exception as e:
            LOG.info(f"Some information missing from PriorcalsResults: {e}")
            d = {}

        return d

    def create_stat(self, vis, val):
        longdescription = "Added for pipeline statistics: priorcals opacities per spw."
        ps1 = PipelineStatistic(name="priorcals_opacity",
                                value=val,
                                longdesc=longdescription,
                                level=PipelineStatisticLevel.EB)
        d = {}
        d[vis] = ps1
        return d


class VLASetjyResultsStatsExtractor(ResultsStatsExtractor):
    """
    Pipeline statistics extractor for hifv_vlasetjy.

    The extracted values are:
       - Stokes I flux value per field
    """
    result_cls = FluxCalibrationResults
    child_cls = None
    generating_task = VLASetjy

    def handle(self, result: FluxCalibrationResults, context) -> Dict:
        val = self.calculate_value(result)
        vis = result.inputs['vis']
        ps = self.create_stat(vis, val)
        return ps

    def calculate_value(self, result: FluxCalibrationResults) -> Dict:
        """
        Extract values for pipeline statistics.

        Args:
            result: FluxCalibrationResults object

        Returns:
            Dict[str, Dict[str, float]]
        """
        d = {}
        try:
            flux_dict = {}
            for field, fluxlist in result.measurements.items():
                flux_I = float(fluxlist[0].I.value)
                flux_dict[f'field_{field}'] = {'I': flux_I}
            if flux_dict:
                d['flux'] = flux_dict

        except Exception as e:
            LOG.info(f"Some information missing from FluxCalibrationResults: {e}")
            d = {}

        return d

    def create_stat(self, vis, val):
        longdescription = "Added for pipeline statistics: vlasetjy flux calibration values."
        ps1 = PipelineStatistic(name="vlasetjy_flux",
                                value=val,
                                longdesc=longdescription,
                                level=PipelineStatisticLevel.EB)
        d = {}
        d[vis] = ps1
        return d


class VLAStatwtResultsStatsExtractor(ResultsStatsExtractor):
    """
    Pipeline statistics extractor for hifv_statwt.

    The extracted values are:
       - mean and variance
    """
    result_cls = StatwtResults
    child_cls = None
    generating_task = Statwt

    def handle(self, result: StatwtResults, context) -> Dict:
        val = self.calculate_value(result)
        vis = result.inputs['vis']
        ps = self.create_stat(vis, val)
        return ps

    def calculate_value(self, result: StatwtResults) -> Dict:
        """
        Extract values for pipeline statistics.

        Args:
            result: StatwtResults object

        Returns:
            Dict[str, float]
        """
        d = {}
        try:
            if result.jobs:
                d['mean'] = result.jobs[0]['mean']
                d['variance'] = result.jobs[0]['variance']

        except Exception as e:
            LOG.info(f"Some information missing from StatwtResults: {e}")
            d = {}

        return d

    def create_stat(self, vis, val):
        longdescription = "Added for pipeline statistics: statwt mean and variance."
        ps1 = PipelineStatistic(name="statwt_stats",
                                value=val,
                                longdesc=longdescription,
                                level=PipelineStatisticLevel.EB)
        d = {}
        d[vis] = ps1
        return d


class VLAImportDataResultsStatsExtractor(ResultsStatsExtractor):
    """
    Pipeline statistics extractor for hifv_importdata.

    The extracted values are:
       - number of antennas
       - max integration time
    """
    result_cls = VLAImportDataResults
    child_cls = None
    generating_task = VLAImportData

    def handle(self, result: VLAImportDataResults, context) -> Dict:
        val = self.calculate_value(result)
        vis = result.inputs['vis'] if hasattr(result, 'inputs') and 'vis' in result.inputs else result.mses[0].name if result.mses else None
        if vis and val:
            ps = self.create_stat(vis, val)
            return ps
        return {}

    def calculate_value(self, result: VLAImportDataResults) -> Dict:
        """
        Extract values for pipeline statistics.

        Args:
            result: VLAImportDataResults object

        Returns:
            Dict[str, Union[int, float]]
        """
        d = {}
        try:
            if result.mses:
                d['numantennas'] = len(result.mses[0].antennas)
                d['vla_max_integration_time'] = result.mses[0].get_integration_time_stats(stat_type="max")

        except Exception as e:
            LOG.info(f"Some information missing from VLAImportDataResults: {e}")
            d = {}

        return d

    def create_stat(self, vis, val):
        longdescription = "Added for pipeline statistics: VLA import data antenna count and integration time."
        ps1 = PipelineStatistic(name="vla_importdata_stats",
                                value=val,
                                longdesc=longdescription,
                                level=PipelineStatisticLevel.EB)
        d = {}
        d[vis] = ps1
        return d


class FlagDeterVLAResultsStatsExtractor(ResultsStatsExtractor):
    """
    Pipeline statistics extractor for hifv_flagdata.

    The extracted values are:
       - number of flags per category
    """
    result_cls = FlagDeterVLAResults
    child_cls = None
    generating_task = FlagDeterVLA

    def handle(self, result: FlagDeterVLAResults, context) -> Dict:
        val = self.calculate_value(result)
        vis = result.inputs['vis']
        ps = self.create_stat(vis, val)
        return ps

    def calculate_value(self, result: FlagDeterVLAResults) -> Dict:
        """
        Extract values for pipeline statistics.

        Args:
            result: FlagDeterVLAResults object

        Returns:
            Dict[str, Dict[str, int]]
        """
        d = {}
        try:
            flag_dict = {}
            for summary in result.summaries:
                category = summary['name']
                flag_dict[category] = int(summary['flagged'])
            if flag_dict:
                d['flagged'] = flag_dict

        except Exception as e:
            LOG.info(f"Some information missing from FlagDeterVLAResults: {e}")
            d = {}

        return d

    def create_stat(self, vis, val):
        longdescription = "Added for pipeline statistics: VLA flagdata flagging by category."
        ps1 = PipelineStatistic(name="vla_flagdata_flagging",
                                value=val,
                                longdesc=longdescription,
                                level=PipelineStatisticLevel.EB)
        d = {}
        d[vis] = ps1
        return d


class testBPdcalsResultsStatsExtractor(ResultsStatsExtractor):
    """
    Pipeline statistics extractor for hifv_testBPdcals.

    The extracted values are:
       - number of flagged solutions per band for bandpass and delay
    """
    result_cls = testBPdcalsResults
    child_cls = None
    generating_task = testBPdcals

    def handle(self, result: testBPdcalsResults, context) -> Dict:
        val = self.calculate_value(result)
        vis = result.inputs['vis']
        ps = self.create_stat(vis, val)
        return ps

    def calculate_value(self, result: testBPdcalsResults) -> Dict:
        """
        Extract values for pipeline statistics.

        Args:
            result: testBPdcalsResults object

        Returns:
            Dict[str, Dict[str, Dict[str, int]]]
        """
        d = {}
        try:
            bandpass_dict = {}
            for band, flagdict in result.flaggedSolnApplycalbandpass.items():
                bandpass_dict[f'{band}-band'] = int(flagdict['all']['flagged'])
            if bandpass_dict:
                d['bandpass.flagged'] = bandpass_dict

            delay_dict = {}
            for band, flagdict in result.flaggedSolnApplycaldelay.items():
                delay_dict[f'{band}-band'] = int(flagdict['all']['flagged'])
            if delay_dict:
                d['delay.flagged'] = delay_dict

        except Exception as e:
            LOG.info(f"Some information missing from testBPdcalsResults: {e}")
            d = {}

        return d

    def create_stat(self, vis, val):
        longdescription = "Added for pipeline statistics: testBPdcals flagged solutions per band."
        ps1 = PipelineStatistic(name="testbpdcals_flagged",
                                value=val,
                                longdesc=longdescription,
                                level=PipelineStatisticLevel.EB)
        d = {}
        d[vis] = ps1
        return d


class semiFinalBPdcalsResultsStatsExtractor(ResultsStatsExtractor):
    """
    Pipeline statistics extractor for hifv_semiFinalBPdcals.

    The extracted values are:
       - number of flagged solutions per band for bandpass and delay
    """
    result_cls = semiFinalBPdcalsResults
    child_cls = None
    generating_task = semiFinalBPdcals

    def handle(self, result: semiFinalBPdcalsResults, context) -> Dict:
        val = self.calculate_value(result)
        vis = result.inputs['vis']
        ps = self.create_stat(vis, val)
        return ps

    def calculate_value(self, result: semiFinalBPdcalsResults) -> Dict:
        """
        Extract values for pipeline statistics.

        Args:
            result: semiFinalBPdcalsResults object

        Returns:
            Dict[str, Dict[str, Dict[str, int]]]
        """
        d = {}
        try:
            bandpass_dict = {}
            for band, flagdict in result.flaggedSolnApplycalbandpass.items():
                bandpass_dict[f'{band}-band'] = int(flagdict['all']['flagged'])
            if bandpass_dict:
                d['bandpass.flagged'] = bandpass_dict

            delay_dict = {}
            for band, flagdict in result.flaggedSolnApplycaldelay.items():
                delay_dict[f'{band}-band'] = int(flagdict['all']['flagged'])
            if delay_dict:
                d['delay.flagged'] = delay_dict

        except Exception as e:
            LOG.info(f"Some information missing from semiFinalBPdcalsResults: {e}")
            d = {}

        return d

    def create_stat(self, vis, val):
        longdescription = "Added for pipeline statistics: semiFinalBPdcals flagged solutions per band."
        ps1 = PipelineStatistic(name="semifinalbpdcals_flagged",
                                value=val,
                                longdesc=longdescription,
                                level=PipelineStatisticLevel.EB)
        d = {}
        d[vis] = ps1
        return d


class FinalcalsResultsStatsExtractor(ResultsStatsExtractor):
    """
    Pipeline statistics extractor for hifv_finalcals.

    The extracted values are:
       - number of flagged solutions for bandpass and delay
    """
    result_cls = FinalcalsResults
    child_cls = None
    generating_task = Finalcals

    def handle(self, result: FinalcalsResults, context) -> Dict:
        val = self.calculate_value(result)
        vis = result.inputs['vis']
        ps = self.create_stat(vis, val)
        return ps

    def calculate_value(self, result: FinalcalsResults) -> Dict:
        """
        Extract values for pipeline statistics.

        Args:
            result: FinalcalsResults object

        Returns:
            Dict[str, int]
        """
        d = {}
        try:
            d['bandpass.flagged'] = int(result.flaggedSolnApplycalbandpass['all']['flagged'])
            d['delay.flagged'] = int(result.flaggedSolnApplycaldelay['all']['flagged'])

        except Exception as e:
            LOG.info(f"Some information missing from FinalcalsResults: {e}")
            d = {}

        return d

    def create_stat(self, vis, val):
        longdescription = "Added for pipeline statistics: finalcals flagged solutions."
        ps1 = PipelineStatistic(name="finalcals_flagged",
                                value=val,
                                longdesc=longdescription,
                                level=PipelineStatisticLevel.EB)
        d = {}
        d[vis] = ps1
        return d


class SDBLFlagResultsStatsExtractor(ResultsStatsExtractor):
    """
    Pipeline statistics extractor for sd_blfrag.

    The extracted values are:
       - the number of flagged and scanned rows before this task
       - the number of flagged and scanned rows after this task
       - QA scores
    """
    result_cls = SDBLFlagResults
    child_cls = None
    generating_task = SDBLFlag

    def handle(self, result: SDBLFlagResults, context) -> Dict:
        val = self.calculate_value(result)
        vis = result.inputs['vis']
        ps = self.create_stat(vis, val)
        return ps

    def calculate_value(self, result: SDBLFlagResults) -> Dict:
        """
        Extract values for pipeline statistics.

        Args:
            result: SDBLFlagResults object
        
        Returns:
            Dict[str, Union[int, Dict]]
        """
        d = {}
        try:
            flag_dict = {}
            for summary in result.outcome['flagdata_summary']:
                name = None
                prop = None
                for k, v in summary.items():
                    if 'name' == k:
                        name = v
                    elif isinstance(v, dict):
                        prop = v
                if name is not None and prop is not None:
                    flag_dict[f'num_rows_flagged.{name}'] = int(prop['flagged'])
                    scan_dict = {}
                    for scan_id, v in prop['scan'].items():
                        scan_dict[f'scan_{scan_id}'] = int(v['flagged'])
                    if scan_dict:
                        flag_dict[f'scan.num_rows_flagged.{name}'] = scan_dict
            if flag_dict:
                d.update(flag_dict)

            # Extract QA scores
            if hasattr(result, 'qa') and result.qa and result.qa.pool:
                qa_entries = extract_qa_score_regression("sd_blflag", result)
                d.update(qa_entries)

        except Exception as e:
            LOG.info(f"Some information missing from SDBLFlagResults: {e}")
            d = {}

        return d

    def create_stat(self, vis, val):
        longdescription = "Added for pipeline statistics: SD baseline flagging summaries and QA scores."
        ps1 = PipelineStatistic(name="sd_blflag_flagging",
                                value=val,
                                longdesc=longdescription,
                                level=PipelineStatisticLevel.EB)
        d = {}
        d[vis] = ps1
        return d


class SDImagingResultsStatsExtractor(ResultsStatsExtractor):
    """
    Pipeline statistics extractor for sd_imaging.

    The extracted values are:
        - QA scores
    """
    result_cls = SDImagingResults
    child_cls = None
    generating_task = SDImaging

    def handle(self, result: SDImagingResults, context) -> Dict:
        val = self.calculate_value(result)
        if not val:
            return {}
        # For imaging, we may not have a single vis, so we need to handle it differently
        # Try to get vis from context or result
        vis = None
        if hasattr(result, 'inputs') and 'vis' in result.inputs:
            vis = result.inputs['vis']
        elif hasattr(result, 'vislist') and result.vislist:
            vis = result.vislist[0]
        
        if vis:
            ps = self.create_stat(vis, val)
            return ps
        return {}

    def calculate_value(self, result: SDImagingResults) -> Dict:
        """
        Extract values for pipeline statistics.

        Args:
            result: SDImagingResults object
        
        Returns:
            Dict[str, Dict]
        """
        d = {}
        try:
            # Extract QA scores
            if hasattr(result, 'qa') and result.qa and result.qa.pool:
                qa_entries = extract_qa_score_regression("sd_imaging", result)
                d.update(qa_entries)

        except Exception as e:
            LOG.info(f"Some information missing from SDImagingResults: {e}")
            d = {}

        return d

    def create_stat(self, vis, val):
        longdescription = "Added for pipeline statistics: SD imaging QA scores."
        ps1 = PipelineStatistic(name="sd_imaging_qa",
                                value=val,
                                longdesc=longdescription,
                                level=PipelineStatisticLevel.EB)
        d = {}
        d[vis] = ps1
        return d


class SDRestoredataResultsStatsExtractor(ResultsStatsExtractor):
    """
    Pipeline statistics extractor for sd_restoredata.

    The extracted values are:
        - the number of flagged and scanned rows after this task
        - QA scores
    """
    result_cls = SDRestoreDataResults
    child_cls = None
    generating_task = SDRestoreData

    def handle(self, result: SDRestoreDataResults, context) -> Dict:
        val = self.calculate_value(result)
        # For restoredata, we may have multiple sessions/mses
        # Create stats for each session/ms combination
        stats_list = []
        try:
            for session, mses in result.flagging_summaries.items():
                for ms_name, ms in mses.items():
                    session_val = {}
                    for target_name, target in ms.items():
                        if isinstance(target, dict):
                            target_dict = {'num_rows_flagged': int(target['flagged'])}
                            scan_dict = {}
                            for scan_id, v in target['scan'].items():
                                scan_dict[f'scan_{scan_id}'] = int(v['flagged'])
                            if scan_dict:
                                target_dict['scan'] = scan_dict
                            session_val[f'target_{target_name}'] = target_dict
                    
                    if session_val:
                        ps = self.create_stat(ms_name, session_val)
                        stats_list.append(ps)
            
            # Also add QA scores if present
            if hasattr(result, 'qa') and result.qa and result.qa.pool:
                qa_val = extract_qa_score_regression("sd_restoredata", result)
                if qa_val:
                    # Add QA to the first stats dict or create a new one
                    if stats_list:
                        for vis, stat in stats_list[0].items():
                            if isinstance(stat.value, dict):
                                stat.value.update(qa_val)
                    else:
                        # Create a new stat just for QA
                        default_vis = list(result.flagging_summaries.values())[0].keys()[0] if result.flagging_summaries else "unknown"
                        ps = self.create_stat(default_vis, qa_val)
                        stats_list.append(ps)
        except Exception as e:
            LOG.info(f"Error processing SDRestoreDataResults: {e}")
        
        # Return union of all stats
        if stats_list:
            return union([], stats_list[0]) if len(stats_list) == 1 else union([], stats_list)
        return []

    def calculate_value(self, result: SDRestoreDataResults) -> Dict:
        """
        Extract values for pipeline statistics.

        Args:
            result: SDRestoreDataResults object
        
        Returns:
            Dict[str, Dict]
        """
        d = {}
        try:
            for session, mses in result.flagging_summaries.items():
                for ms_name, ms in mses.items():
                    for target_name, target in ms.items():
                        if isinstance(target, dict):
                            d[f'session_{session}.{ms_name}.target_{target_name}.num_rows_flagged'] = int(target['flagged'])
                            for scan_id, v in target['scan'].items():
                                d[f'session_{session}.{ms_name}.target_{target_name}.scan_{scan_id}.num_rows_flagged'] = int(v['flagged'])

            # Extract QA scores
            if hasattr(result, 'qa') and result.qa and result.qa.pool:
                qa_entries = extract_qa_score_regression("sd_restoredata", result)
                d.update(qa_entries)

        except Exception as e:
            LOG.info(f"Some information missing from SDRestoreDataResults: {e}")
            d = {}

        return d

    def create_stat(self, vis, val):
        longdescription = "Added for pipeline statistics: SD restoredata flagging summaries and QA scores."
        ps1 = PipelineStatistic(name="sd_restoredata_flagging",
                                value=val,
                                longdesc=longdescription,
                                level=PipelineStatisticLevel.EB)
        d = {}
        d[vis] = ps1
        return d


def extract_qa_score_regression(prefix: str, result: Results) -> dict:
    """Extract QA scores from a TaskResults object and organize them into a structured dictionary.

    Args:
        prefix (str): Base string to prepend to each key in the output dictionary.
        result (Results): TaskResults Object containing QA pool data to be processed.

    Returns:
        dict: Dictionary with formatted keys mapping to metric scores and values.
            Keys follow the pattern: {prefix}.field_{field_id}.spw_{spw_id}.qa.{metric|score}.{metric_name}

    Examples:
        >>> result = Results(...)  # Assuming Results object with qa.pool
        >>> scores = extract_qa_score_regression("test", result)
        >>> # Resulting keys might look like: "test.field_data.spw_0.qa.metric.accuracy"
    
    """
    # Initialize a dictionary
    d = {}

    # Iterate through each QA score in the result's pool
    for qa_score in result.qa.pool:
        # Extract and clean metric name for use in keys
        metric_name = qa_score.origin.metric_name
        # Remove all non-word characters (everything except numbers and letters)
        metric_name = re.sub(r"[^\w\s]", '', metric_name)
        # Replace all runs of whitespace with a single dash
        metric_name = re.sub(r"\s+", '-', metric_name)

        metric_score, score_value = qa_score.origin.metric_score, qa_score.score

        data_select = "".join(
            f".{key}_" + "_".join(sorted(map(str, value)))
            for key, value in [("field", qa_score.applies_to.field), ("spw", qa_score.applies_to.spw)]
            if value
        )
        # Add metric score and value to dictionary with formatted keys
        d.update({
            f"{prefix}{data_select}.qa.metric.{metric_name}": metric_score,
            f"{prefix}{data_select}.qa.score.{metric_name}": score_value,
        })
    return d


def union(input: List, new: Union[Dict, List[Dict]]) -> List[Dict]:
    """
    Combines lst which is always a list, with new,
    which could be a list of PipelineStatistic objects
    or an individual PipelineStatistic object.
    """
    union = copy.deepcopy(input)

    if isinstance(new, list):
        for elt in new:
            union.append(elt)
    else:
        union.append(new)
    return union


def get_stats_from_results(context: Context, stats_collection: PipelineStatsCollection) -> None:
    """
    Gathers all possible pipeline statistics from results.
    """
    for results_proxy in context.results:
        results = results_proxy.read()
        handle_results = registry.handle(results, context)
        LOG.debug("Got stats from results: %s", handle_results)
        for elt in handle_results:
            for eb, stat in elt.items():
                stats_collection.add_stat(stat, eb=eb, level=PipelineStatisticLevel.EB, mous=context.get_oussid())
        LOG.debug("stats collection results so far: %s", stats_collection)


# This is the main interface for generating statistics.
def generate_stats(context: Context) -> Dict:
    """
    Gathers statistics from the context and results and returns a 
    representation of them as a dict.
    """
    # Gather context-based stats like project and pipeline run info
    LOG.info("Gathering pipeline stats from context")
    stats_collection = get_stats_from_context(context)

    # Gather stats from results objects
    LOG.info("Getting pipeline stats from results")
    get_stats_from_results(context, stats_collection)
    LOG.info("Adding stats from results to stats collection")

    # Construct dictionary representation of all pipeline stats
    LOG.info("Converting pipeline stats collection to dictionary")
    final_dict = stats_collection.to_dict()
    LOG.info("Returning final pipeline stats dictionary")

    return final_dict
