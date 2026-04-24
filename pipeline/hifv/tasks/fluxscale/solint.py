import collections
import os
import numpy as np
from scipy import stats

import pipeline.hif.heuristics.findrefant as findrefant
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.vdp as vdp
from pipeline.hifv.heuristics import getCalFlaggedSoln, uvrange
from pipeline.hifv.heuristics.lib_EVLApipeutils import vla_minbaselineforcal
from pipeline.infrastructure import casa_tasks
from pipeline.infrastructure import casa_tools
from pipeline.infrastructure import task_registry
from pipeline.infrastructure import utils


LOG = infrastructure.get_logger(__name__)


def solint_rounded_to_integer_integrations(solint,integration_time):
    # code to return a solint that is an even number of integrations
    for i in range(1,10):
        test_n_integrations = (int(solint) + i) / integration_time
        if (test_n_integrations - int(test_n_integrations)) == 0.0:
            return test_n_integrations*integration_time


class SolintInputs(vdp.StandardInputs):
    """Inputs class for the hifv_solint pipeline task.  Used on VLA measurement sets.

    The class inherits from vdp.StandardInputs.

    """
    limit_short_solint = vdp.VisDependentProperty(default='')
    refantignore = vdp.VisDependentProperty(default='')
    refant = vdp.VisDependentProperty(default='')

    # docstring and type hints: supplements hifv_solint
    def __init__(self, context, vis=None, limit_short_solint=None, refantignore=None, refant=None):
        """Initialize Inputs.

        Args:
            context (:obj:): Pipeline context

            vis(str, optional): The list of input MeasurementSets. Defaults to the list of MeasurementSets specified in the hifv_importdata task.

            limit_short_solint(str): Keyword argument in units of seconds to limit the short solution interval. Can be a string or float numerical value in units of seconds of '0.45' or 0.45.
                Can be set to a string value of 'int'.

            refantignore(str): String list of antennas to ignore.

                Example:  refantignore='ea02, ea03'

            refant(str): A csv string of reference antenna(s). When used, disables ``refantignore``.

                Example: refant = 'ea01, ea02'

        """
        super(SolintInputs, self).__init__()
        self.context = context
        self.vis = vis
        self.limit_short_solint = limit_short_solint
        self.refantignore = refantignore
        self.gain_solint1 = 'int'
        self.gain_solint2 = 'int'
        self.refant = refant


class SolintResults(basetask.Results):
    """Results class for the hifv_solint pipeline task.  Used on VLA measurement sets.

    The class inherits from basetask.Results.

    """

    def __init__(self,
                 final: list | None = None,
                 pool: list | None = None,
                 preceding: list | None = None,
                 longsolint: dict | None = None,
                 gain_solint2: dict | None = None,
                 shortsol2: dict | None = None,
                 short_solint: dict | None = None,
                 new_gain_solint1: dict | None = None,
                 vis: str | None = None,
                 bpdgain_touse: dict | None = None,
                 integration_time: dict | None = None):
        """Initializes the object with various calibration and visibility parameters.

        Args:
            final: Calibration list applied (not used).
            pool: Calibration list assessed (not used).
            preceding: DEPRECATED results from worker tasks executed by this task.
            longsolint: Numerical value of the long solution interval.
            gain_solint2: String representation of longsolint with 's' seconds units.
            shortsol2: Values based on the VLA maximum integration time.
            short_solint: Short solution interval numerical value.
            new_gain_solint1: String representation of short_solint with 's' seconds units.
            vis: String name of the measurement set.
            bpdgain_touse: Dictionary of tables per band.
            integration_time: Dictionary of maximum integration times per band.
        """
        if final is None:
            final = []
        if pool is None:
            pool = []
        if preceding is None:
            preceding = []

        super().__init__()

        self.vis = vis
        self.pool = pool[:]
        self.final = final[:]
        self.preceding = preceding[:]
        self.error = set()
        self.longsolint = longsolint
        self.gain_solint2 = gain_solint2

        self.shortsol2 = shortsol2
        self.short_solint = short_solint
        self.new_gain_solint1 = new_gain_solint1
        self.bpdgain_touse = bpdgain_touse
        self.integration_time = integration_time

    def merge_with_context(self, context):
        m = context.observing_run.get_ms(self.vis)
        context.evla['msinfo'][m.name].gain_solint2 = self.gain_solint2
        context.evla['msinfo'][m.name].longsolint = self.longsolint

        context.evla['msinfo'][m.name].shortsol2 = self.shortsol2
        context.evla['msinfo'][m.name].short_solint = self.short_solint
        context.evla['msinfo'][m.name].new_gain_solint1 = self.new_gain_solint1


@task_registry.set_equivalent_casa_task('hifv_solint')
class Solint(basetask.StandardTaskTemplate):
    """Class for the solint pipeline task.  Used on VLA measurement sets.

    The class inherits from basetask.StandardTaskTemplate

    """
    Inputs = SolintInputs

    def prepare(self):
        """Bulk of task execution occurs here.

        Args:
            None

        Returns:
            SolintResults()

        """

        m = self.inputs.context.observing_run.get_ms(self.inputs.vis)
        spw2band = m.get_vla_spw2band()
        band2spw = collections.defaultdict(list)
        spwobjlist = m.get_spectral_windows(science_windows_only=True)
        listspws = [spw.id for spw in spwobjlist]
        for spw, band in spw2band.items():
            if spw in listspws:  # Science intents only
                band2spw[band].append(str(spw))

        longsolint = {}
        gain_solint2 = {}
        shortsol2 = {}
        short_solint = {}
        new_gain_solint1 = {}
        bpdgain_touse = {}
        integration_time = {}
        vis = self.inputs.vis
        calMs = 'calibrators.ms'
        self._do_split(calMs)

        for band, spwlist in band2spw.items():
            try:
                longsolint_band, gain_solint2_band, shortsol2_band, short_solint_band, \
                new_gain_solint1_band, vis, bpdgain_touse_band, integration_time_band = self._do_solint(band, spwlist, calMs)

                longsolint[band] = longsolint_band
                gain_solint2[band] = gain_solint2_band
                shortsol2[band] = shortsol2_band
                short_solint[band] = short_solint_band
                new_gain_solint1[band] = new_gain_solint1_band
                bpdgain_touse[band] = bpdgain_touse_band
                integration_time[band] = integration_time_band
            except Exception as ex:
                    LOG.warning(str(ex))

        return SolintResults(longsolint=longsolint, gain_solint2=gain_solint2, shortsol2=shortsol2,
                             short_solint=short_solint, new_gain_solint1=new_gain_solint1, vis=vis,
                             bpdgain_touse=bpdgain_touse, integration_time=integration_time)

    def analyse(self, results):
        """Determine the best parameters by analysing the given jobs before returning any final jobs to execute.

        Override method of basetask.StandardTaskTemplate.analyze()

        Args:
            results (list of class: `~pipeline.infrastructure.jobrequest.JobRequest`):
                the job requests generated by :func:`~SimpleTask.prepare`

        Returns:
            class:`~pipeline.api.Result`
        """
        return results

    def _do_solint(self, band, spwlist, calMs):
        """Execute solint heuristics per band and spwlist

        Args:
            band(str):  String band single letter identifier -  'L'  'U'  'X' etc.
            spwlist(List):  List of string values for spws - ['0', '1', '2', '3']
            calMs(str):  Split off calibrators MS

        Returns:
            longsolint(float): numerical value of the long solution interval
            gain_solint2(str):  str representation of longsolint with 's' seconds units
            shortsol2(float): values based on the vla max integration time
            short_solint(float): short solution interval numerical value
            new_gain_solint1(str): str representation of short_solint with 's' seconds units.
            vis(str):  MS name
            bpdgain_touse(Dict):  Dictionary of tables per band

        """

        # Solint section

        (longsolint, gain_solint2) = self._do_determine_solint(calMs, ','.join(spwlist), band)
        m = self.inputs.context.observing_run.get_ms(self.inputs.vis)
        # PIPE-2164: getting setjy result stored in context
        self.setjy_results = self.inputs.context.evla['msinfo'][m.name].setjy_results

        try:
            stage_number = self.inputs.context.results[-1].read()[0].stage_number + 1
        except Exception as e:
            stage_number = self.inputs.context.results[-1].read().stage_number + 1

        tableprefix = os.path.basename(self.inputs.vis) + '.' + 'hifv_solint.s'

        # Testgains section
        tablebase = tableprefix + str(stage_number) + '_1.' + 'testgaincal'
        table_suffix = ['_{!s}.tbl'.format(band), '3_{!s}.tbl'.format(band),
                        '10_{!s}.tbl'.format(band), 'scan_{!s}.tbl'.format(band), 'limit_{!s}.tbl'.format(band)]
        soltimes = [1.0, 3.0, 10.0]
        m = self.inputs.context.observing_run.get_ms(self.inputs.vis)
        integration_time = m.get_integration_time_stats(stat_type="max", band=band)
        soltimes = [integration_time * x for x in soltimes]

        solints = ['int', str(soltimes[1]) + 's', str(soltimes[2]) + 's']
        soltime = soltimes[0]
        solint = solints[0]
        shortsol1 = self.inputs.context.evla['msinfo'][m.name].shortsol1[band]
        combtime = 'scan'

        refantfield = self.inputs.context.evla['msinfo'][m.name].calibrator_field_select_string

        self.ignorerefant = self.inputs.context.evla['msinfo'][m.name].ignorerefant
        refantignore = utils.build_refantignore(refantignore=self.inputs.refantignore, ignorerefant=self.ignorerefant)
        # PIPE-595: if refant list is not provided, compute refants else use provided refant list.
        if len(self.inputs.refant) == 0:
            refantobj = findrefant.RefAntHeuristics(vis=calMs, field=refantfield,
                                                    geometry=True, flagging=True, intent='',
                                                    spw='', refantignore=refantignore)

            RefAntOutput = refantobj.calculate()
        else:
            RefAntOutput = self.inputs.refant.split(",")

        refAnt = ','.join(RefAntOutput)

        bpdgain_touse = tablebase + table_suffix[0]

        testgains_result = self._do_gtype_testgains(calMs, bpdgain_touse, solint=solint,
                                                    context=self.inputs.context, combtime=combtime,
                                                    refAnt=refAnt, spw=','.join(spwlist))


        flaggedSolnResult1 = getCalFlaggedSoln(bpdgain_touse)
        LOG.info("For solint = " + solint + " fraction of flagged solutions = " +
                 str(flaggedSolnResult1['all']['fraction']))
        LOG.info("Median fraction of flagged solutions per antenna = " +
                 str(flaggedSolnResult1['antmedian']['fraction']))

        if flaggedSolnResult1['all']['total'] > 0:
            fracFlaggedSolns1 = flaggedSolnResult1['antmedian']['fraction']
        else:
            fracFlaggedSolns1 = 1.0

        shortsol2 = soltime

        if fracFlaggedSolns1 > 0.05:
            soltime = soltimes[1]
            solint = solints[1]

            testgains_result = self._do_gtype_testgains(calMs, tablebase + table_suffix[1], solint=solint,
                                                        context=self.inputs.context, combtime=combtime,
                                                        refAnt=refAnt, spw=','.join(spwlist))
            flaggedSolnResult3 = getCalFlaggedSoln(tablebase + table_suffix[0])

            LOG.info("For solint = " + solint + " fraction of flagged solutions = " +
                     str(flaggedSolnResult3['all']['fraction']))
            LOG.info("Median fraction of flagged solutions per antenna = " +
                     str(flaggedSolnResult3['antmedian']['fraction']))

            if flaggedSolnResult3['all']['total'] > 0:
                fracFlaggedSolns3 = flaggedSolnResult3['antmedian']['fraction']
            else:
                fracFlaggedSolns3 = 1.0

            if fracFlaggedSolns3 < fracFlaggedSolns1:
                shortsol2 = soltime
                bpdgain_touse = tablebase + table_suffix[1]

                if fracFlaggedSolns3 > 0.05:
                    soltime = soltimes[2]
                    solint = solints[2]

                    testgains_result = self._do_gtype_testgains(calMs, tablebase + table_suffix[2], solint=solint,
                                                                context=self.inputs.context, combtime=combtime,
                                                                refAnt=refAnt, spw=','.join(spwlist))
                    flaggedSolnResult10 = getCalFlaggedSoln(tablebase + table_suffix[2])
                    LOG.info("For solint = " + solint + " fraction of flagged solutions = " +
                             str(flaggedSolnResult3['all']['fraction']))
                    LOG.info("Median fraction of flagged solutions per antenna = " +
                             str(flaggedSolnResult3['antmedian']['fraction']))

                    if flaggedSolnResult10['all']['total'] > 0:
                        fracFlaggedSolns10 = flaggedSolnResult10['antmedian']['fraction']
                    else:
                        fracFlaggedSolns10 = 1.0

                    if fracFlaggedSolns10 < fracFlaggedSolns3:
                        shortsol2 = soltime
                        bpdgain_touse = tablebase + table_suffix[2]

                        if fracFlaggedSolns10 > 0.05:
                            solint = 'inf'
                            combtime = ''
                            testgains_result = self._do_gtype_testgains(calMs, tablebase + table_suffix[3],
                                                                        solint=solint, context=self.inputs.context,
                                                                        combtime=combtime, refAnt=refAnt,
                                                                        spw=','.join(spwlist))
                            flaggedSolnResultScan = getCalFlaggedSoln(tablebase + table_suffix[3])
                            LOG.info("For solint = " + solint + " fraction of flagged solutions = " +
                                     str(flaggedSolnResult3['all']['fraction']))
                            LOG.info("Median fraction of flagged solutions per antenna = " +
                                     str(flaggedSolnResult3['antmedian']['fraction']))

                            if flaggedSolnResultScan['all']['total'] > 0:
                                fracFlaggedSolnsScan = flaggedSolnResultScan['antmedian']['fraction']
                            else:
                                fracFlaggedSolnsScan = 1.0

                            if fracFlaggedSolnsScan < fracFlaggedSolns10:
                                shortsol2 = self.inputs.context.evla['msinfo'][m.name].longsolint
                                bpdgain_touse = tablebase + table_suffix[3]

                                if fracFlaggedSolnsScan > 0.05:
                                    LOG.warning("Warning, large fraction of flagged solutions.  " +
                                                "There might be something wrong with your data")

        LOG.info("ShortSol1: %s", shortsol1)
        LOG.info("ShortSol2: %s", shortsol2)

        short_solint = max(shortsol1, shortsol2)
        LOG.info('Short_solint determined from heuristics: %s', short_solint)
        integration_time = m.get_integration_time_stats(stat_type="max", band=band)
        if short_solint == integration_time:
            new_gain_solint1 = 'int'
        else:
            new_gain_solint1 = str(short_solint) + 's'

        if self.inputs.limit_short_solint != '':
            LOG.warning('Short Solint limited by the task input to %r', self.inputs.limit_short_solint)
            limit_short_solint = self.inputs.limit_short_solint
            if limit_short_solint not in ("int", "inf"):
                try:
                    limit_short_solint = float(limit_short_solint)
                except ValueError:
                    LOG.warning("limit_short_solint must be 'int', 'inf', or a numeric value. Defaulting to 'int'.")
                    limit_short_solint = 'int'

            if limit_short_solint == 'int':
                combtime = 'scan'
                # PIPE-2686: short_solint is being compared with longslit for QA scoring downstream;
                # try to use float when possible.
                short_solint = integration_time
                new_gain_solint1 = 'int'
            elif limit_short_solint == 'inf':
                combtime = ''
                short_solint = 'inf'
                new_gain_solint1 = longsolint
                LOG.warning("limit_short_solint is 'inf', so combine is set to '' and solint to long solint (%.2fs) in gaincal.", longsolint)
            elif limit_short_solint < integration_time:
                combtime = 'scan'
                short_solint = integration_time
                new_gain_solint1 = 'int'
                LOG.warning("limit_short_solint is shorter than a single integration time (%.2fs). Setting solint='int'.", integration_time)
            elif limit_short_solint > longsolint:
                combtime = 'scan'
                short_solint = longsolint
                new_gain_solint1 = longsolint
                LOG.warning("limit_short_solint larger than long solint (%.2fs), setting short solint equal to long solint.", longsolint)
            else:
                short_solint = limit_short_solint
                if short_solint == integration_time:
                    new_gain_solint1 = 'int'
                else:
                    new_gain_solint1 = short_solint
                combtime = 'scan'

            # PIPE-460.  Use solint='int' when the minimum solution interval corresponds to one integration
            # PIPE-696.  Need to compare short solint with int time and limit the precision.
            if short_solint == float(f"{integration_time:.6f}"):
                new_gain_solint1 = "int"
                LOG.info(
                    'The short solution interval used is: %r %.2fs.', new_gain_solint1, short_solint)
            self._do_gtype_testgains(calMs, tablebase + table_suffix[4], solint=new_gain_solint1,
                                     context=self.inputs.context, combtime=combtime,
                                     refAnt=refAnt, spw=','.join(spwlist))
            bpdgain_touse = tablebase + table_suffix[4]

        LOG.info("Using short solint = " + str(new_gain_solint1))
        if short_solint not in ('int', 'inf') and abs(longsolint - short_solint) <= soltime:
            LOG.warning('Short solint = long solint +/- integration time of {}s'.format(integration_time))

        return longsolint, gain_solint2, shortsol2, short_solint, new_gain_solint1, self.inputs.vis, bpdgain_touse,integration_time

    def _do_split(self, calMs: str):
        """Execute CASA task split on the calibrator scan select string

        Args:
            calMs(str):  outputvis parameter name

        Returns:
            Executed job

        """

        m = self.inputs.context.observing_run.get_ms(self.inputs.vis)
        calibrator_scan_select_string = self.inputs.context.evla['msinfo'][m.name].calibrator_scan_select_string

        LOG.info("Splitting out calibrators into " + calMs)

        task_args = {'vis': m.name,
                     'outputvis': calMs,
                     'datacolumn': 'corrected',
                     'keepmms': True,
                     'field': '',
                     'spw': '',
                     'width': 1,
                     'antenna': '',
                     'timebin': '0s',
                     'timerange': '',
                     'scan': calibrator_scan_select_string,
                     'intent': '',
                     'array': '',
                     'uvrange': '',
                     'correlation': '',
                     'observation': '',
                     'keepflags': False}

        job = casa_tasks.split(**task_args)

        return self._executor.execute(job)

    def _do_determine_solint(self, calMs: str, spw: str = '',  band: str | None = None):
        """Code to determine solution interval

        Args:
            calMs(str):  split off calibrators MS
            spw(str):  spw selection  '2,3,4', etc.
            band(str): string band, 'L'  'U'  'X' etc.
        Returns:
            longsolint
            gain_solint2

        """

        durations = []
        old_spws = []
        old_field = ''

        with casa_tools.MSReader(calMs) as ms:
            scan_summary = ms.getscansummary()

            m = self.inputs.context.observing_run.get_ms(self.inputs.vis)

            phase_scan_list = self.inputs.context.evla['msinfo'][m.name].phase_scan_select_string.split(',')
            phase_scan_list = [int(i) for i in phase_scan_list]

            # Sub-select phase scan list per band
            phase_scanids_perband = [scan.id for scan in m.get_scans(scan_id=phase_scan_list, spw=spw)]

            for kk in range(len(phase_scan_list)):
                ii = phase_scan_list[kk]
                if ii in phase_scanids_perband:
                    try:
                        # Collect beginning and ending times
                        # Take max of end times and min of beginning times
                        endtimes = [scan_summary[str(ii)][scankey]['EndTime'] for scankey in scan_summary[str(ii)]]
                        begintimes = [scan_summary[str(ii)][scankey]['BeginTime'] for scankey in scan_summary[str(ii)]]

                        end_time = max(endtimes)
                        begin_time = min(begintimes)

                        new_spws = scan_summary[str(ii)]['0']['SpwIds']
                        new_field = scan_summary[str(ii)]['0']['FieldId']

                        if ((kk > 0) and (phase_scan_list[kk-1] == ii-1) and
                                (set(new_spws) == set(old_spws)) and (new_field == old_field) and
                                (phase_scan_list[kk-1] in phase_scanids_perband)):
                            # if contiguous scans, just increase the time on the previous one
                            add_duration = 86400 * (end_time - old_begin_time)
                            if add_duration < 1000.0:
                                durations[-1] = add_duration
                                LOG.info("End time, old begin time {} {}".format(end_time, old_begin_time))
                        else:
                            LOG.info("End time, begin time {} {}".format(end_time, begin_time))
                            durations.append(86400*(end_time - begin_time))
                            old_begin_time = begin_time
                            LOG.info("Append durations, old, begin {} {} {}:".format(durations, old_begin_time, begin_time))
                        LOG.info("Scan "+str(ii)+" has "+str(durations[-1])+"s on source")
                        old_spws = new_spws
                        old_field = new_field

                    except KeyError:
                        LOG.warning("Scan "+str(ii)+" is completely flagged and missing from " + calMs)

        orig_durations = np.array(durations)

        try:
            durations = orig_durations[(np.abs(stats.zscore(orig_durations)) < 3)]
        except ValueError:
            LOG.info("No statistical outliers in list of determined durations.")
            durations = orig_durations

        if not durations.tolist():
            LOG.info("No statistical outliers in list of determined durations.")
            durations = orig_durations
        nsearch = 5
        integration_time = m.get_integration_time_stats(stat_type="max", band=band)
        integration_time = np.around(integration_time, decimals=2)
        search_results = np.zeros(nsearch)
        if len(orig_durations) != 0:
            longest_scan = np.round(np.max(orig_durations))
        else:
            longest_scan = None
        if len(durations) != 0:
            zscore_solint = np.max(durations)
            solint_integer_integrations = solint_rounded_to_integer_integrations(zscore_solint * 1.01, integration_time)
        else:
            zscore_solint = None
            solint_integer_integrations = None
        if solint_integer_integrations and longest_scan is not None:
            for i in range(nsearch):
                # print('testing solint', solint_integer_integrations + i * integration_time)
                search_results[i] = longest_scan / (solint_integer_integrations + i * integration_time) - int(longest_scan / (solint_integer_integrations + i * integration_time))
            longsolint = solint_integer_integrations + np.argmax(search_results) * integration_time
        else:
            if durations:
                longsolint = (np.max(durations)) * 1.01
                LOG.warning("Using alternate long solint calculation.")
            else:
                longsolint = integration_time
                LOG.warning("No determined durations found; setting 'longsolint' to integration time.")
        # PIPE-2686: convert np.float64 to native float
        longsolint = float(longsolint)
        gain_solint2 = str(longsolint) + 's'

        return longsolint, gain_solint2

    def _do_gtype_testgains(self, calMs: str, caltable: str, solint: str = 'int', context=None, combtime: str = 'scan',
                            refAnt = None, spw: str = ''):
        """Perform a G-Type delay calibration with CASA task gaincal

        Args:
            calMs(str): split off calibrators for use in the gaincal vis parameter
            caltable(str): Name of the caltable to be created
            solint
            context (:obj:): Pipeline context
            combtime(str):  gaincal parameter default of 'scan'
            refAnt(str): csv string of reference antennas
            spw(str):  spw selection  '2,3,4', etc.

        Returns:
            Boolean

        """

        m = self.inputs.context.observing_run.get_ms(self.inputs.vis)

        calibrator_scan_select_string = context.evla['msinfo'][m.name].calibrator_scan_select_string

        scanlist = [int(scan) for scan in calibrator_scan_select_string.split(',')]
        scanids_perband = ','.join([str(scan.id) for scan in m.get_scans(scan_id=scanlist, spw=spw)])

        minBL_for_cal = vla_minbaselineforcal()

        task_args = {'vis': calMs,
                     'caltable': caltable,
                     'field': '',
                     'spw': spw,
                     'intent': '',
                     'selectdata': True,
                     'scan': scanids_perband,
                     'solint': solint,
                     'combine': combtime,
                     'preavg': -1.0,
                     'refant': refAnt.lower(),
                     'minblperant': minBL_for_cal,
                     'minsnr': 5.0,
                     'solnorm': False,
                     'gaintype': 'G',
                     'smodel': [],
                     'calmode': 'ap',
                     'append': False,
                     'gaintable': [''],
                     'gainfield': [''],
                     'interp': [''],
                     'spwmap': [],
                     'uvrange': '',
                     'parang': True}

        calscanslist = list(map(int, scanids_perband.split(',')))
        scanobjlist = m.get_scans(scan_id=calscanslist,
                                  scan_intent=['AMPLITUDE', 'BANDPASS', 'POLLEAKAGE', 'POLANGLE',
                                               'PHASE', 'POLARIZATION', 'CHECK'])
        fieldidlist = []
        for scanobj in scanobjlist:
            fieldobj, = scanobj.fields
            if str(fieldobj.id) not in fieldidlist:
                fieldidlist.append(str(fieldobj.id))

        for fieldidstring in fieldidlist:
            # PIPE-1729: passing fieldidstring instead of field id to avoid
            # warning while concatenating string and int
            taql = (f"FIELD_ID == {fieldidstring}")
            if utils.get_row_count(calMs, taql) != 0:
                uvrangestring = uvrange(self.setjy_results, fieldidstring)
                task_args['field'] = fieldidstring
                task_args['uvrange'] = uvrangestring
                if os.path.exists(caltable):
                    task_args['append'] = True

                job = casa_tasks.gaincal(**task_args)

                self._executor.execute(job)

        return True
