from __future__ import annotations

import abc
import collections.abc
import copy
import datetime
import enum
import re
from typing import TYPE_CHECKING

import numpy as np

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.renderer.htmlrenderer as htmlrenderer
import pipeline.infrastructure.utils as utils
from pipeline import environment
from pipeline.domain import measures
from pipeline.domain.datatype import DataType
from pipeline.h.tasks.common import flagging_renderer_utils as flagutils
from pipeline.hifa.tasks.flagging.flagdeteralma import FlagDeterALMAResults
from pipeline.infrastructure.renderer import regression

LOG = infrastructure.logging.get_logger(__name__)

if TYPE_CHECKING:
    from numpy import generic
    from numpy.typing import NDArray

    from pipeline.domain.measurementset import MeasurementSet
    from pipeline.infrastructure.basetask import Results, ResultsList
    from pipeline.infrastructure.launcher import Context


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
    def __init__(self, name: str, value: str | int | float | list | dict | set | np.int64 | NDArray[generic],
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

    def to_dict(self) -> dict:
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

    def add_stats(self, stats: list[PipelineStatistic], mous: str = None, source: str = None,
                  level: PipelineStatisticLevel = None, eb: str = None, spw: str = None):
        for stat in stats:
            self.add_stat(stat, level=level, mous=mous, source=source, eb=eb, spw=spw)

    def to_dict(self) -> dict:
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


def _generate_header() -> dict:
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
    timestamps.append(datetime.datetime.now(datetime.timezone.utc))
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


def _get_mous_values(context, mous: str, ms_list: list[MeasurementSet],
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


def _get_eb_values(context, mous: str, ms_list: list[MeasurementSet],
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


def _get_spw_values(context, mous: str, ms_list: list[MeasurementSet],
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


def _get_source_values(context, mous: str, ms_list: list[MeasurementSet],
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
class ResultsStatsExtractor(abc.ABC):
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

    def is_handler_for(self, result: Results | ResultsList) -> bool:
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


class StatsExtractorRegistry:
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

    def handle(self, result: Results | ResultsList, context=None):
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

    def handle(self, result: FlagDeterALMAResults, context) -> dict:
        value = self.calculate_value(result, context)
        ps = self.create_stat(value)
        return ps

    def calculate_value(self, result: FlagDeterALMAResults, context: Context) -> dict:
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

    def create_stat(self, value_dict: dict) -> dict:
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


def union(input: list, new: dict | list[dict]) -> list[dict]:
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
def generate_stats(context: Context) -> dict:
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
