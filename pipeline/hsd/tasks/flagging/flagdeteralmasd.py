from __future__ import annotations

import collections
import itertools
import os
import re
import shutil
import string
from typing import TYPE_CHECKING, Generator, List, Optional, Union

import numpy as np

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.utils as utils
import pipeline.infrastructure.vdp as vdp
import pipeline.infrastructure.sessionutils as sessionutils
from pipeline.domain import DataTable
from pipeline.h.tasks.flagging import flagdeterbase
from pipeline.infrastructure import casa_tools
from pipeline.infrastructure import casa_tasks
from pipeline.infrastructure import task_registry
from pipeline.infrastructure.displays import pointing
from pipeline.hsd.heuristics.pointing_outlier import PointingOutlierHeuristics
from pipeline.hsd.tasks.common.flagcmd_util import datatable_rowid_to_timerange

if TYPE_CHECKING:
    from pipeline.domain import SpectralWindow
    from pipeline.infrastructure import Context

LOG = infrastructure.get_logger(__name__)

PointingOutlierStats = collections.namedtuple(
    "PointingOutlierStats",
    ["cx", "cy", "median_distance", "factor",
     "outliers", "timerange", "separations"]
)

class FlagDeterALMASingleDishInputs(flagdeterbase.FlagDeterBaseInputs):
    """
    FlagDeterALMASingleDishInputs defines the inputs for the FlagDeterALMASingleDish pipeline task.
    """
    parallel = sessionutils.parallel_inputs_impl()

    autocorr = vdp.VisDependentProperty(default=False)
    edgespw = vdp.VisDependentProperty(default=True)
    fracspw = vdp.VisDependentProperty(default='1.875GHz')
    fracspwfps = vdp.VisDependentProperty(default=0.048387)

    @vdp.VisDependentProperty
    def intents(self) -> str:
        """Define default list of intents to be flagged."""
        # return just the unwanted intents that are present in the MS
        intents_to_flag = {'POINTING', 'FOCUS', 'ATMOSPHERE', 'SIDEBAND',
                           'UNKNOWN', 'SYSTEM_CONFIGURATION', 'CHECK'}
        return ','.join(self.ms.intents.intersection(intents_to_flag))

    template = vdp.VisDependentProperty(default=True)

    @flagdeterbase.FlagDeterBaseInputs.filetemplate.postprocess
    def filetemplate(self, unprocessed: Union[str, List[str]]) -> str:
        """Post-process filetemplate.

        This ensures filetemplate value is string.

        Args:
            unprocessed: Unprocessed value of filetemplate.

        Returns:
            String value of filetemplate.
        """
        if isinstance(unprocessed, list) and len(unprocessed) == 1:
            value = unprocessed[0]
        else:
            value = unprocessed
        return value

    pointing = vdp.VisDependentProperty(default=True)
    incompleteraster = vdp.VisDependentProperty(default=True)

    @vdp.VisDependentProperty
    def filepointing(self) -> str:
        """Define defualt name of pointing flag file.

        Returns:
            Default name of pointing flag file.
        """
        vis_root = os.path.splitext(self.vis)[0]
        return vis_root + '.flagpointing.txt'

    # New property for QA0 / QA2 flags
    qa0 = vdp.VisDependentProperty(default=True)
    qa2 = vdp.VisDependentProperty(default=True)

    # docstring and type hints: supplements hsd_flagdata
    def __init__(self,
                 context: 'Context',
                 vis: Optional[List[str]] = None,
                 output_dir: Optional[str] = None,
                 flagbackup: Optional[Union[str, bool]] = None,
                 autocorr: Optional[Union[str, bool]] = None,
                 shadow: Optional[Union[str, bool]] = None,
                 scan: Optional[Union[str, bool]] = None,
                 scannumber: Optional[str] = None,
                 intents: Optional[str] = None,
                 edgespw: Optional[Union[str, bool]] = None,
                 fracspw: Optional[str] = None,
                 fracspwfps: Optional[Union[str, float]] = None,
                 online: Optional[Union[str, bool]] = None,
                 fileonline: Optional[str] = None,
                 template: Optional[Union[str, bool]] = None,
                 filetemplate: Optional[str] = None,
                 pointing: Optional[Union[str, bool]] = None,
                 filepointing: Optional[str] = None,
                 incompleteraster: Optional[Union[str, bool]] = None,
                 hm_tbuff: Optional[str] = None,
                 tbuff: Optional[Union[str, float]] = None,
                 qa0: Optional[Union[str, bool]] = None,
                 qa2: Optional[Union[str, bool]] = None,
                 parallel: Optional[Union[str, bool]] = None):
        """Construct FlagDeterALMASingleDishInputs instance.

        Args:
            context: Pipeline context object containing state information.

            vis: The list of input MeasurementSets. Defaults to the list of
                MeasurementSets defined in the pipeline context.

            output_dir: Output directory.

            flagbackup: Back up any pre-existing flags before applying new ones.

                Default: None (equivalent to True)

            autocorr: Flag autocorrelation data.

                Default: None (equivalent to False)

            shadow: Flag shadowed antennas.

                Default: None (equivalent to True)

            scan: Flag a list of scans and intents specified by scannumber and intents.

                Default: None (equivalent to True)

            scannumber: A string containing a comma delimited list of scans to be flagged.

                Default: None (equivalent to '')

            intents: A string containing a comma delimited list of intents
                against which the scans to be flagged are matched.
                Defaults to intents that are not relevant to pipeline processing.

                Example: `'*BANDPASS*'`

            edgespw: Flag the edge spectral window channels.

                Default: None (equivalent to True)

            fracspw: Fraction of the baseline correlator TDM edge channels to be flagged.

                Default: None (equivalent to 0.03125)

            fracspwfps: Fraction of the ACA correlator TDM edge channels to be flagged.

                Default: None (equivalent to 0.048387)

            online: Apply the online flags.

                Default: None (equivalent to True)

            fileonline: File containing the online flags. These are computed
                by the h_init or hsd_importdata data tasks. If the online flags files
                are undefined a name of the form 'msname.flagonline.txt' is assumed.

            template: Apply a flagging template.

                Default: None (equivalent to True)

            filetemplate: The name of a text file that contains the flagging
                template for RFI, birdies, telluric lines, etc.  If the
                template flags files is undefined a name of the form
                'msname.flagtemplate.txt' is assumed.

            pointing: Apply a flagging template for pointing flag.

                Default: None (equivalent to True)

            filepointing: The name of a text file that contains the flagging
                template for pointing flag. If the template flags files is
                undefined a name of the form 'msname.flagpointing.txt' is assumed.

            incompleteraster: Apply commands to flag incomplete raster sequence.
                If this is False, relevant commands in filepointing are
                simply commented out.

                Default: None (equivalent to True)

            hm_tbuff: The heuristic for computing the default time interval
                padding parameter. The options are 'halfint' and 'manual'.
                In 'halfint' mode tbuff is set to half the maximum of the
                median integration time of the science and calibrator target
                observations.

                Default: None (equivalent to 'halfint')

            tbuff: The time in seconds used to pad flagging command time
                intervals if hm_tbuff='manual'.

                Default: None (equivalent to 0.0)

            qa0: QA0 flags

            qa2: QA2 flags

            parallel: Execute using CASA HPC functionality, if available.

                Options: 'automatic', 'true', 'false', True, False

                Default: None (equivalent to 'automatic')
        """
        super().__init__(
            context, vis=vis, output_dir=output_dir, flagbackup=flagbackup, autocorr=autocorr, shadow=shadow, scan=scan,
            scannumber=scannumber, intents=intents, edgespw=edgespw, fracspw=fracspw, fracspwfps=fracspwfps,
            online=online, fileonline=fileonline, template=template, filetemplate=filetemplate, hm_tbuff=hm_tbuff,
            tbuff=tbuff)

        # solution parameters
        self.qa0 = qa0
        self.qa2 = qa2

        # pointing flag
        self.pointing = pointing
        self.filepointing = filepointing
        self.incompleteraster = incompleteraster

        # Tier-0 parallelization
        self.parallel = parallel

    def to_casa_args(self):
        # Initialize the arguments from the inherited
        # FlagDeterBaseInputs() class
        task_args = super().to_casa_args()

        # Return the tflagdata task arguments
        return task_args


class FlagDeterALMASingleDishResults(flagdeterbase.FlagDeterBaseResults):

    def __init__(
            self,
            summaries: list[dict],
            flagcmds: list[str],
            pointing_outlier_stats: dict[tuple[int, int], PointingOutlierStats]):
        """Initialize results object for hsd_flagdata.

        Args:
            summaries: List of flagging summaries.
            flagcmds: List of flagging commands
            pointing_outlier_stats: Statistics of pointing outliers.
        """
        super().__init__(summaries, flagcmds)
        self.pointing_outlier_stats = pointing_outlier_stats

    def merge_with_context(self, context):
        # call parent's method
        super().merge_with_context(context)

        # regenerate pointing plots
        if not basetask.DISABLE_WEBLOG:
            ephem_names = casa_tools.measures.listcodes(casa_tools.measures.direction())['extra']
            valid_ephem_names = [x for x in ephem_names if x != 'COMET']
            LOG.info('Regenerate pointing plots to update flag information')
            msobj = context.observing_run.get_ms(self.inputs['vis'])
            task = pointing.SingleDishPointingChart(context, msobj)
            for antenna in msobj.antennas:
                for target, reference in msobj.calibration_strategy['field_strategy'].items():
                    LOG.debug('target field id %s / reference field id %s' % (target, reference))
                    task.plot(revise_plot=True, antenna=antenna, target_field_id=target,
                              reference_field_id=reference, target_only=True)
                    task.plot(revise_plot=True, antenna=antenna, target_field_id=target,
                              reference_field_id=reference, target_only=False)

                    # if the target is ephemeris, offset pointing pattern should also be plotted
                    target_field = msobj.fields[target]
                    source_name = target_field.source.name
                    offset_pointings = []
                    if source_name.upper() in valid_ephem_names:
                        plotres = task.plot(revise_plot=True, antenna=antenna, target_field_id=target,
                                            reference_field_id=reference, target_only=True, ofs_coord=True)
                        if plotres is not None:
                            offset_pointings.append(plotres)


def update_flag_pointing(filename: str, flag_incomplete_raster: bool):
    """Disable "uniform_image_rms" flag commands if necessary.

    Args:
        filename: Name of the flag commands file.
        flag_incomplete_raster: Set True to disable "uniform_image_rms"
                                flag commands.
    """
    tmpfile = filename + '.bak'
    try:
        shutil.copy(filename, tmpfile)
        reason = "reason='SDPL:uniform_image_rms'"
        with open(filename, 'r') as f:

            if flag_incomplete_raster is True:
                # uncomment commands
                gen = map(
                    lambda x: x.lstrip('#') if x.find(reason) != -1 and x.startswith('#') else x, f
                )
            else:
                LOG.info(f'Disabling flag commands for reason "{reason}')
                # comment out commands
                gen = map(
                    lambda x: f'#{x}' if x.find(reason) != -1 and not x.startswith('#') else x, f
                )

            lines = list(gen)

        with open(filename, 'w') as f:
            f.writelines(lines)

    except Exception:
        shutil.copy(tmpfile, filename)

    finally:
        if os.path.exists(tmpfile):
            os.remove(tmpfile)


class SerialFlagDeterALMASingleDish(flagdeterbase.FlagDeterBase):

    # Make the member functions of the FlagDeterALMASingleDishInputs() class member
    # functions of this class
    Inputs = FlagDeterALMASingleDishInputs

    # Flag edge channels if bandwidth exceeds bandwidth_limit
    # Currently, default bandwidth limit is set to 1.875GHz but it is
    # controllable via parameter 'fracspw'
    @property
    def bandwidth_limit(self):
        if isinstance(self.inputs.fracspw, str):
            return casa_tools.quanta.convert(self.inputs.fracspw, 'Hz')['value']
        else:
            return 1.875e9  # 1.875GHz

    def prepare(self) -> FlagDeterALMASingleDishResults:
        """Generates results object."""
        if self.inputs.pointing:
            # save flag status before flagging
            self._execute_flagmanager(mode='save')

        try:
            # pre-apply deterministic flagging
            results = self._apply_deterministic_flagging()

            # run pointing outlier heuristic for each target field
            outlier_stats = self._detect_pointing_outliers()

            # check if pointing outliers are detected or not
            if len(outlier_stats) > 0:
                for (field_id, antenna_id), stats in outlier_stats.items():
                    field = self.inputs.ms.get_fields(field_id=field_id)[0]
                    antenna = self.inputs.ms.get_antenna(str(antenna_id))[0]
                    LOG.warning(
                        '[pointing_outlier_flagged] '
                        'Pointing outliers are detected in "%s", '
                        'Field "%s", Antenna "%s": time range "%s", '
                        'max separation %.2f arcsec',
                        self.inputs.vis, field.name, antenna.name,
                        ', '.join(stats.timerange), np.max(stats.separations)
                    )

                if self.inputs.pointing:
                    # if outlier exists, update pointing flag file
                    self._append_outlier_flagcmd_to_flagpoinging_file(
                        outlier_stats
                    )

                    # restore flag status
                    self._execute_flagmanager(mode='restore')

                    # apply deterministic flagging and update datatable again
                    results = self._apply_deterministic_flagging()

        finally:
            if self.inputs.pointing:
                # delete flag state for internal use
                self._execute_flagmanager(mode='delete')

        return FlagDeterALMASingleDishResults(
            results.summaries,
            results.flagcmds(),
            pointing_outlier_stats=outlier_stats
        )

    def _apply_deterministic_flagging(self) -> flagdeterbase.FlagDeterBaseResults:
        """Apply deterministic flagging.

        It also updates the datatable.

        Returns:
            Results object of the base class.
        """
        results = super().prepare()

        # update datatable
        self._update_datatable()

        return results

    def _execute_flagmanager(self, mode: str):
        """Run flagmanager to save/restore/delete flag status.

        Args:
            mode: Execution mode. Should be either
                'save', 'restore', or 'delete'.
        """
        flagversion_name = 'SDPL_hsd_flagdata_internal_before_flagging'
        args_save = {
            'vis': self.inputs.vis,
            'mode': mode,
            'versionname': flagversion_name
        }
        job = casa_tasks.flagmanager(**args_save)
        self._executor.execute(job)

    def _update_datatable(self):
        """Update flag information in the datatable.

        This is necessary to make datatable consistent with the MS.
        """
        origin_basename = os.path.basename(self.inputs.ms.origin_ms)
        table_name = os.path.join(
            self.inputs.context.observing_run.ms_datatable_name,
            origin_basename
        )
        datatable = DataTable(name=table_name, readonly=False)
        datatable._update_flag(self.inputs.ms.origin_ms)
        datatable.exportdata(minimal=False)

    def _detect_pointing_outliers(self) -> dict[tuple[int, int], PointingOutlierStats]:
        outlier_stats = {}
        origin_basename = os.path.basename(self.inputs.ms.origin_ms)
        table_name = os.path.join(
            self.inputs.context.observing_run.ms_datatable_name,
            origin_basename
        )
        msname = self.inputs.ms.basename
        datatable = DataTable(name=table_name, readonly=True)
        antennas = self.inputs.ms.get_antenna()
        target_fields = self.inputs.ms.get_fields(intent="TARGET")
        ra_all = datatable.getcol("SHIFT_RA")
        dec_all = datatable.getcol("SHIFT_DEC")
        srctype_all = datatable.getcol("SRCTYPE")
        field_id_all = datatable.getcol("FIELD_ID")
        antenna_id_all = datatable.getcol("ANTENNA")
        flag_all = np.any(datatable.getcol("FLAG_PERMANENT")[:, 3] == 1, axis=0)
        valid_on_source = np.logical_and(srctype_all == 0, flag_all == 1)

        heuristic = PointingOutlierHeuristics()

        for field, antenna in itertools.product(target_fields, antennas):
            # data selection
            field_antenna_flag = np.logical_and(
                field_id_all == field.id,
                antenna_id_all == antenna.id
            )
            selection = np.logical_and(valid_on_source, field_antenna_flag)
            rows = np.where(selection)[0]
            ra = ra_all[selection]
            dec = dec_all[selection]

            # run heuristic
            heuristic_result = heuristic(field.frame, ra, dec)

            outlier_mask = np.where(np.logical_not(heuristic_result.mask))[0]
            if len(outlier_mask) > 0:
                outliers = rows[outlier_mask]
                LOG.info(
                    'MS "%s" field "%s" antenna "%s": %d pointing outliers detected',
                    msname, field.name, antenna.name, len(outliers)
                )
                LOG.debug("Outliers: %s", outliers)
                separations = heuristic_result.dist[outlier_mask]
                timerange_list = datatable_rowid_to_timerange(
                    datatable, rows[outlier_mask]
                )
                outliers_for_field = PointingOutlierStats(
                        heuristic_result.cx, heuristic_result.cy,
                        heuristic_result.med_dist, heuristic_result.factor,
                        outliers, timerange_list, separations
                    )
                outlier_stats[(field.id, antenna.id)] = outliers_for_field
            else:
                LOG.debug(
                    'MS "%s" field "%s" antenna "%s": no outliers detected',
                    msname, field.name, antenna.name
                )

        return outlier_stats

    def _append_outlier_flagcmd_to_flagpoinging_file(
            self,
            outlier_stats: dict[tuple[int, int], PointingOutlierStats]):
        reason = "pointing_outlier"
        cmd_template = string.Template(
            "mode='manual' field='$field_id' antenna='$antenna_id&&&' timerange='$timerange'"
            f" reason='SDPL:{reason}'\n"
        )

        # generate flag commands
        flagcmds = []
        for (field_id, antenna_id), stats in outlier_stats.items():
            timerange_list = stats.timerange
            for timerange in timerange_list:
                flagcmds.append(
                    cmd_template.safe_substitute(
                        field_id=field_id,
                        antenna_id=antenna_id,
                        timerange=timerange
                    )
                )

        # append flag commands only when flagpointing file exists
        if os.path.exists(self.inputs.filepointing):
            with open(self.inputs.filepointing, 'a') as f:
                for cmd in flagcmds:
                    f.write(cmd)

    def _yield_edge_spw_cmds(self) -> Generator[str, None, None]:
        """Yield flag commands to flag edge channels.

        Yields:
            flag command string to flag edge channels.
        """
        inputs = self.inputs
        # loop over the spectral windows, generate a flagging command for each
        # spw in the ms. Calling get_spectral_windows() with no arguments
        # returns just the science windows, which is exactly what we want.
        for spw in inputs.ms.get_spectral_windows():
            try:
                # test that this spw should be flagged by assessing number of
                # correlations, TDM/FDM mode etc.
                self.verify_spw(spw)
            except ValueError as e:
                # this spw should not be or is incapable of being flagged
                LOG.debug(str(e))
                continue

            # get fraction of spw to flag from template function
            fracspw_org = inputs.fracspw
            try:
                fracspw_list = []
                for _frac in fracspw_org:
                    inputs.fracspw = _frac
                    fracspw_list.append(self.get_fracspw(spw))
            finally:
                inputs.fracspw = fracspw_org
            if len(fracspw_list) == 0:
                continue
            elif len(fracspw_list) == 1:
                fracspw_list.append(fracspw_list[0])

            # If the twice the number of flagged channels is greater than the
            # number of channels for a given spectral window, skip it.
            # frac_chan = int(utils.round_half_up(fracspw * spw.num_channels + 0.5))
            # Make rounding less agressive
            frac_chan_list = [int(utils.round_half_up(x * spw.num_channels)) for x in fracspw_list][:2]
            if sum(frac_chan_list) >= spw.num_channels:
                LOG.debug('Too many flagged channels %s for spw %s '
                          '' % (spw.num_channels, spw.id))
                continue

            # calculate the channel ranges to flag. No need to calculate the
            # left minimum as it is always channel 0.
            l_max = frac_chan_list[0] - 1
            # r_min = spw.num_channels - frac_chan - 1
            # Fix asymmetry
            r_min = spw.num_channels - frac_chan_list[1]
            r_max = spw.num_channels - 1

            # state the spw and channels to flag in flagdata format, adding
            # the statement to the list of flag commands
            def yield_channel_ranges():
                if l_max >= 0:
                    yield '0~{0}'.format(l_max)
                if r_max >= r_min:
                    yield '{0}~{1}'.format(r_min, r_max)

            channel_ranges = list(yield_channel_ranges())

            if len(channel_ranges) == 0:
                continue

            cmd = '{0}:{1}'.format(spw.id, ';'.join(channel_ranges))

            LOG.debug('list type edge fraction specification for spw %s' % spw.id)
            LOG.debug('cmd=\'%s\'' % cmd)

            yield cmd

    def _get_edgespw_cmds(self) -> List[str]:
        """Construct and return list of flag commands.

        Returned list contains flag commands for edge channel flagging.

        Returns:
            List of flag commands for edge channel flag.
        """
        inputs = self.inputs

        if isinstance(inputs.fracspw, float) or isinstance(inputs.fracspw, str):
            to_flag = super()._get_edgespw_cmds()
        elif isinstance(inputs.fracspw, collections.abc.Iterable):
            # inputs.fracspw is iterable indicating that the user want to flag
            # edge channels with different fractions/number of channels for
            # left and right edges

            # to_flag is the list to which flagging commands will be appended
            to_flag = list(self._yield_edge_spw_cmds())

        return to_flag

    def get_fracspw(self, spw: SpectralWindow) -> float:
        """Get fraction of total number of spw channels that are to be flagged on each side of the spw.

        Args:
            spw: SpectralWindow domain object for target spw.

        Returns:
            Fraction of number of channels to be flagged.
        """
        # override the default fracspw getter with our ACA-aware code
        # if spw.num_channels in (62, 124, 248):
        #    return self.inputs.fracspwfps
        # else:
        #    return self.inputs.fracspw
        if isinstance(self.inputs.fracspw, float):
            return self.inputs.fracspw
        elif isinstance(self.inputs.fracspw, str):
            LOG.debug('bandwidth limited edge flagging for spw %s' % spw.id)
            bandwidth_limit = self.bandwidth_limit
            bandwidth = float(spw.bandwidth.value)
            fracspw = 0.5 * (bandwidth - bandwidth_limit) / bandwidth
            LOG.debug('fraction is %s' % fracspw)
            return max(0.0, fracspw)

    def verify_spw(self, spw: SpectralWindow):
        """Test if given spw needs to be processed by edgespw flagging.

        Args:
            spw: SpectralWindow domain object for target spw.

        Raises:
            ValueError: Bandwidth of the spw is less than bandwidth limit.
        """
        # override the default verifier, adding bandwidth check
        super().verify_spw(spw)

        # Skip if TDM mode where TDM modes are defined to be modes with
        # <= 256 channels per correlation
        # dd = self.inputs.ms.get_data_description(spw=spw)
        # ncorr = len(dd.corr_axis)
        # if ncorr * spw.num_channels > 256:
        #    raise ValueError('Skipping edge flagging for FDM spw %s' % spw.id)

        # Skip if edge channel flagging is based on bandwidth limit, and
        # bandwidth is less than bandwidth limit
        if isinstance(self.inputs.fracspw, str) and spw.bandwidth.value <= self.bandwidth_limit:
            raise ValueError('Skipping edge flagging for spw %s' % spw.id)

    def _get_flag_commands(self) -> List[str]:
        """
        Edit flag commands so that all summaries are based on target data instead of total.
        """
        flag_cmds = super()._get_flag_commands()

        # PIPE-646 & PIPE-647
        # apply flag commands in flagpointing.txt
        if self.inputs.pointing:
            if not os.path.exists(self.inputs.filepointing):
                LOG.warning(
                    'Pointing flag file \'{}\' was not found. Pointing '
                    'flagging for {} disabled.'
                    .format(self.inputs.filepointing, self.inputs.ms.basename)
                )
            else:
                update_flag_pointing(self.inputs.filepointing, self.inputs.incompleteraster)
                pointing_cmds = self._read_flagfile(self.inputs.filepointing)
                pointing_cmds.append("mode='summary' name='pointing' reason='SDPL:missing_pointing_data'")

                # insert flag commands between shadow and edgespw
                idx = [i for i, c in enumerate(flag_cmds) if re.search(r"(mode|name)='shadow'", c)]
                assert len(idx) > 0
                sep = idx[-1] + 1
                flag_cmds = flag_cmds[:sep] + pointing_cmds + flag_cmds[sep:]

        for i in range(len(flag_cmds)):
            if flag_cmds[i].startswith("mode='summary'"):
                flag_cmds[i] += " intent='OBSERVE_TARGET#ON_SOURCE'"

        return flag_cmds


@task_registry.set_equivalent_casa_task('hsd_flagdata')
@task_registry.set_casa_commands_comment(
    'Flags generated by the online telescope software, by the QA0 process, and manually set by the pipeline user.'
)
class FlagDeterALMASingleDish(sessionutils.ParallelTemplate):
    Inputs = FlagDeterALMASingleDishInputs
    Task = SerialFlagDeterALMASingleDish
