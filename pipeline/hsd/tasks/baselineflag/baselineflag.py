from __future__ import annotations

import collections
import os
from typing import TYPE_CHECKING, Any

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.sessionutils as sessionutils
import pipeline.infrastructure.utils as utils
import pipeline.infrastructure.vdp as vdp
from pipeline.domain import DataType
from pipeline.h.heuristics import fieldnames
from pipeline.h.tasks.applycal.applycal import reshape_flagdata_summary
from pipeline.infrastructure.utils import absolute_path
from pipeline.infrastructure import casa_tasks
from pipeline.infrastructure import task_registry
from . import worker
from .flagsummary import SDBLFlagSummary
from .. import common
from ..common import utils as sdutils

if TYPE_CHECKING:
    from numbers import Real

    from pipeline.infrastructure import Context

LOG = infrastructure.logging.get_logger(__name__)


class SDBLFlagInputs(vdp.StandardInputs):
    """
    Inputs for single dish flagging
    """
    def __to_numeric(self, val: Any) -> Real | str | None:
        """Convert any value into numeric.

        Utility method for VisDependentProperty.

        Args:
            val: Any value

        Returns:
            Numeric value
        """
        return sdutils.to_numeric(val)

    def __to_bool(self, val: Any) -> bool:
        """Convert any value into boolean.

        Utility method for VisDependentProperty.

        Args:
            val: Any value

        Returns:
            Boolean value
        """
        return sdutils.to_bool(val)

    def __to_int(self, val: Any) -> int:
        """Convert any value into integer.

        Utility method for VisDependentProperty.

        Args:
            val: Any value

        Returns:
            Integer value
        """
        return int(val)

    def __to_list(self, val: Any) -> list[int]:
        """Convert any value into integer list.

        Utility method for VisDependentProperty.

        Args:
            val: Any value

        Returns:
            Integer list
        """
        return sdutils.to_list(val)

    # Search order of input vis
    processing_data_type = [DataType.ATMCORR,
                            DataType.REGCAL_CONTLINE_ALL, DataType.RAW ]

    parallel = sessionutils.parallel_inputs_impl()

    spw = vdp.VisDependentProperty(default='')
    intent = vdp.VisDependentProperty(default='TARGET')
    iteration = vdp.VisDependentProperty(default=5, fconvert=__to_int)
    edge = vdp.VisDependentProperty(default=[0, 0], fconvert=__to_list)
    flag_tsys = vdp.VisDependentProperty(default=True, fconvert=__to_bool)
    tsys_thresh = vdp.VisDependentProperty(default=3.0, fconvert=__to_numeric)
    flag_prfre = vdp.VisDependentProperty(default=True, fconvert=__to_bool)
    prfre_thresh = vdp.VisDependentProperty(default=6.0, fconvert=__to_numeric)
    flag_pofre = vdp.VisDependentProperty(default=True, fconvert=__to_bool)
    pofre_thresh = vdp.VisDependentProperty(default=2.6666, fconvert=__to_numeric)
    flag_prfr = vdp.VisDependentProperty(default=True, fconvert=__to_bool)
    prfr_thresh = vdp.VisDependentProperty(default=9.0, fconvert=__to_numeric)
    flag_pofr = vdp.VisDependentProperty(default=True, fconvert=__to_bool)
    pofr_thresh = vdp.VisDependentProperty(default=8.0, fconvert=__to_numeric)
    flag_prfrm = vdp.VisDependentProperty(default=True, fconvert=__to_bool)
    prfrm_thresh = vdp.VisDependentProperty(default=11.0, fconvert=__to_numeric)
    prfrm_nmean = vdp.VisDependentProperty(default=5, fconvert=__to_int)
    flag_pofrm = vdp.VisDependentProperty(default=True, fconvert=__to_bool)
    pofrm_thresh = vdp.VisDependentProperty(default=10.0, fconvert=__to_numeric)
    pofrm_nmean = vdp.VisDependentProperty(default=5, fconvert=__to_int)
    plotflag = vdp.VisDependentProperty(default=True, fconvert=__to_bool)

    @vdp.VisDependentProperty
    def infiles(self) -> str | list[str] | None:
        """Name of input MS.

        This is just an alias of vis.

        Returns:
            MS name or list of MS names.
        """
        return self.vis

    @infiles.convert
    def infiles(self, value: str | list[str] | None) -> str | list[str] | None:
        """Additional conversion operation on infiles.

        It doesn't apply any conversion. Instead, this ensures
        synchronization of infiles with vis.

        Args:
            value: Original value.

        Returns:
            Converted value.
        """
        self.vis = value
        return value

    antenna = vdp.VisDependentProperty(default='')

    @antenna.convert
    def antenna(self, value: str | None) -> str:
        """Make antenna selection consistent with vis.

        Args:
            value: Original antenna selection.

        Returns:
            Updated antenna selection.
        """
        antennas = self.ms.get_antenna(value)
        # if all antennas are selected, return ''
        if len(antennas) == len(self.ms.antennas):
            return ''
        return utils.find_ranges([a.id for a in antennas])
#         return ','.join([str(a.id) for a in antennas])

    @vdp.VisDependentProperty
    def field(self):
        """Define default field selection.

        Default field selection is constructed from vis
        and observing intent.

        Returns:
            Default field selection.
        """
        # this will give something like '0542+3243,0343+242'
        field_finder = fieldnames.IntentFieldnames()
        intent_fields = field_finder.calculate(self.ms, self.intent)

        # run the answer through a set, just in case there are duplicates
        fields = set()
        fields.update(utils.safe_split(intent_fields))

        return ','.join(fields)

    @vdp.VisDependentProperty
    def pol(self):
        """Define default polarization selection.

        Default polarization selection is constructed
        from vis and spw.

        Returns:
            Default polarization selection.
        """
        # need to convert input (virtual) spw into real spw
        real_spw = sdutils.convert_spw_virtual2real(self.context, self.spw, [self.ms])[self.vis]
        selected_spwids = [int(spwobj.id) for spwobj in self.ms.get_spectral_windows(real_spw, with_channels=True)]
        pols = set()
        for idx in selected_spwids:
            pols.update(self.ms.get_data_description(spw=idx).corr_axis)

        return ','.join(pols)

    #  docstring and type hints: supplements hsd_blflag
    def __init__(
            self,
            context: Context,
            output_dir: str | None = None,
            iteration: str | int | None = None,
            edge: str | int | list[int] | None = None,
            flag_tsys: str | bool | None = None,
            tsys_thresh: str | int | float | None = None,
            flag_prfre: str | bool | None = None,
            prfre_thresh: str | int | float | None = None,
            flag_pofre: str | bool | None = None,
            pofre_thresh: str | int | float | None = None,
            flag_prfr: str | bool | None = None,
            prfr_thresh: str | int | float | None = None,
            flag_pofr: str | bool | None = None,
            pofr_thresh: str | int | float | None = None,
            flag_prfrm: str | bool | None = None,
            prfrm_thresh: str | int | float | None = None,
            prfrm_nmean: str | int | None = None,
            flag_pofrm: str | bool | None = None,
            pofrm_thresh: str | int | float | None = None,
            pofrm_nmean: str | int | None = None,
            plotflag: str | bool | None = None,
            infiles: str | list[str] | None = None,
            antenna: str | list[str] | None = None,
            field: str | list[str] | None = None,
            spw: str | list[str] | None = None,
            pol: str | list[str] | None = None,
            parallel: bool | str | None = None,
            ):
        """Construct SDBLFlagInputs instance.

        Args:
            context: Pipeline context object containing state information.

            output_dir: Output directory.

            iteration: Number of iterations to perform sigma clipping
                to calculate threshold value of flagging.

                Default: None (equivalent to 5.0)

            edge: Number of channels to be dropped from the edge.
                The value must be a list of integer with length of one or
                two. If list length is one, same number will be applied
                both side of the band.

                Example: [10,20], [10]

                Default: None (equivalent to [0, 0])

            flag_tsys: Activate (True) or deactivate (False) Tsys flag.
                Default is None which is equivalent to True.

            tsys_thresh: Threshold value for Tsys flag.
                Default is None which sets 3.0 as a threshold.

            flag_prfre: Activate (True) or deactivate (False) flag by
                expected rms of pre-fit spectra.
                Default is None which is equivalent to True.

            prfre_thresh: Threshold value for flag by expected rms of
                pre-fit spectra. Default is None which sets 3.0 to a threshold.

            flag_pofre: Activate (True) or deactivate (False) flag by
                expected rms of post-fit spectra.
                Default is None which is equivalent to True.

            pofre_thresh: Threshold value for flag by expected rms of
                post-fit spectra. Default is None which sets 1.333 to a threshold.

            flag_prfr: Activate (True) or deactivate (False) flag by
                rms of pre-fit spectra.
                Default is None which is equivalent to True.

            prfr_thresh: Threshold value for flag by rms of pre-fit spectra.
                Default is None which sets 4.5 to a threshold.

            flag_pofr: Activate (True) or deactivate (False) flag by
                rms of post-fit spectra.
                Default is None which is equivalent to True.

            pofr_thresh: Threshold value for flag by rms of post-fit spectra.
                Default is None which sets 4.0 to a threshold.

            flag_prfrm: Activate (True) or deactivate (False) flag by
                running mean of pre-fit spectra.
                Default is None which is equivalent to True.

            prfrm_thresh: Threshold value for flag by running mean of pre-fit spectra.
                Default is None which sets 5.5 to a threshold.

            prfrm_nmean: Number of channels for running mean of pre-fit spectra.
                Default is None which sets 5 channels for running mean.

            flag_pofrm: Activate (True) or deactivate (False) flag by
                running mean of post-fit spectra.
                Default is None which is equivalent to True.

            pofrm_thresh: Threshold value for flag by running mean of post-fit spectra.
                Default is None which sets 5.0 to a threshold.

            pofrm_nmean: Number of channels for running mean of post-fit spectra.
                Default is None which sets 5 channels for running mean.

            plotflag: True to plot result of data flagging.
                Default is None which is equivalent to True.

            infiles: ASDM or MS files to be processed. This parameter behaves
                as data selection parameter. The name specified by infiles must be
                registered to context before you run hsd_blflag.

                Default: None (process all registered data)

            antenna: Data selection by antenna names or ids.

                Example: 'PM03,PM04', '' (all antennas)

                Default: None (process all antennas)

            field: Data selection by field names or ids.

                Example: '`*Sgr*,M100`', '' (all fields)

                Default: None (process all science fields)

            spw: Data selection by spw ids.

                Example: '3,4' (spw 3 and 4), '' (all spws)

                Default: None (process all science spws)

            pol: Data selection by polarizations.

                Example: 'XX,YY' (correlation XX and YY), '' (all polarizations)

                Default: None (process all polarizations)

            parallel: Execute using CASA HPC functionality, if available.

                Options: 'automatic', 'true', 'false', True, False

                Default: None (equivalent to 'automatic')

        """
        super().__init__()

        # context and vis/infiles must be set first so that properties that require
        # domain objects can be function
        self.context = context
        self.infiles = infiles
        self.output_dir = output_dir
        # task specific parameters
        self.iteration = iteration
        self.edge = edge
        self.flag_tsys = flag_tsys
        self.tsys_thresh = tsys_thresh
        self.flag_prfre = flag_prfre
        self.prfre_thresh = prfre_thresh
        self.flag_pofre = flag_pofre
        self.pofre_thresh = pofre_thresh
        self.flag_prfr = flag_prfr
        self.prfr_thresh = prfr_thresh
        self.flag_pofr = flag_pofr
        self.pofr_thresh = pofr_thresh
        self.flag_prfrm = flag_prfrm
        self.prfrm_thresh = prfrm_thresh
        self.prfrm_nmean = prfrm_nmean
        self.flag_pofrm = flag_pofrm
        self.pofrm_thresh = pofrm_thresh
        self.pofrm_nmean = pofrm_nmean
        self.plotflag = plotflag
        self.antenna = antenna
        self.field = field
        self.spw = spw
        self.pol = pol
        self.parallel = parallel

        ### Default Flag rule
        from . import SDFlagRule
        self.FlagRuleDictionary = SDFlagRule.SDFlagRule
        # MUST NOT configure FlagRuleDictionary here.

    def _configureFlagRule(self):
        """A private method to convert input parameters to FlagRuleDictionary"""
        d = {'TsysFlag': (self.flag_tsys, [self.tsys_thresh]),
             'RmsPreFitFlag': (self.flag_prfr, [self.prfr_thresh]),
             'RmsPostFitFlag': (self.flag_pofr, [self.pofr_thresh]),
             'RmsExpectedPreFitFlag': (self.flag_prfre, [self.prfre_thresh]),
             'RmsExpectedPostFitFlag': (self.flag_pofre, [self.pofre_thresh]),
             'RunMeanPreFitFlag': (self.flag_prfrm, [self.prfrm_thresh, self.prfrm_nmean]),
             'RunMeanPostFitFlag': (self.flag_pofrm, [self.pofrm_thresh, self.pofrm_nmean])}
        keys = ['Threshold', 'Nmean']
        for k, v in d.items():
            (b, p) = v
            if b == True:
                self.activateFlagRule(k)
                for i in range(len(p)):
                    self.FlagRuleDictionary[k][keys[i]] = p[i]
            elif b == False:
                self.deactivateFlagRule(k)
            else:
                raise RuntimeError("Invalid flag operation definition for %s" % k)

    def activateFlagRule(self, key):
        """Activates a flag type specified by the input parameter in FlagRuleDictionary"""
        if key in self.FlagRuleDictionary:
            self.FlagRuleDictionary[key]['isActive'] = True
        else:
            raise RuntimeError('Error: %s not in predefined Flagging Rules' % key)

    def deactivateFlagRule(self, key):
        """Deactivates a flag type specified by the input parameter in FlagRuleDictionary"""
        if key in self.FlagRuleDictionary:
            self.FlagRuleDictionary[key]['isActive'] = False
        else:
            raise RuntimeError('Error: %s not in predefined Flagging Rules' % key)


class SDBLFlagResults(common.SingleDishResults):
    """
    The results of SDFalgData
    """
    def __init__(self, task=None, success=None, outcome=None):
        super().__init__(task, success, outcome)

    def merge_with_context(self, context):
        super().merge_with_context(context)

    def _outcome_name(self):
        return 'none'


class SerialSDBLFlag(basetask.StandardTaskTemplate):
    """
    Single dish flagging class.
    """
    ##################################################
    # Note
    # The class uses _handle_multiple_vis framework.
    # Method, prepare() is called per MS. Inputs.ms
    # holds "an" MS instance to be processed.
    ##################################################
    Inputs = SDBLFlagInputs

    def prepare(self):
        """
        Iterates over reduction group and invoke flagdata worker function in each clip_niteration.
        """
        inputs = self.inputs
        context = inputs.context
        # name of MS to process
        cal_name = inputs.ms.name
        bl_list = context.observing_run.get_measurement_sets_of_type([DataType.BASELINED])
        match = sdutils.match_origin_ms(bl_list, inputs.ms.origin_ms)
        bl_name = match.name if match is not None else cal_name
        in_ant = inputs.antenna
        in_spw = inputs.spw
        real_spw = sdutils.convert_spw_virtual2real(context, in_spw, [self.inputs.ms])[self.inputs.vis]
        LOG.trace(f'ms "{self.inputs.ms.basename}" in_spw="{in_spw}" real_spw="{real_spw}"')
        in_field = inputs.field
        in_pol = '' if inputs.pol in ['', '*'] else inputs.pol.split(',')
        clip_niteration = inputs.iteration
        reduction_group = context.observing_run.ms_reduction_group
        # configure FlagRuleDictionary
        # this has to be done in runtime rather than in Inputs.__init__
        # to accommodate later overwrite of parameters.
        inputs._configureFlagRule()
        flag_rule = inputs.FlagRuleDictionary

        LOG.debug("Flag Rule for %s: %s" % (cal_name, flag_rule))

        # sumarize flag before execution
        full_intent = utils.to_CASA_intent(inputs.ms, inputs.intent)
        flagdata_summary_job = casa_tasks.flagdata(vis=bl_name, mode='summary',
                                                   antenna=in_ant, field=in_field,
                                                   spw=real_spw, intent=full_intent,
                                                   spwcorr=True, fieldcnt=True,
                                                   name='before')
        stats_before = self._executor.execute(flagdata_summary_job)

        # collection of field, antenna, and spw ids in reduction group per MS
        registry = collections.defaultdict(sdutils.RGAccumulator)

        # loop over reduction group (spw and source combination)
        flagResult = []
        for group_id, group_desc in reduction_group.items():
            LOG.debug('Processing Reduction Group %s' % group_id)
            LOG.debug('Group Summary:')
            for m in group_desc:
                LOG.debug('\t%s: Antenna %d (%s) Spw %d Field %d (%s)' %
                          (os.path.basename(m.ms.name), m.antenna_id,
                           m.antenna_name, m.spw_id, m.field_id, m.field_name))

            nchan = group_desc.nchan
            if nchan == 1:
                LOG.info('Skipping a group of channel averaged spw')
                continue

            field_sel = ''
            if len(in_field) == 0:
                # fine, just go ahead
                field_sel = in_field
            elif group_desc.field_name in [x.strip('"') for x in in_field.split(',')]:
                # pre-selection of the field name
                field_sel = group_desc.field_name
            else:
                # no field name is included in in_field, skip
                LOG.info('Skip reduction group {:d}'.format(group_id))
                continue

            # Which group in group_desc list should be processed
            member_list = list(common.get_valid_ms_members(group_desc, [cal_name], in_ant, field_sel, real_spw))
            LOG.trace('group %s: member_list=%s' % (group_id, member_list))

            # skip this group if valid member list is empty
            if len(member_list) == 0:
                LOG.info('Skip reduction group %d' % group_id)
                continue

            member_list.sort()  # list of group_desc IDs to flag
            antenna_list = [group_desc[i].antenna_id for i in member_list]
            spwid_list = [group_desc[i].spw_id for i in member_list]
            ms_list = [group_desc[i].ms for i in member_list]
            fieldid_list = [group_desc[i].field_id for i in member_list]
            temp_dd_list = [ms_list[i].get_data_description(spw=spwid_list[i])
                            for i in range(len(member_list))]
            pols_list = [[corr for corr in ddobj.corr_axis if (in_pol == '' or corr in in_pol)]
                         for ddobj in temp_dd_list]
            del temp_dd_list

            for i in range(len(member_list)):
                member = group_desc[member_list[i]]
                registry[member.ms].append(field_id=member.field_id,
                                           antenna_id=member.antenna_id,
                                           spw_id=member.spw_id,
                                           pol_ids=pols_list[i])

        # per-MS loop
        plots = []
        for msobj, accumulator in registry.items():
            if absolute_path(cal_name) == absolute_path(bl_name):
                LOG.warning("%s is not yet baselined. Skipping flag by post-fit statistics for the data."
                            " MASKLIST will also be cleared up. You may go on flagging but the statistics"
                            " will contain line emission." % inputs.ms.basename)

            antenna_list = accumulator.get_antenna_id_list()
            fieldid_list = accumulator.get_field_id_list()
            spwid_list = accumulator.get_spw_id_list()
            pols_list = accumulator.get_pol_ids_list()

            LOG.info("*"*60)
            LOG.info('Members to be processed:')
            for antenna_id, field_id, spw_id, pol_ids in zip(antenna_list, fieldid_list, spwid_list, pols_list):
                LOG.info("\t{}:: Antenna {} ({}) Spw {} Field {} ({}) Pol '{}'".format(
                    msobj.basename,
                    antenna_id,
                    msobj.antennas[antenna_id].name,
                    spw_id,
                    field_id,
                    msobj.fields[field_id].name,
                    ','.join(pol_ids)))

            LOG.info("*"*60)

            nchan = 0
            # Calculate flag and update DataTable
            flagging_inputs = worker.SDBLFlagWorkerInputs(
                context, clip_niteration,
                msobj.name, antenna_list, fieldid_list,
                spwid_list, pols_list, nchan, flag_rule)
            flagging_task = worker.SDBLFlagWorker(flagging_inputs)

            flagging_results = self._executor.execute(flagging_task, merge=False)
            thresholds = flagging_results.outcome
            # Summary
            if not basetask.DISABLE_WEBLOG:
                renderer = SDBLFlagSummary(context, msobj,
                                           antenna_list, fieldid_list, spwid_list,
                                           pols_list, thresholds, flag_rule)
                result, plot_list = self._executor.execute(renderer, merge=False)
                flagResult += result
                plots.extend( plot_list )

        # Calculate flag fraction after operation.
        # flag summary for By Topic Page (all data in MS are needed)
        flagkwargs = ["spw='{!s}' intent='{}' fieldcnt=True mode='summary' name='AntSpw{:0>3}'".format(spw.id, full_intent, spw.id)
                              for spw in self.inputs.ms.get_spectral_windows()]
        # add the summary after flagging with data selection
        flagkwargs.append(f"antenna='{in_ant}' field='{in_field}' spw='{real_spw}' intent='{full_intent}' spwcorr=True fieldcnt=True mode='summary' name='after'")
        detailed_flag_job = casa_tasks.flagdata(vis=bl_name, mode='list', inpfile=flagkwargs, flagbackup=False)
        detailed_flag_result = self._executor.execute(detailed_flag_job)
        # Pop the summary with data selection.
        stats_after = None
        for k, v in detailed_flag_result.items():
            if v['name'] == 'after':
                stats_after = detailed_flag_result.pop(k)
                break
        assert stats_after is not None

        outcome = {'flagdata_summary': [stats_before, stats_after],
                   'summary': flagResult,
                   'plots': plots }
        results = SDBLFlagResults(task=self.__class__,
                                  success=True,
                                  outcome=outcome)
        results.flagsummary = reshape_flagdata_summary(detailed_flag_result)

        return results

    def analyse(self, result):
        return result

@task_registry.set_equivalent_casa_task('hsd_blflag')
@task_registry.set_casa_commands_comment(
    'Perform row-based flagging based on noise level and quality of spectral baseline subtraction.\n'
    'This stage performs a pipeline calculation without running any CASA commands to be put in this file.'
)
class SDBLFlag(sessionutils.ParallelTemplate):
    Inputs = SDBLFlagInputs
    Task = SerialSDBLFlag
