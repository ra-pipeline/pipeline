import os

import numpy as np

import pipeline.domain as domain
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.vdp as vdp
import pipeline.infrastructure.utils as utils
from pipeline.h.tasks.common import calibrationtableaccess as caltableaccess
from pipeline.h.tasks.common import commonresultobjects
from pipeline.h.tasks.common import viewflaggers
from pipeline.h.tasks.flagging.flagdatasetter import FlagdataSetter
from pipeline.hif.tasks import bandpass
from pipeline.hifa.tasks import bandpass as bandpass_alma
from pipeline.hif.tasks import gaincal
from pipeline.hifa.heuristics.phasespwmap import combine_spwmap
from pipeline.infrastructure import callibrary
from pipeline.infrastructure import task_registry
from pipeline.infrastructure.refantflag import (
    identify_fully_flagged_antennas_from_flagview,
    mark_antennas_for_refant_update,
    aggregate_fully_flagged_antenna_notifications,
)
from .resultobjects import LowgainflagDataResults
from .resultobjects import LowgainflagResults
from .resultobjects import LowgainflagViewResults

__all__ = [
    'LowgainflagInputs',
    'Lowgainflag'
]

LOG = infrastructure.get_logger(__name__)


class LowgainflagInputs(vdp.StandardInputs):
    """
    LowgainflagInputs defines the inputs for the Lowgainflag pipeline task.
    """
    flag_nmedian = vdp.VisDependentProperty(default=True)
    fnm_hi_limit = vdp.VisDependentProperty(default=1.5)
    fnm_lo_limit = vdp.VisDependentProperty(default=0.5)

    @vdp.VisDependentProperty
    def intent(self):
        # PIPE-2601
        # for ALMA data we want to use almaphcorbandpass method
        # which will allow SpW combine, solint time averaging, channel binning in bandpass
        if self.ms.antenna_array.name == 'ALMA':
            bp_inputs = bandpass_alma.SerialALMAPhcorBandpass.Inputs(context=self.context, vis=self.vis, intent=None)
        else:
            bp_inputs = bandpass.PhcorBandpass.Inputs(context=self.context, vis=self.vis, intent=None)

        # function is to default to the intent that would be used for bandpass calibration (BANDPASS)
        return bp_inputs.intent

    # Flagging view is created if number of antennas in a set equals-or-exceeds
    # the threshold.
    min_nants_threshold = vdp.VisDependentProperty(default=5)
    niter = vdp.VisDependentProperty(default=2)

    # PIPE-566, PIPE-808: set threshold for "too many entirely flagged"
    tmef1_limit = vdp.VisDependentProperty(default=0.666)

    @vdp.VisDependentProperty
    def refant(self):
        # we cannot find the context value without the measurement set
        if not self.ms:
            return None

        # get the reference antenna for this measurement set
        ant = self.ms.reference_antenna
        if isinstance(ant, list):
            ant = ant[0]

        # return the antenna name/id if this is an Antenna domain object
        if isinstance(ant, domain.Antenna):
            return getattr(ant, 'name', ant.id)

        # otherwise return whatever we found. We assume the calling function
        # knows how to handle an object of this type.
        return ant

    @vdp.VisDependentProperty
    def spw(self):
        science_spws = self.ms.get_spectral_windows(with_channels=True, science_windows_only=True)
        return ','.join([str(spw.id) for spw in science_spws])

    # docstring and type hints: supplements hif_lowgainflag
    def __init__(self, context, output_dir=None, vis=None, intent=None, spw=None, refant=None, flag_nmedian=None,
                 fnm_lo_limit=None, fnm_hi_limit=None, niter=None, min_nants_threshold=None, tmef1_limit=None):
        """Initialize Inputs.

        Args:
            context: Pipeline context object containing state information.

            output_dir: Output directory.
                Defaults to None, which corresponds to the current working directory.

            vis: The list of input MeasurementSets. Defaults to the list of
                MeasurementSets specified in the <hifa,hifv>_importdata task.
                '': use all MeasurementSets in the context

                Examples: 'ngc5921.ms', ['ngc5921a.ms', ngc5921b.ms', 'ngc5921c.ms']

            intent: A string containing the list of intents to be checked for
                antennas with deviant gains. The default is blank, which
                causes the task to select the 'BANDPASS' intent.

            spw: The list of spectral windows and channels to which the
                calibration will be applied. Defaults to all science windows
                in the pipeline context.

                Examples: spw='17', spw='11, 15'

            refant: A string containing a prioritized list of reference antenna
                name(s) to be used to produce the gain table. Defaults to the
                value(s) stored in the pipeline context. If undefined in the
                pipeline context defaults to the CASA reference antenna naming
                scheme.

                Examples: refant='DV01', refant='DV06,DV07'

            flag_nmedian: Whether to flag figures of merit greater than
                ``fnm_hi_limit`` * median or lower than ``fnm_lo_limit`` * median.
                (default: True)

            fnm_lo_limit: Flag values lower than ``fnm_lo_limit`` * median (default: 0.5)

            fnm_hi_limit: Flag values higher than ``fnm_hi_limit`` * median (default: 1.5)

            niter: The maximum number of iterations to run of the sequence:
                solve for amplitude gains, assess statistics, flag spw/antenna
                combinations that are outliers (default: 2)

            min_nants_threshold:

            tmef1_limit: Threshold for "too many entirely flagged" -
                the critical fraction of antennas whose solutions are entirely
                flagged in the flagging view of a spw for this stage:
                if the fraction is equal or greater than this value, then flag
                the visibility data from all antennas in this spw
                (default: 0.666)

        """
        super().__init__()

        # pipeline inputs
        self.context = context
        # vis must be set first, as other properties may depend on it
        self.vis = vis
        self.output_dir = output_dir

        # data selection arguments
        self.intent = intent
        self.spw = spw
        self.refant = refant
        self.min_nants_threshold = min_nants_threshold

        # flagging parameters
        self.flag_nmedian = flag_nmedian
        self.fnm_hi_limit = fnm_hi_limit
        self.fnm_lo_limit = fnm_lo_limit
        self.niter = niter
        self.tmef1_limit = tmef1_limit


@task_registry.set_equivalent_casa_task('hif_lowgainflag')
@task_registry.set_casa_commands_comment(
    'Sometimes antennas have significantly lower gain than nominal. Even when calibrated, it is better for ALMA data to'
    ' flag these antennas. The pipeline detects this by calculating a long solint amplitude gain on the bandpass '
    'calibrator.  First, temporary phase and bandpass solutions are calculated, these use the ALMA methodology '
    'where SpWs can be combined, the solint can be longer than the integration time. Second, the bandpass solve '
    'can also use channel binning to maintain SNR, and finally the bandpass is pre-applied and the solint and '
    'combine parameters are forwarded to the -short- solint phase and long (inf) solint amplitude solution.'
)
class Lowgainflag(basetask.StandardTaskTemplate):
    Inputs = LowgainflagInputs

    def prepare(self):
        inputs = self.inputs

        # Initialize result and store vis in result
        result = LowgainflagResults(vis=inputs.vis)

        # Construct the task that will read the data.
        datainputs = LowgainflagDataInputs(
            context=inputs.context, output_dir=inputs.output_dir,
            vis=inputs.vis, intent=inputs.intent, spw=inputs.spw,
            refant=inputs.refant)
        datatask = LowgainflagData(datainputs)

        # Construct the generator that will create the view of the data
        # that is the basis for flagging.
        viewtask = LowgainflagView(
            context=inputs.context, vis=inputs.vis, intent=inputs.intent,
            spw=inputs.spw, refant=inputs.refant,
            min_nants_threshold=inputs.min_nants_threshold)

        # Construct the task that will set any flags raised in the
        # underlying data.
        flagsetterinputs = FlagdataSetter.Inputs(
            context=inputs.context, vis=inputs.vis, table=inputs.vis,
            inpfile=[])
        flagsettertask = FlagdataSetter(flagsetterinputs)

        # Define which type of flagger to use.
        flagger = viewflaggers.MatrixFlagger

        # Translate the input flagging parameters to a more compact
        # list of rules.
        rules = flagger.make_flag_rules(
            flag_nmedian=inputs.flag_nmedian,
            fnm_lo_limit=inputs.fnm_lo_limit,
            fnm_hi_limit=inputs.fnm_hi_limit)

        # PIPE-566: append a rule to detect when a flagging view has no usable
        # (unflagged) data at all for a spw (e.g. because gaincal could not
        # compute any solutions). In this case the underlying (bad) data in the
        # MS for this spw should get flagged explicitly.
        rules.extend(flagger.make_flag_rules(flag_tmef1=True, tmef1_axis='Antenna1', tmef1_limit=inputs.tmef1_limit))

        # Construct the flagger task around the data view task and the
        # flagsetter task.
        matrixflaggerinputs = flagger.Inputs(
            context=inputs.context, output_dir=inputs.output_dir,
            vis=inputs.vis, datatask=datatask, viewtask=viewtask,
            flagsettertask=flagsettertask, rules=rules, niter=inputs.niter,
            extendfields=['field', 'scan'], iter_datatask=True, skip_fully_flagged=False)
        flaggertask = flagger(matrixflaggerinputs)

        # Execute the flagger task.
        flaggerresult = self._executor.execute(flaggertask)

        # Import views, flags, and "measurement set or caltable to flag"
        # into final result
        result.importfrom(flaggerresult)

        # Copy flagging summaries to final result
        result.summaries = flaggerresult.summaries

        return result

    def analyse(self, result):
        """
        Analyses the Lowgainflag result.

        :param result: LowgainflagResults object
        :return: LowgainflagResults object
        """
        result = self._identify_refants_to_update(result)

        return result

    def _identify_refants_to_update(self, result):
        """
        Updates the Lowgainflag result to mark any antennas that were found
        to be fully flagged by the newly introduced flagging commands
        to be demoted and/or removed when result gets accepted.

        :param result: LowgainflagResults object
        :return: LowgainflagResults object
        """

        # First summarize which antennas are fully flagged in any flagging view.
        ms = self.inputs.ms

        # The flagging view shows antennas with flagging commands introduced in this stage,
        # as well as those which have been flagged by earlier stages.
        # OTOH the flagging commands only show the effect of this stage alone.
        # The two uncommented lines below implement the former approach (currently used),
        # and the commented-out line - the latter.

        scan_to_field_names = {str(scan.id): tuple(field.name for field in scan.fields) for scan in ms.scans}
        fully_flagged_antennas = identify_fully_flagged_antennas_from_flagview(ms, result, scan_to_field_names)

        # fully_flagged_antennas = identify_fully_flagged_antennas_from_flagcmds(ms, result.flagcmds())

        # If any fully flagged antennas were found, then update result to mark
        # these antennas for demotion and/or removal.
        all_spw_ids = {int(spw) for spw in self.inputs.spw.split(',')}
        result = mark_antennas_for_refant_update(ms, result, fully_flagged_antennas, all_spw_ids)

        # Aggregate the list of fully flagged antennas by intent, field and spw for subsequent QA scoring
        result.fully_flagged_antenna_notifications = aggregate_fully_flagged_antenna_notifications(
            fully_flagged_antennas, all_spw_ids)

        return result


class LowgainflagDataInputs(vdp.StandardInputs):
    def __init__(self, context, output_dir=None, vis=None, intent=None,
                 spw=None, refant=None):
        super().__init__()

        # pipeline inputs
        self.context = context
        # vis must be set first, as other properties may depend on it
        self.vis = vis
        self.output_dir = output_dir

        # data selection arguments
        self.intent = intent
        self.spw = spw
        self.refant = refant


class LowgainflagData(basetask.StandardTaskTemplate):
    Inputs = LowgainflagDataInputs

    def __init__(self, inputs):
        super().__init__(inputs)

    def prepare(self):
        inputs = self.inputs

        # Initialize result structure
        result = LowgainflagDataResults()
        result.vis = inputs.vis

        # PIPE-2601 refactor to not have working direct in 'prepare'
        # but separated out into the respective functions

        # Do the bandpass steps
        bpcal_result, solint, combine = self._do_initial_bandpass()

        # Do the phase-up
        gpcal_result = self._do_postbandpass_phaseup(solint, combine)


        # Do the amplitude gains
        gacal_result, gatable, table_available = self._do_postbandpass_ampgains()

        # Result passed back is the gaintable and boolean
        # if it was correctly made
        result.table = gatable
        result.table_available = table_available

        return result

    def analyse(self, result):
        return result


    def _do_initial_bandpass(self):
        """
        This method is responsible for doing the 
        calls to make a bandpass table. The method will call
        either of the PhcorBandpass, or SerialALMAPhcorBandpass
        processes for non-ALMA and ALMA data respecitvely.

        With ALMA data, the PIPE-2442 process is used, i.e. an 
        SNR check is used to combine spw and change solint time for 
        the pre-bandpass phase-up, and thereafter the bandpass solver 
        will also bin channels for a suitable SNR bandpass solutions
 
        For other data, the default process (as <=PL2025) will 
        not combine spw, and uses int for all phase-up solves
        while using a default 7.8125MHz channel binning for bandpass
        """

        inputs = self.inputs

        # PIPE-2601 check ALMA or not
        if inputs.ms.antenna_array.name == 'ALMA':
            bpcal_inputs = bandpass_alma.SerialALMAPhcorBandpass.Inputs(
                context=inputs.context, vis=inputs.vis, intent=inputs.intent,
                spw=inputs.spw, refant=inputs.refant)
            bpcal_task = bandpass_alma.SerialALMAPhcorBandpass(bpcal_inputs)
            bpcal_result = self._executor.execute(bpcal_task, merge=False)
        else:
            # Not ALMA
            bpcal_inputs = bandpass.PhcorBandpass.Inputs(
                context=inputs.context, vis=inputs.vis, intent=inputs.intent,
                spw=inputs.spw, refant=inputs.refant, solint='inf,7.8125MHz')
            bpcal_task = bandpass.PhcorBandpass(bpcal_inputs)
            bpcal_result = self._executor.execute(bpcal_task, merge=False)

        # Default fallback used when bandpass produces no final solution.
        solint, combine = 'int', ''
        if not bpcal_result.final:
            LOG.warning("No bandpass solution computed for %s", inputs.ms.basename)
        else:
            bpcal_result.accept(inputs.context)
            # PIPE-2601 get the phase-up solution interval and combine parameters
            # as these need to be passed to the subsequent gaincal to avoid loss of data.
            # The function returns 'int', '' for non-ALMA data.
            solint, combine = self._get_prebandpass_phaseup_params(bpcal_result)

        return bpcal_result, solint, combine
        
    def _do_postbandpass_phaseup(self, solint, combine):
        """ 
        This method is responsible for doing the post
        bandpass solve phaseup. The bandpass in local context
        will be applied and then a phase gain caltable is made.
        Inputs are solint and combine, as to use values previously 
        found that will get a sufficient SNR and not cause 
        undue lost solutions due to low SNR for e.g. High Freq and
        ACA data where SNR is intrinsically low and an assumed per
        SpW, solint = 'int' solution will not gurantee enough SNR
       
        returns the gpcal result but it is registered here
        """

        inputs = self.inputs

        # Calculate gain phases
        # PIPE-2601 added to use solint and combine found in pre-phaseup done before bandpass
        # required to have high enough SNR and avoid flags due to this solve
        # if combine used need to add spw mapping for ALMA data.
        # Otherwise, 'int' and '' are passes for solint and combine such as to make
        # the default phase-up
        gpcal_inputs = gaincal.GTypeGaincal.Inputs(context=inputs.context, vis=inputs.vis, intent=inputs.intent,
                                                   spw=inputs.spw, refant=inputs.refant, calmode='p', minsnr=2.0,
                                                   solint=solint, combine=combine)
        gpcal_task = gaincal.GTypeGaincal(gpcal_inputs)
        gpcal_result = self._executor.execute(gpcal_task, merge=False)
        if not gpcal_result.final:
            LOG.warning("No phase time solution computed for {}".format(inputs.ms.basename))

        else:
            # PIPE-2601 before accepting to context
            # need to set the spwmap such that the pre-apply when solving amp gains
            # will map correctly. Can only trigger for ALMA data where combine has an entry
            if combine:
                spwmap = inputs.ms.get_spectral_windows(task_arg=inputs.spw, science_windows_only=True)
                combspwmapheur = combine_spwmap(spwmap)

                LOG.info('Using combined spw map %s for ALMA phaseup', combspwmapheur)

                modified_calapp = callibrary.copy_calapplication(gpcal_result.pool[0], spwmap=combspwmapheur)
                gpcal_result.pool[0] = modified_calapp
                gpcal_result.final[0] = modified_calapp
            gpcal_result.accept(inputs.context)

        # pass the result back in case any subsequent or future code want this
        return gpcal_result

        
    def _do_postbandpass_ampgains(self):
        """
        This method is responsible for creating the amp gain
        caltable for the BANDPASS intent and making a fixed 'inf' 
        solution amplitude gains solve.
 
        The resulting caltable will be locally registered and 
        investigated for low gain values
        """
        
        inputs = self.inputs

        # Calculate gain amplitudes
        gacal_inputs = gaincal.GTypeGaincal.Inputs(
            context=inputs.context, vis=inputs.vis,
            intent=inputs.intent, spw=inputs.spw,
            refant=inputs.refant,
            calmode='a', minsnr=2.0, solint='inf', gaintype='T')
        gacal_task = gaincal.GTypeGaincal(gacal_inputs)
        gacal_result = self._executor.execute(gacal_task, merge=False)
        if not gacal_result.final:
            gatable = list(gacal_result.error)
            gatable = gatable[0].gaintable
            LOG.warning("No amplitude time solution computed for {}".format(inputs.ms.basename))
            table_available = False
        else:
            gacal_result.accept(inputs.context)
            gatable = gacal_result.final
            gatable = gatable[0].gaintable
            table_available = True

        return gacal_result, gatable, table_available
            
    def _get_prebandpass_phaseup_params(self, result):
        """
        Read the result object passed from the bandpass task for ALMA data
        as to loop the pre-applied gaintables, and to extract the input args used
        for solint and combine so these can be output, and will later propagate to 
        the phase-up _post_ bandpass and _pre_ amp gains

        :param: result, the bpcal result from bandpass.SerialALMAPhCorBandpass
        :return: solint, combine as strings to gaincal input
        """

        # Default parameters for ALMA and non-ALMA data
        solint_use, combine_use = 'int', ''

        # PIPE-2601 protection here to only work on ALMA data
        if self.inputs.ms.antenna_array.name == 'ALMA':
            phaseup_calapps = []
            # loop applies that 'preceded' the bandpass solve, i.e. the phaseup/phase-offset
            for previous_result in result.preceding:
                for calapp in previous_result:
                    gaincal_froms = [cf for cf in calapp.calfrom if cf.caltype == 'gaincal']
                    if gaincal_froms and calapp not in phaseup_calapps:
                        phaseup_calapps.append(calapp)

            # extract solint and combine from the calapp applied
            # there will be a maximum of two calapps for ALMA;
            # if spw combination was triggered in the ALMAPhcorBandpass method
            # the first calapp is the phase offset with solint=inf,
            # the second is the phase-up with solint = 'time', this is what we extract here.
            for calapp in phaseup_calapps:
                solint = utils.get_origin_input_arg(calapp, 'solint')
                combine = utils.get_origin_input_arg(calapp, 'combine')
                if solint != 'inf':
                    solint_use = solint
                    combine_use = combine

        return solint_use, combine_use

class LowgainflagView:

    def __init__(self, context, vis=None, intent=None, spw=None, refant=None,
                 min_nants_threshold=None):

        self.context = context
        self.vis = vis
        self.intent = intent
        self.spw = spw
        self.refant = refant
        self.min_nants_threshold = min_nants_threshold

    def __call__(self, data):

        # Initialize result structure
        self.result = LowgainflagViewResults()

        if data.table_available:

            # Calculate the view
            gatable = data.table
            LOG.info('Computing flagging metrics for caltable {0}'.format(
                os.path.basename(gatable)))
            self.calculate_view(gatable)

        # Add visibility name to result
        self.result.vis = self.vis

        return self.result

    def calculate_view(self, table):
        """
        table -- Name of gain table to be analysed.
        """

        # Open gains caltable.
        gtable = caltableaccess.CalibrationTableDataFiller.getcal(table)

        # Get range of scans covered.
        scans = set()
        for row in gtable.rows:
            # The gain table is T, should be no pol dimension
            npols = np.shape(row.get('CPARAM'))[0]
            if npols != 1:
                raise Exception('table has polarization results')
            scans.update([row.get('SCAN_NUMBER')])
        scans = np.sort(list(scans))

        # Create translation of scan ID to flagging view axis ID.
        scanid_to_axisid = {scan_id: axis_id for axis_id, scan_id in enumerate(scans)}

        # Get the MS domain object.
        ms = self.context.observing_run.get_ms(name=self.vis)

        # Get spw IDs from MS: the task input "spw" arg may contain channel
        # specification, so let MS parse input and read spw ID from the
        # SpectralWindow domain objects that are returned.
        spwids = [spw.id for spw in ms.get_spectral_windows(self.spw)]

        # Identify set of unique antenna diameters present in MS.
        ant_diameters = {antenna.diameter for antenna in ms.antennas}

        # Create separate flagging view for each set of antennas with
        # same diameter.
        for antdiam in ant_diameters:
            # Identify antennas with current diameter.
            antenna_ids = sorted([antenna.id for antenna in ms.antennas if antenna.diameter == antdiam])

            # Create translation of antenna ID to flagging view axis ID.
            antid_to_axisid = {ant_id: axis_id for axis_id, ant_id in enumerate(antenna_ids)}
            nants = len(antenna_ids)

            # If the number of antennas is below the threshold, then skip
            # flagging for the set with current diameter.
            if nants < self.min_nants_threshold:
                LOG.warning(
                    "Number of antennas with diameter of {:.1f} m is"
                    " below the minimum threshold ({}), skipping"
                    " flagging for these antennas (no flagging view"
                    " created).".format(antdiam, self.min_nants_threshold))
            else:
                # Create flagging view for each spwid.
                for spwid in spwids:

                    # Initialize arrays for flagging view.
                    data = np.zeros([nants, len(scans)])
                    flag = np.ones([nants, len(scans)], bool)

                    for row in gtable.rows:
                        ant = row.get('ANTENNA1')
                        if row.get('SPECTRAL_WINDOW_ID') == spwid and ant in antenna_ids:
                            gain = row.get('CPARAM')[0][0]
                            gainflag = row.get('FLAG')[0][0]
                            scan = row.get('SCAN_NUMBER')
                            if not gainflag:
                                data[antid_to_axisid[ant], scanid_to_axisid[scan]] = np.asarray(np.abs(gain)).item()
                                flag[antid_to_axisid[ant], scanid_to_axisid[scan]] = 0

                    axes = [
                        commonresultobjects.ResultAxis(name='Antenna1', units='id', data=np.asarray(antenna_ids)),
                        commonresultobjects.ResultAxis(name='Scan', units='id', data=[str(scan) for scan in scans],
                                                       channel_width=1)
                    ]

                    # associate the result with a generic filename - using
                    # specific names gives confusing duplicates on the weblog
                    # display
                    ants = ','.join([str(ant) for ant in antenna_ids])
                    viewresult = commonresultobjects.ImageResult(
                        filename='%s(gtable)' % os.path.basename(gtable.vis),
                        intent=self.intent, data=data, flag=flag, axes=axes,
                        datatype='gain amplitude', spw=spwid,
                        ant=ants)

                    # add the view results and their children results to the
                    # class result structure
                    self.result.addview(viewresult.description, viewresult)

