import enum
import functools
import itertools
import math
import os

import numpy
import pipeline.domain.measures as measures
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.sessionutils as sessionutils
import pipeline.infrastructure.utils as utils
import pipeline.infrastructure.vdp as vdp
from pipeline.hif.tasks import gaincal
from pipeline.hif.tasks.bandpass import bandpassmode, bandpassworker
from pipeline.hif.tasks.bandpass.common import BandpassResults, SolintAdjustment
from pipeline.hifa.heuristics import phasespwmap
from pipeline.hifa.tasks.bpsolint import bpsolint, BpSolintResults
from pipeline.infrastructure import callibrary
from pipeline.infrastructure import casa_tools
from pipeline.infrastructure import exceptions
from pipeline.infrastructure import task_registry
from pipeline.infrastructure.pipelineqa import TargetDataSelection
from pipeline.infrastructure.utils.math import round_up

LOG = infrastructure.get_logger(__name__)


__all__ = [
    'ALMAPhcorBandpassInputs',
    'SerialALMAPhcorBandpass',
    'ALMAPhcorBandpass',    
    'SessionALMAPhcorBandpass',
    'SessionALMAPhcorBandpassInputs'
]


class LowSNRPhaseupSolintOrigin(enum.Enum):
    """
    Enumeration of all possible hierarchy values for SolintAdjustment.

    These values represent the different scenarios where phase-up solution
    intervals may be adjusted during bandpass calibration.
    """

    # When no SNR results are available
    NO_SNR_RESULT = "bandpass.solint.no_snr_result"

    # When SNR result does not contain data for expected spws
    SPWS_MISSING_DATA = "bandpass.solint.insufficient_data"

    # When insufficient points are present in the solution
    INSUFFICIENT_POINTS = "bandpass.solint.insufficient_points"

    # When insufficient channels to use smoothing
    TOO_FEW_CHANNELS ="bandpass.solint.too_few_channels"

    # When solint is less than integration time
    LT_INTEGRATION_TIME = "bandpass.solint.lt_integration_time"

    # Regular phaseup solint adjustments
    UNCOMBINED_GT_PHASEUPMAXSOLINT = "phaseup.solint.uncombined.gt_phaseupmaxsolint"
    UNCOMBINED_LE_PHASEUPMAXSOLINT = "phaseup.solint.uncombined.le_phaseupmaxsolint"

    # Combined SpW phaseup solint adjustments
    COMBINED_MIN_BEST_LE_INTEGRATION_TIME = (
        "phaseup.solint.combined.min_best_le_integration_time"
    )
    COMBINED_LE_INTEGRATION_TIME = "phaseup.solint.combined.le_integration_time"
    COMBINED_GT_PHASEUPMAXSOLINT = "phaseup.solint.combined.gt_phaseupmaxsolint"
    COMBINED_LT_PHASEUPMAXSOLINT = "phaseup.solint.combined.lt_phaseupmaxsolint"


class ALMAPhcorBandpassInputs(bandpassmode.BandpassModeInputs):
    bpnsols = vdp.VisDependentProperty(default=8)
    bpsnr = vdp.VisDependentProperty(default=50.0)
    minbpsnr = vdp.VisDependentProperty(default=20.0)
    evenbpints = vdp.VisDependentProperty(default=True)

    # Boolean declaring how to populate the bandpass solution parameter
    # "fillgaps" (PIPE-2116, also depends on hm_bandpass modes).
    hm_auto_fillgaps = vdp.VisDependentProperty(default=True)

    # Bandpass heuristics, options are 'fixed', 'smoothed', and 'snr'
    hm_bandpass = vdp.VisDependentProperty(default='snr')

    @hm_bandpass.convert
    def hm_bandpass(self, value):
        allowed = ('fixed', 'smoothed', 'snr')
        if value not in allowed:
            m = ', '.join(('{!r}'.format(i) for i in allowed))
            raise ValueError('Value not in allowed value set ({!s}): {!r}'.format(m, value))
        return value

    # PIPE-2442: SpW combination heuristic for phase-up in bandpass task.
    # Options are 'snr', 'always', and 'never'.
    hm_phaseup_combine = vdp.VisDependentProperty(default='snr')

    @hm_phaseup_combine.convert
    def hm_phaseup_combine(self, value):
        allowed = ('snr', 'always', 'never')
        if value not in allowed:
            m = ', '.join(('{!r}'.format(i) for i in allowed))
            raise ValueError('Value not in allowed value set ({!s}): {!r}'.format(m, value))
        return value

    # Phaseup heuristics, options are '', 'manual' and 'snr'
    hm_phaseup = vdp.VisDependentProperty(default='snr')

    @hm_phaseup.convert
    def hm_phaseup(self, value):
        allowed = ('', 'manual', 'snr')
        if value not in allowed:
            m = ', '.join(('{!r}'.format(i) for i in allowed))
            raise ValueError('Value not in allowed value set ({!s}): {!r}'.format(m, value))
        return value

    maxchannels = vdp.VisDependentProperty(default=240)
    phaseupbw = vdp.VisDependentProperty(default='')
    phaseupmaxsolint = vdp.VisDependentProperty(default=60.0)
    phaseupnsols = vdp.VisDependentProperty(default=2)
    phaseupsnr = vdp.VisDependentProperty(default=20.0)
    phaseupsolint = vdp.VisDependentProperty(default='int')
    solint = vdp.VisDependentProperty(default='inf')
    # PIPE-628: new parameter to unregister existing bcals before appending to callibrary
    unregister_existing = vdp.VisDependentProperty(default=False)

    parallel = sessionutils.parallel_inputs_impl(default=False)

    def __init__(self, context, output_dir=None, vis=None, mode='channel', hm_phaseup=None, phaseupbw=None,
                 phaseupmaxsolint=None, phaseupsolint=None, phaseupsnr=None, phaseupnsols=None, hm_phaseup_combine=None,
                 hm_bandpass=None, solint=None, maxchannels=None, evenbpints=None, bpsnr=None, minbpsnr=None,
                 bpnsols=None, unregister_existing=None, hm_auto_fillgaps=None, parallel=None, **parameters):
        """Initialize Inputs.

        Args:
            context: Pipeline context.

            output_dir: Output directory.
                Defaults to None, which corresponds to the current working directory.

            vis: List of input MeasurementSets. Defaults to the list of
                MeasurementSets specified in the pipeline context.

                Example: vis=['ngc5921.ms']

            mode: Type of bandpass solution. Currently only supports the
                default value of 'channel' (corresponding to bandtype='B' in
                CASA bandpass) to perform a channel-by-channel solution for each
                spw.

            hm_phaseup: The pre-bandpass solution phaseup gain heuristics. The
                options are:

                - 'snr': compute solution required to achieve the specified SNR
                - 'manual': use manual solution parameters
                - '': skip phaseup

                Example: hm_phaseup='manual'

            phaseupbw: Bandwidth to be used for phaseup. Used when
                ``hm_phaseup`` = 'manual'.

                Example:

                - phaseupbw='' to use entire bandpass
                - phaseupbw='500MHz' to use central 500MHz

            phaseupmaxsolint: Maximum phase correction solution interval (in
                seconds) allowed in very low-SNR cases. Used only when
                ``hm_phaseup`` = 'snr'.

                Example: phaseupmaxsolint=60.0

            phaseupsolint: The phase correction solution interval in CASA syntax.
                Used when ``hm_phaseup`` = 'manual' or as a default if
                the ``hm_phaseup`` = 'snr' heuristic computation fails.

                Example: phaseupsolint='300s'

            phaseupsnr: The required SNR for the phaseup solution. Used to calculate
                the phaseup time solint, and only if ``hm_phaseup`` = 'snr'.

                Example: phaseupsnr=10.0

            phaseupnsols: The minimum number of phaseup gain solutions. Used only
                if ``hm_phaseup`` = 'snr'.

                Example: phaseupnsols=4

            hm_phaseup_combine: The spw combination heuristic for the phase-up
                solution. Accepts one of following 3 options:

                - 'snr', default: heuristics will use combine='spw' in phase-up
                  gaincal, when SpWs have SNR < phaseupsnr (default = 20).
                - 'always': heuristic will force combine='spw' in the phase-up
                  gaincal.
                - 'never': heuristic will not use spw combination; this was the
                  default logic for Pipeline release 2024 and prior.

                Example: hm_phaseup_combine='always'

            hm_bandpass: The bandpass solution heuristics. The options are:
                'snr': compute the solution required to achieve the specified SNR
                'smoothed': simple 'smoothing' i.e. spectral solint>1chan
                'fixed': use the user defined parameters for all spws

                Example: hm_bandpass='snr'

            solint: Time and channel solution intervals in CASA syntax.
                Default is solint='inf', which is used when
                ``hm_bandpass`` = 'fixed'.
                If ``hm_bandpass`` = 'snr', then the task will attempt
                to compute and use an optimal SNR-based solint (and warn
                if this solint is not good enough).
                If ``hm_bandpass`` = 'smoothed', the task will override
                the spectral solint with bandwidth/maxchannels.

                Example: solint='int'

            maxchannels: The bandpass solution 'smoothing' factor in channels,
                i.e. spectral solint will be set to bandwidth / maxchannels
                Set to 0 for no smoothing. Used if
                ``hm_bandpass`` = 'smoothed'.

                Example: maxchannels=240

            evenbpints: Force the per spw frequency solint to be evenly divisible
                into the spw bandpass if ``hm_bandpass`` = 'snr'.

                Example: evenbpints=False

            bpsnr: The required SNR for the bandpass solution. Used only if
                ``hm_bandpass`` = 'snr'.

                Example: bpsnr=30.0

            minbpsnr: The minimum required SNR for the bandpass solution
                when strong atmospheric lines exist in Tsys spectra.
                Used only if ``hm_bandpass``='snr'.

                Example: minbpsnr=10.0

            bpnsols: The minimum number of bandpass solutions. Used only if
                ``hm_bandpass`` = 'snr'.

                Example: bpnsols=8

            unregister_existing: Unregister all bandpass calibrations from the pipeline
                context before registering the new bandpass calibrations
                from this task. Defaults to False.

                Example: unregister_existing=True

            hm_auto_fillgaps: If True, then the ``hm_bandpass`` = 'snr' or 'smoothed'
                modes, that solve bandpass per SpW, are performed with
                CASA bandpass task parameter 'fillgaps' set to a quarter
                of the respective SpW bandwidth (in channels).
                If False, then these bandpass solves will use
                fillgaps=0.
                The ``hm_bandpass`` = 'fixed' mode is unaffected by
                ``hm_auto_fillgaps`` and always uses fillgaps=0.

            caltable: List of names for the output calibration tables. Defaults
                to the standard pipeline naming convention.

                Example: caltable=['ngc5921.gcal']

            field: The list of field names or field ids for which
                bandpasses are computed. Set to field='' by default,
                which means the task will select all fields.

                Example: field='3C279', field='3C279,M82'

            intent: A string containing a comma delimited list of intents
                against which the selected fields are matched. Set to
                intent='' by default, which means the task will select
                all data with the BANDPASS intent.

                Example: intent='`*PHASE*`'

            spw: The list of spectral windows and channels for which
                bandpasses are computed. Set to spw='' by default, which
                means the task will select all science spectral windows.

                Example: spw='11,13,15,17'

            antenna: Set of data selection antenna IDs

            combine: Data axes to combine for solving. Axes are '', 'scan',
                'spw', 'field' or any comma-separated combination.

                Example: combine='scan,field'

            refant: List of reference antenna names. Defaults to the
                value(s) stored in the pipeline context. If undefined in
                the pipeline context defaults to the CASA reference
                antenna naming scheme.

                Example: refant='DV06,DV07'

            solnorm: Normalise the bandpass solution; defaults to True.

                Example: solnorm=False

            minblperant: Minimum number of baselines required per antenna for
                each solve. Antennas with fewer baselines are excluded
                from solutions.

                Example: minblperant=4

            minsnr: Solutions below this SNR are rejected in the phaseup and
                bandpass solves.

                Example: minsnr=3.0

            parallel: Process multiple MeasurementSets in parallel using the casampi parallelization framework.
                options: 'automatic', 'true', 'false', True, False
                default: None (equivalent to False)

        """
        super().__init__(context, output_dir=output_dir, vis=vis, mode=mode, **parameters)
        self.bpnsols = bpnsols
        self.bpsnr = bpsnr
        self.minbpsnr = minbpsnr
        self.evenbpints = evenbpints
        self.hm_auto_fillgaps = hm_auto_fillgaps
        self.hm_bandpass = hm_bandpass
        self.hm_phaseup_combine = hm_phaseup_combine
        self.hm_phaseup = hm_phaseup
        self.maxchannels = maxchannels
        self.phaseupbw = phaseupbw
        self.phaseupmaxsolint = phaseupmaxsolint
        self.phaseupnsols = phaseupnsols
        self.phaseupsnr = phaseupsnr
        self.phaseupsolint = phaseupsolint
        self.solint = solint
        self.unregister_existing = unregister_existing
        self.parallel = parallel



class SerialALMAPhcorBandpass(bandpassworker.BandpassWorker):
    Inputs = ALMAPhcorBandpassInputs

    def prepare(self, **parameters):
        inputs = self.inputs
        solint_adjustments: list[SolintAdjustment] = []

        if inputs.unregister_existing:
            # Unregister old bandpass calibrations to stop them from being preapplied
            # when calculating phase-ups, etc.

            # predicate function that triggers when a bandpass caltable is detected
            def bandpass_matcher(_: callibrary.CalToArgs, calfrom: callibrary.CalFrom) -> bool:
                return 'bandpass' in calfrom.caltype

            LOG.info('Temporarily unregistering all previous bandpass calibrations while task executes')
            inputs.context.callibrary.unregister_calibrations(bandpass_matcher)

        # Call the SNR estimater if either
        #     hm_phaseup='snr'
        # or
        #     hm_bandpass='snr'
        if inputs.hm_phaseup == 'snr' or inputs.hm_bandpass == 'snr':
            snr_result = self._compute_bpsolints()
        else:
            snr_result = None

        # If requested, execute a phaseup job. This will add the resulting
        # caltable to the on-the-fly calibration context, so we don't need any
        # subsequent gaintable manipulation
        if inputs.hm_phaseup != '':
            # If requested and available, use the SNR results to determine the
            # optimal values for combine and solution interval.
            if inputs.hm_phaseup == 'snr' and snr_result.spwids:
                phaseup_solint, phaseup_combine, phaseup_snr_expected, adjustments = self._get_best_phaseup_solint(snr_result)
                solint_adjustments.extend(adjustments)
            # Otherwise, skip determination of optimal values, and stick with
            # default values, i.e. use the input phase solint, and use the
            # default of no spw combination unless explicitly forced by user.
            else:
                # Log warning if optimal determination was requested but not
                # possible due to missing SNR results.
                if inputs.hm_phaseup == 'snr':
                    LOG.warning('SNR based phaseup solint estimates are unavailable for MS %s' % inputs.ms.basename)
                phaseup_solint = inputs.phaseupsolint
                phaseup_combine = 'spw' if inputs.hm_phaseup_combine == 'always' else ''
                phaseup_snr_expected = None

            # Report choice for solint and combine (when applicable), and
            # compute temporary spw-to-spw phase offset caltable if necessary.
            if phaseup_combine == '':
                LOG.info("Using phaseup solint of '%s' in MS %s" % (phaseup_solint, inputs.ms.basename))
                phasediff_result = None
            else:
                LOG.info("Using combine='spw' and phaseup solint of '%s' in MS %s" % (phaseup_solint, inputs.ms.basename))

                # Compute the spw-to-spw phase offsets cal table and accept into
                # local context.
                LOG.info(f'{inputs.ms.basename}: since phaseup will use spw combination, first computing temporary'
                         f' spw-to-spw phase offsets table to use in pre-apply.')
                phasediff_result = self._do_phaseup(solint='inf')

            # Run the phase-up task.
            phaseup_result = self._do_phaseup(combine=phaseup_combine, solint=phaseup_solint)

        # Now perform the bandpass
        if inputs.hm_bandpass == 'snr':
            if len(snr_result.spwids) <= 0:
                LOG.warning('SNR based bandpass solint estimates are unavailable for MS %s' % inputs.ms.basename)
            else:
                LOG.info('Using SNR based solint estimates')
            result = self._do_snr_bandpass(snr_result)
        elif inputs.hm_bandpass == 'smoothed':
            LOG.info('Using simple bandpass smoothing solint estimates')
            result = self._do_smoothed_bandpass()
        else:
            LOG.info('Using fixed solint estimates')
            result = self._do_bandpass()

        # Attach the preparatory results to the final result so we have a
        # complete log of all the executed tasks.
        if inputs.hm_phaseup != '':
            if phasediff_result:
                result.preceding.append(phasediff_result.final)
            result.preceding.append(phaseup_result.final)
            # PIPE-2442: add phase-up SNR to the final result for QA scoring.
            result.phaseup_snr_expected = phaseup_snr_expected

            # PIPE-1624: Store bandpass phaseup caltable table name so it
            # can be saved into the context. Do not use the version in
            # preceding.append (above), as it is labeled "deprecated"
            for cal in phaseup_result.final:
                result.phaseup_caltable_for_phase_rms.append(cal.gaintable)

        # PIPE-628: set whether we should unregister old bandpass calibrators
        # on results acceptance
        result.unregister_existing = inputs.unregister_existing

        # PIPE-1760: pull bpsolint messages etc. up into result for optional printing as a QA warning
        result.solint_adjustments.extend(solint_adjustments)
        if snr_result:
            result.low_channel_solutions = snr_result.low_channel_solutions

        return result

    # Compute the solints required to match the SNR
    def _compute_bpsolints(self) -> BpSolintResults:
        inputs = self.inputs

        # Note currently the phaseup bandwidth is not supported
        bpsolint_inputs = bpsolint.BpSolint.Inputs(inputs.context,
            vis            = inputs.vis,
            field          = inputs.field,
            intent         = inputs.intent,
            spw            = inputs.spw,
            phaseupsnr     = inputs.phaseupsnr,
            minphaseupints = inputs.phaseupnsols,
            evenbpints     = inputs.evenbpints,
            bpsnr          = inputs.bpsnr,
            minbpsnr       = inputs.minbpsnr,
            minbpnchan    = inputs.bpnsols
        )

        bpsolint_task = bpsolint.BpSolint(bpsolint_inputs)
        return self._executor.execute(bpsolint_task)

    # Returns the best solint, spw mapping, expected SNR, and solint
    # adjustments for the bandpass phase-up solution that will be pre-applied
    # during 'bandpass'.
    def _get_best_phaseup_solint(
            self,
            snr_result: bpsolint.BpSolintResults
    ) -> tuple[str, str, float | None, list[SolintAdjustment]]:
        """
        Use SNR results (incl. optimal bandpass solution intervals) to select
        the best solution interval and spw combination setting to use in the
        phase-up, and the expected phase-up SNR.

        Args:
            snr_result: dictionary with SNR results for each SpW.

        Returns:
            4-tuple containing:
            - phase-up solution interval
            - phase-up combine setting
            - expected phase-up SNR
            - list of solint adjustments
        """
        inputs = self.inputs
        quanta = casa_tools.quanta

        # holds adjustments made to solint. For hifa_bandpassflag these become QA scores
        adjustments: list[SolintAdjustment] = []

        # If the SNR results are empty, then no optimal solint can be
        # determined. In this case, log a warning, and return early with the
        # default input phaseup solint and phaseup combine.
        if not snr_result.spwids:
            LOG.info(f"{inputs.ms.basename}: no SNR results available, therefore unable to determine optimal phaseup"
                        f" solint. Reverting to phaseup solint default {inputs.phaseupsolint}.")
            phase_combine = 'spw' if inputs.hm_phaseup_combine == 'always' else ''
            adjustments.append(
                SolintAdjustment(
                    applies_to=TargetDataSelection(vis={inputs.ms.basename}),
                    original="",
                    adjusted=inputs.phaseupsolint,
                    threshold="",
                    origin=LowSNRPhaseupSolintOrigin.NO_SNR_RESULT.value,
                    reason=f"SNR results expected but unavailable",
                )
            )
            return inputs.phaseupsolint, phase_combine, None, adjustments

        # PIPE-2442: select which SpWs to consider in determination of best
        # solint, and retrieve the corresponding indices of those SpWs in the
        # SNR result structure.
        if inputs.ms.is_band_to_band:
            # For Band-to-Band datasets, only refine solint based on the TARGET
            # (high frequency) spectral windows that are expected to have the
            # lowest SNRs.
            LOG.info(
                '%s is a Band-to-Band dataset: selecting high-frequency SpWs for solint refinement.', inputs.ms.basename
            )
            spwindex = [
                snr_result.spwids.index(s.id)
                for s in inputs.ms.get_spectral_windows(inputs.spw, intent='TARGET')
            ]
        else:
            # For all other datasets, restrict the refinement to the SpWs of a
            # single SpectralSpec. Start with retrieving mapping of SpectralSpec
            # to science spectral windows.
            spspec_to_spwid = utils.get_spectralspec_to_spwid_map(inputs.ms.get_spectral_windows(inputs.spw))

            # If there is only 1 SpectralSpec, then use that one.
            if len(spspec_to_spwid) == 1:
                spwindex = [snr_result.spwids.index(s) for s in next(iter(spspec_to_spwid.values()))]
            # Otherwise, with 2+ SpectralSpec, select which SpectralSpec to use.
            # PIPE-2442: in this case, it is assumed that the representative
            # SpectralSpec to use is the one that has the lowest value of
            # maximum SNR for its SpWs.
            else:
                # Identify the maximum SNR for the SpWs in each SpectralSpec.
                max_snr_spspec = []
                for spwids in spspec_to_spwid.values():
                    # Get the indices of these SpWs into the SNR result.
                    spwi = [snr_result.spwids.index(s) for s in spwids]

                    # Identify SNRs for all SpWs in this SpectralSpec. It is
                    # possible for "phintsnrs" in the SNR result to contain None
                    # and those are immediately rejected.
                    snrs = [snr_result.phintsnrs[i] for i in spwi if snr_result.phintsnrs[i] is not None]

                    # If at least one valid SNR was found, then compute the
                    # maximum SNR, and store the outcome for this SpectralSpec
                    # as the corresponding spw index and max SNR. If no valid
                    # SNRs were found (i.e. all were None), then this
                    # SpectralSpec and its SpWs are rejected from consideration.
                    if snrs:
                        max_snr_spspec.append((spwi, max(snrs)))

                # If a maximum SNR was found for at least one SpectralSpec, then
                # proceed to identify the SpectralSpec with the lowest max SNR,
                # and use its corresponding spw index.
                if max_snr_spspec:
                    spwindex =  min(max_snr_spspec, key=lambda x: x[1])[0]
                # Otherwise, in the unlikely scenario that no valid SNRs were
                # found for any SpW of any SpectralSpec, proceed with an empty
                # spw index.
                else:
                    spwindex = []

        # If there are no valid SpWs, or the SNR results are missing optimal
        # solint values for all selected SpWs, then no optimal solint can be
        # determined. In this case, log a warning, and return early with the
        # default input phaseup solint and phaseup combine.
        if not spwindex or not any(snr_result.phsolints[i] for i in spwindex):
            LOG.info(
                f"{inputs.ms.basename}: no SNR results available for any of the expected SpWs, therefore unable"
                f" to determine optimal phaseup solint. Reverting to phaseup solint default {inputs.phaseupsolint}."
            )
            phase_combine = 'spw' if inputs.hm_phaseup_combine == 'always' else ''
            adjustments.append(
                SolintAdjustment(
                    applies_to=TargetDataSelection(vis={inputs.ms.basename}),
                    original="",
                    adjusted=inputs.phaseupsolint,
                    threshold="",
                    origin=LowSNRPhaseupSolintOrigin.SPWS_MISSING_DATA.value,
                    reason=f"SNR results not available for any of the expected spws",
                )
            )
            return inputs.phaseupsolint, phase_combine, None, adjustments

        # Since SNR results are not empty, then use the first available SpW to
        # determine the scan integration time as a timedelta object. It is
        # assumed that all scans for all SpWs are taken with the exact same
        # integration interval.
        scans = inputs.ms.get_scans(scan_intent=inputs.intent)
        mean_intervals = {scan.mean_interval(snr_result.spwids[0])
                          for scan in scans if snr_result.spwids[0] in [spw.id for spw in scan.spws]}
        timedelta = mean_intervals.pop()
        timedelta_integration_time = timedelta.total_seconds()

        # int time is needed to calculate QA score and does not change from here on in
        adjustment_cls = functools.partial(SolintAdjustment, integration_time=timedelta_integration_time)

        # Determine best solution interval based on SNR results for each SpW
        # under consideration.
        spwids = []
        phintsnrs = []
        bestsolint = []
        for i in spwindex:
            # No solution available for this SpW.
            if not snr_result.phsolints[i]:
                # This per-spw warning is distinct from the early return on
                # L585, which is a global warning for all spws
                LOG.warning('No phaseup solint estimate for spw %s in MS %s' %
                            (snr_result.spwids[i], inputs.ms.basename))
                continue

            # Otherwise, keep this SpW under consideration and store its SNR
            # estimate.
            spwids.append(snr_result.spwids[i])
            phintsnrs.append(snr_result.phintsnrs[i])

            # If the number of phase solutions in the SNR result was below the
            # minimum number of phaseup gain solution points:
            if snr_result.nphsolutions[i] < inputs.phaseupnsols:
                # The solint in the SNR result is not usable, and instead the
                # best solint for this SpW is set to achieve the minimum number
                # of phase solutions (dividing exposure time by phaseupnsols).
                # Note: exposure time in SNR result is a string including unit,
                # so using quanta here to get the value as a float.
                newsolint = quanta.quantity(snr_result.exptimes[i])['value'] / inputs.phaseupnsols
                bestsolint.append(newsolint)

                # Depending on whether spw combination is an option, either log
                # a message or solint adjustment (=QA warning) that there were
                # too few phaseup solution points.
                msg = (
                    f"{inputs.ms.basename}: phaseup solution for spw {snr_result.spwids[i]} has only"
                    f" {snr_result.nphsolutions[i]} points; reducing estimated phaseup solint from"
                    f" {snr_result.phsolints[i]:0.3f}s to {newsolint:0.3f}s."
                )
                if inputs.hm_phaseup_combine == "never":
                    adjustments.append(
                        adjustment_cls(
                            applies_to=TargetDataSelection(vis={inputs.ms.basename}, spw={snr_result.spwids[i]}),
                            original=snr_result.phsolints[i],
                            adjusted=newsolint,
                            threshold=inputs.phaseupnsols,
                            origin=LowSNRPhaseupSolintOrigin.INSUFFICIENT_POINTS.value,
                            reason=f"Insufficient phase-up solution points for spw {snr_result.spwids[i]}, adjusting solint to {newsolint:0.3f}",
                        )
                    )
                else:
                    msg += f" However, the option to combine spw will trigger a recalculation of solint."
                LOG.info(msg)
            # Otherwise, adopt for this SpW the solint from the SNR result.
            else:
                # Using quanta here to cast to same type as above.
                bestsolint.append(quanta.quantity(snr_result.phsolints[i])['value'])

        max_bestsolint = max(bestsolint)
        min_bestsolint = min(bestsolint)
        spw_of_max_bestsolint = spwids[bestsolint.index(max_bestsolint)]

        # If the best solution interval for all evaluated SpWs are all
        # smaller/equal to the integration time, then the required SNR can be
        # reached by setting solint to "int". No SpW combination is necessary
        # but may have been explicitly forced by user input. Return early with
        # this outcome:
        if max_bestsolint <= timedelta_integration_time:
            LOG.info(f"{inputs.ms.basename}: the largest optimal solint, {max_bestsolint:.3f}s, is smaller than"
                     f" the integration time, {timedelta_integration_time:.3f}s, setting solint to 'int'.")
            if inputs.hm_phaseup_combine == 'always':
                phase_combine = 'spw'
                snr_expected = numpy.linalg.norm(phintsnrs)
            else:
                phase_combine = ''
                snr_expected = min(phintsnrs)

            adjustments.append(
                adjustment_cls(
                    applies_to=TargetDataSelection(vis={inputs.ms.basename}, spw={spw_of_max_bestsolint}),
                    original=max_bestsolint,
                    adjusted="int",
                    threshold=timedelta_integration_time,
                    origin=LowSNRPhaseupSolintOrigin.LT_INTEGRATION_TIME.value,
                    reason=f"Largest optimal solint in spw {spw_of_max_bestsolint} still less than integration time {timedelta_integration_time:.3f}, adjusting solint to 'int'",
                )
            )
            return 'int', phase_combine, snr_expected, adjustments

        # Otherwise, the maximum best solution interval was above the
        # integration time, and it may be possible to use SpW combination to
        # improve the SNR.
        LOG.info(f"{inputs.ms.basename}: the largest optimal solint, {max_bestsolint:.3f}s, is larger than"
                 f" the integration time, {timedelta_integration_time:.3f}s.")

        # these variables are used to annotate the SolintAdjustment with the
        # appropriate reasons and threshold information.
        original_solint: float
        decision_threshold: float
        metric_identifier: str
        reason: str
        # this will be mutated as required by the metric
        applies_to = TargetDataSelection(vis={inputs.ms.basename})

        # If the task input explicitly disabled the option of combining SpWs,
        # then stick to the solint selection heuristic from PL2024 and earlier,
        # to pick the largest optimal solint that was determined for the SpWs
        # but capped to maximum set by inputs.phaseupmaxsolint.
        if inputs.hm_phaseup_combine == 'never':
            # Combine is explicitly disabled for phase-up.
            LOG.info(f"{inputs.ms.basename}: SpW combination for phase-up is explicitly set to 'never' in task inputs"
                     f" and will therefore not be considered as an option for SNR improvement.")
            phaseup_combine = ''

            # If the largest optimal solint is greater than the maximum allowed
            # value:
            if max_bestsolint > inputs.phaseupmaxsolint:
                # Set the solution interval to the maximum allowed value, but
                # slightly adjust the value to round it to the nearest integer
                # multiple of the integration time. Use quanta to turn into a
                # string with unit, and restrict to 3 significant digits.
                finalfactor = round_up(inputs.phaseupmaxsolint / timedelta_integration_time)
                finalsolint = quanta.tos(quanta.quantity(timedelta_integration_time * finalfactor, 's'), 3)
                snr_expected = numpy.sqrt(finalfactor) * min(phintsnrs)
                LOG.info(
                    f"{inputs.ms.basename}: the largest optimal solint, {max(bestsolint):.3f}s, is greater than"
                    f" {inputs.phaseupmaxsolint}s, adjusting to {finalsolint}."
                )

                applies_to.spw |= {spw_of_max_bestsolint}
                metric_identifier = LowSNRPhaseupSolintOrigin.UNCOMBINED_GT_PHASEUPMAXSOLINT.value
                original_solint = max_bestsolint
                decision_threshold = inputs.phaseupmaxsolint
                reason = f"Largest optimal solint greater than {decision_threshold}s, adjusting to {finalsolint}"

                # Identify for which SpWs the derived optimal solint was larger
                # than the maximum allowed value, and then warn that those SpWs
                # will have a low phaseup SNR.
                low_snr_spws = [str(spwid) for bsi, spwid in zip(bestsolint, spwids) if bsi > inputs.phaseupmaxsolint]
                if low_snr_spws:
                    LOG.info(
                        f"{inputs.ms.basename}: spw(s) {utils.commafy(low_snr_spws, False)} will have a"
                        f" low phaseup gaincal SNR = {snr_expected}, which is < input phase-up SNR threshold"
                        f" ({inputs.phaseupsnr})."
                    )

            # Otherwise, the largest derived optimal solint must be above the
            # integration time but below the maximum allowed value:
            else:
                # Set the solution interval to the largest derived optimal
                # solint but slightly adjust the value to round it to the
                # nearest integer multiple of the integration time. Use quanta
                # to turn into a string with unit, and restrict to 3 significant
                # digits.
                finalfactor = round_up(max_bestsolint / timedelta_integration_time)
                finalsolint = quanta.tos(quanta.quantity(timedelta_integration_time * finalfactor, 's'), 3)
                snr_expected = numpy.sqrt(finalfactor) * min(phintsnrs)

                metric_identifier = LowSNRPhaseupSolintOrigin.UNCOMBINED_LE_PHASEUPMAXSOLINT.value
                original_solint = max_bestsolint
                decision_threshold = inputs.phaseupmaxsolint
                reason = f"Largest optimal solint less than {decision_threshold}s, adjusting to {finalsolint}"

                LOG.info(f"{inputs.ms.basename}: setting solint to {finalsolint}.")

        # Otherwise, the optimal derived solint for at least one SpW was larger
        # than the integration time, and SpW combination is available as an
        # option, so continue with the new PL2025 heuristic (PIPE-2442) to find
        # an optimal solution interval for SpW combination, based on aggregate
        # bandwidth.
        else:
            LOG.info(f"{inputs.ms.basename}: combining SpWs to improve phaseup SNR.")
            phaseup_combine = 'spw'

            # If the smallest optimal solint, to achieve the required SNR, was
            # smaller than the integration time for at least one SpW, then the
            # SNR will only improve with more bandwidth after combining SpWs,
            # so "int" will be the minimum optimal solint for combine='spw'.
            if min_bestsolint <= timedelta_integration_time:
                LOG.info(f"{inputs.ms.basename}: optimal solint based on aggregate bandwidth is 'int'.")
                finalsolint = 'int'
                snr_expected = numpy.linalg.norm(phintsnrs)

                metric_identifier = LowSNRPhaseupSolintOrigin.COMBINED_MIN_BEST_LE_INTEGRATION_TIME.value
                original_solint = min_bestsolint
                decision_threshold = timedelta_integration_time
                reason = f"Optimal solint based on aggregate bandwidth is {finalsolint}"

            # Otherwise, a new optimal solint based on the aggregate bandwidth
            # through SpW combination needs to be computed here.
            else:
                LOG.info(f"{inputs.ms.basename}: computing optimal solint based on aggregate bandwidth.")

                # Identify SpW with smallest optimal solint.
                spwid_min_solint = spwids[bestsolint.index(min_bestsolint)]

                # Determine the aggregate bandwidth for all SpWs originally
                # under consideration, including any for which there may not
                # have been a valid entry in SNR result, hence use origina
                # spwindex instead of spwids.
                sum_bw = sum(inputs.ms.get_spectral_window(snr_result.spwids[i]).bandwidth.value for i in spwindex)

                # Set bandwidth scaling factor to bandwidth of SpW with the
                # smallest optimal solint divided by the aggregate bandwidth of
                # the SpWs under consideration.
                bwfactor = float(inputs.ms.get_spectral_window(spwid_min_solint).bandwidth.value / sum_bw)

                # Set the solint for the SpW combination gaincal by scaling the
                # smallest optimal solint with the bandwidth scaling factor,
                # and ensuring this is rounded up (ceil) to next nearest integer
                # multiple of the integration time.
                combfactor = math.ceil(min_bestsolint * bwfactor / timedelta_integration_time)
                combinesolint = timedelta_integration_time * combfactor

                # Check how the newly determined optimal solint for combining
                # SpWs compares to the integration time and the maximum allowed
                # solint.
                #
                # If the optimal combined solint is smaller/equal to the
                # integration time, then set the solint to 'int'.
                if combinesolint <= timedelta_integration_time:
                    finalsolint = 'int'
                    snr_expected = numpy.linalg.norm(phintsnrs)

                    metric_identifier = LowSNRPhaseupSolintOrigin.COMBINED_LE_INTEGRATION_TIME.value
                    original_solint = combinesolint
                    decision_threshold = timedelta_integration_time
                    reason = f"Optimal combined solint <= integration time ({timedelta_integration_time})"

                # If the optimal combined solint is still greater than the
                # maximum allowed value (i.e. really low SNR scenario):
                elif combinesolint > inputs.phaseupmaxsolint:
                    # Set the solution interval to the maximum allowed value,
                    # but slightly adjust the value to round it to the nearest
                    # integer multiple of the integration time. Use quanta to
                    # turn into a string with unit, and restrict to 3
                    # significant digits.
                    finalfactor = round_up(inputs.phaseupmaxsolint / timedelta_integration_time)
                    finalsolint = quanta.tos(quanta.quantity(timedelta_integration_time * finalfactor, 's'), 3)
                    snr_expected = numpy.sqrt(finalfactor) * numpy.linalg.norm(phintsnrs)
                    LOG.info(
                        f"{inputs.ms.basename}: the combined spw solution interval, {combinesolint:.3f}s, is"
                        f" greater than {inputs.phaseupmaxsolint}s, adjusting to {finalsolint}, solution SNR"
                        f" = {snr_expected:.2f}, < {inputs.phaseupsnr}."
                    )

                    metric_identifier = LowSNRPhaseupSolintOrigin.COMBINED_GT_PHASEUPMAXSOLINT.value
                    original_solint = combinesolint
                    decision_threshold = inputs.phaseupmaxsolint
                    reason = f"Combined solution interval greater than upper limit ({inputs.phaseupmaxsolint})"

                # Otherwise, proceed with the optimal combined solint.
                else:
                    # Use quanta to turn into a string with unit, and restrict
                    # to 3 significant digits.
                    finalsolint = quanta.tos(quanta.quantity(combinesolint), 3)
                    snr_expected = numpy.sqrt(combfactor) * numpy.linalg.norm(phintsnrs)

                    metric_identifier = LowSNRPhaseupSolintOrigin.COMBINED_LT_PHASEUPMAXSOLINT.value
                    original_solint = combinesolint
                    decision_threshold = inputs.phaseupmaxsolint
                    reason = f"Combined solution interval less than upper limit ({inputs.phaseupmaxsolint})"

        adjustments.append(
            adjustment_cls(
                applies_to=applies_to,
                original=original_solint,
                adjusted=finalsolint,
                threshold=decision_threshold,
                origin=metric_identifier,
                reason=reason,
            )
        )

        return finalsolint, phaseup_combine, snr_expected, adjustments

    # Compute the phaseup solution.
    def _do_phaseup(self, combine='', solint='int'):
        inputs = self.inputs

        # Set input parameters for phase gaincal.
        phaseup_inputs = gaincal.GTypeGaincal.Inputs(
            inputs.context,
            vis=inputs.vis,
            field=inputs.field,
            spw=self._get_phaseup_spw(),
            antenna=inputs.antenna,
            intent=inputs.intent,
            solint=solint,
            combine=combine,
            refant=inputs.refant,
            minblperant=inputs.minblperant,
            calmode='p',
            minsnr=inputs.minsnr
        )

        # Create and run gaincal task.
        phaseup_task = gaincal.GTypeGaincal(phaseup_inputs)
        result = self._executor.execute(phaseup_task, merge=False)

        # Log warning if gaincal did not return a caltable.
        if not result.final:
            LOG.warning(f"No bandpass {'phase offsets' if solint == 'inf' else 'phaseup'} solution for "
                        f" {inputs.ms.basename}.")
        else:
            # If the phaseup uses SpW combination, then first update the
            # CalApplication to add in a spectral window mapping.
            if combine == 'spw':
                # Retrieve a mapping for combining the science SpWs.
                scispws = inputs.ms.get_spectral_windows(task_arg=inputs.spw)
                spwmap = phasespwmap.combine_spwmap(scispws)
                LOG.info(f"{inputs.ms.basename} - combined spw map for phaseup solution: {spwmap}.")

                # There should be only a single CalApplication, so replace that
                # one with the modified CalApplication that includes the SpW
                # mapping.
                modified_calapp = callibrary.copy_calapplication(result.pool[0], spwmap=spwmap)
                result.pool[0] = modified_calapp
                result.final[0] = modified_calapp

            # Register the new phase caltable in the local context, to ensure it
            # is pre-applied in subsequent gaincal calls.
            result.accept(inputs.context)
        return result

    # Compute a standard bandpass
    def _do_bandpass(self) -> BandpassResults:
        bandpass_task = bandpassmode.BandpassMode(self.inputs)
        return self._executor.execute(bandpass_task)

    # Compute the smoothed bandpass
    def _do_smoothed_bandpass(self) -> BandpassResults | None:
        inputs = self.inputs

        # Store original values of some parameters.
        orig_spw = inputs.spw
        orig_solint = inputs.solint
        orig_append = inputs.append

        try:
            # initialize the caltable and list of spws
            inputs.caltable = inputs.caltable
            spwlist = inputs.ms.get_spectral_windows(orig_spw)

            # will hold the CalAppOrigins that record how each CalApp was
            # generate. Ideally this would be a list on the CalApp itself,
            # but we don't have time to do that right now.
            calapp_origins = []

            # Loop through the spw appending the results of each spw
            # to the results of the previous one.
            for spw in spwlist:

                # TDM or FDM
                dd = inputs.ms.get_data_description(spw=spw)
                if dd is None:
                    LOG.debug('Missing data description for spw %s' % spw.id)
                    continue
                ncorr = len(dd.corr_axis)
                if ncorr not in [1, 2, 4]:
                    LOG.debug('Wrong number of correlations %s for spw %s' %
                              (ncorr, spw.id))
                    continue

                # Smooth if FDM and if it makes sense
                if ncorr * spw.num_channels > 256:
                    if (spw.num_channels // inputs.maxchannels) < 1:
                        LOG.info(f"{inputs.ms.basename}: Too few channels ({spw.num_channels}) in SpW {spw.id} to use"
                                 f" smoothing (maxchannels={inputs.maxchannels}), reverting to default bandpass solint"
                                 f" {orig_solint}.")
                        inputs.solint = orig_solint
                    else:
                        # PIPE-2036: work-around for potential issue caused by:
                        #   * PL defined solint as a frequency interval, and
                        #     this may correspond to an exact nr. of channels.
                        #   * the frequency interval is passed with limited
                        #     precision (typically in MHz with 6 decimals, i.e.
                        #     a precision of Hz)
                        #   * CASA's bandpass converts the frequency interval
                        #     back to nr. of channels and then take the floor
                        #
                        # This can result in e.g. a required nr. of channels of
                        # 5 corresponding to 4.8828125 MHz but getting passed as
                        # 4.882812 MHz, then converted back to 4.999999
                        # channels, and floored to 4.
                        #
                        # As a work-around, check whether the frequency interval
                        # would trigger this, and if so, then round *up* the
                        # frequency interval to nearest Hz.
                        bandwidth = spw.bandwidth.to_units(otherUnits=measures.FrequencyUnits.HERTZ)
                        newsolint = bandwidth / inputs.maxchannels
                        chanwidth = bandwidth / spw.num_channels
                        if round(newsolint) / chanwidth < math.floor(newsolint / chanwidth):
                            inputs.solint = f"{orig_solint},{round_up(newsolint) * 1.e-6:f}MHz"
                        else:
                            inputs.solint = f"{orig_solint},{float(newsolint) * 1.e-6:f}MHz"
                        LOG.info(f"{inputs.ms.basename}: using smoothed bandpass solint {inputs.solint} for SpW"
                                 f" {spw.id}.")
                else:
                    inputs.solint = orig_solint
                    LOG.warning(f"Reverting to default bandpass solint {inputs.solint} for spw {spw.id} in MS"
                                f" {inputs.ms.basename}")

                # PIPE-2116: if requested, set fillgaps to a quarter of the
                # number of channels of current SpW.
                if inputs.hm_auto_fillgaps:
                    inputs.fillgaps = int(spw.num_channels / 4)
                else:
                    inputs.fillgaps = 0

                # Compute and append bandpass solution
                inputs.spw = spw.id
                bandpass_task = bandpassmode.BandpassMode(inputs)
                result = self._executor.execute(bandpass_task)
                if os.path.exists(self.inputs.caltable):
                    self.inputs.append = True
                    self.inputs.caltable = result.final[-1].gaintable
                    calapp_origins.extend(result.final[-1].origin)

            # Reset the calto spw list
            result.pool[0].calto.spw = orig_spw
            if result.final:
                result.final[0].calto.spw = orig_spw
                result.final[0].origin = calapp_origins

            return result

        finally:
            inputs.spw = orig_spw
            inputs.solint = orig_solint
            inputs.append = orig_append

    # Compute the bandpass using SNR estimates
    def _do_snr_bandpass(self, snr_result) -> BandpassResults | None:
        inputs = self.inputs
        quanta = casa_tools.quanta

        # Store original values of some parameters.
        orig_spw = inputs.spw
        orig_solint = inputs.solint
        orig_append = inputs.append

        adjustments: list[SolintAdjustment] = []

        try:
            # initialize the caltable and list of spws
            inputs.caltable = inputs.caltable
            spwlist = inputs.ms.get_spectral_windows(orig_spw)

            # will hold the CalAppOrigins that record how each CalApp was
            # generate. Ideally this would be a list on the CalApp itself,
            # but we don't have time to do that right now.
            calapp_origins = []

            for spw in spwlist:

                # TDM or FDM
                dd = inputs.ms.get_data_description(spw=spw)
                if dd is None:
                    LOG.debug('Missing data description for spw %s' % spw.id)
                    continue
                ncorr = len(dd.corr_axis)
                if ncorr not in [1, 2, 4]:
                    LOG.debug('Wrong number of correlations %s for spw %s' %
                              (ncorr, spw.id))
                    continue

                # Find the best solint for that window
                try:
                    solindex = snr_result.spwids.index(spw.id)
                except:
                    solindex = -1

                # Use the optimal solution if it is good enough otherwise
                # revert to the default smoothing algorithm
                if solindex >= 0:

                    if snr_result.nbpsolutions[solindex] < inputs.bpnsols:
                        # Recompute the solution interval to force the minimum
                        # number of solution channels
                        factor = 1.0 / inputs.bpnsols
                        newsolint = quanta.tos(quanta.mul(snr_result.bandwidths[solindex], factor))
                        inputs.solint = orig_solint + ',' + newsolint

                        original = str(to_frequency(snr_result.bpsolints[solindex]))
                        adjusted = f'{orig_solint},{str(to_frequency(newsolint))}'

                        vis = os.path.basename(inputs.vis)
                        adjustments.append(
                            SolintAdjustment(
                                applies_to=TargetDataSelection(vis={vis}, spw={spw.id}),
                                original=original,
                                threshold=inputs.bpnsols,
                                adjusted=adjusted,
                                origin=LowSNRPhaseupSolintOrigin.TOO_FEW_CHANNELS.value,
                                reason=f'Too few channels: changing recommended bandpass solint from {original} to {adjusted} for spw {spw.id}'
                            )
                        )
                    else:
                        inputs.solint = orig_solint + ',' +  \
                            snr_result.bpsolints[solindex]
                    LOG.info('Setting bandpass solint to %s for spw %s' % (inputs.solint, spw.id))

                elif ncorr * spw.num_channels > 256:
                    LOG.warning(f"{inputs.ms.basename}: no SNR based bandpass solint was found for spw {spw.id},"
                                f" reverting to smoothing algorithm.")
                    if (spw.num_channels // inputs.maxchannels) < 1:
                        LOG.info(f"{inputs.ms.basename}: Too few channels ({spw.num_channels}) in SpW {spw.id} to use"
                                 f" smoothing (maxchannels={inputs.maxchannels}), reverting to default bandpass solint"
                                 f" {orig_solint}.")
                        inputs.solint = orig_solint
                    else:
                        # PIPE-2036: work-around for potential issue caused by:
                        #   * PL defined solint as a frequency interval, and
                        #     this may correspond to an exact nr. of channels.
                        #   * the frequency interval is passed with limited
                        #     precision (typically in MHz with 6 decimals, i.e.
                        #     a precision of Hz)
                        #   * CASA's bandpass converts the frequency interval
                        #     back to nr. of channels and then take the floor
                        #
                        # This can result in e.g. a required nr. of channels of
                        # 5 corresponding to 4.8828125 MHz but getting passed as
                        # 4.882812 MHz, then converted back to 4.999999
                        # channels, and floored to 4.
                        #
                        # As a work-around, check whether the frequency interval
                        # would trigger this, and if so, then round *up* the
                        # frequency interval to nearest Hz.
                        bandwidth = spw.bandwidth.to_units(otherUnits=measures.FrequencyUnits.HERTZ)
                        newsolint = bandwidth / inputs.maxchannels
                        chanwidth = bandwidth / spw.num_channels
                        if round(newsolint) / chanwidth < math.floor(newsolint / chanwidth):
                            inputs.solint = f"{orig_solint},{round_up(newsolint) * 1.e-6:f}MHz"
                        else:
                            inputs.solint = f"{orig_solint},{float(newsolint) * 1.e-6:f}MHz"
                        LOG.info(f"{inputs.ms.basename}: using smoothed bandpass solint {inputs.solint} for SpW"
                                 f" {spw.id}.")
                else:
                    inputs.solint = orig_solint
                    LOG.warning("Reverting to default bandpass solint %s for spw %s in MS %s" %
                                (inputs.solint, spw.id, inputs.ms.basename))

                # PIPE-2116: if requested, set fillgaps to a quarter of the
                # number of channels of current SpW.
                if inputs.hm_auto_fillgaps:
                    inputs.fillgaps = int(spw.num_channels / 4)
                else:
                    inputs.fillgaps = 0

                # Compute and append bandpass solution
                inputs.spw = spw.id
                bandpass_task = bandpassmode.BandpassMode(inputs)
                result = self._executor.execute(bandpass_task)
                if os.path.exists(self.inputs.caltable):
                    self.inputs.append = True
                    self.inputs.caltable = result.final[-1].gaintable
                    calapp_origins.extend(result.final[-1].origin)

            # Reset the calto spw list
            result.pool[0].calto.spw = orig_spw
            if result.final:
                result.final[0].calto.spw = orig_spw
                result.final[0].origin = calapp_origins

            result.solint_adjustments.extend(adjustments)

            return result

        finally:
            inputs.spw = orig_spw
            inputs.solint = orig_solint
            inputs.append = orig_append

    # Compute spws using bandwidth parameters
    def _get_phaseup_spw(self):
        """
                   ms -- measurement set object
               spwstr -- comma delimited list of spw ids
            bandwidth -- bandwidth in Hz of central channels used to
                         phaseup
        """
        inputs = self.inputs

        # Add the channel ranges in. Note that this currently assumes no prior
        # channel selection.
        if inputs.phaseupbw == '':
            return inputs.spw

        # Convert bandwidth input to CASA quantity and then on to pipeline
        # domain Frequency object
        quanta = casa_tools.quanta
        bw_quantity = quanta.convert(quanta.quantity(inputs.phaseupbw), 'Hz')
        bandwidth = measures.Frequency(quanta.getvalue(bw_quantity)[0],
                                       measures.FrequencyUnits.HERTZ)

        # Loop over the spws creating a new list with channel ranges
        outspw = []
        for spw in self.inputs.ms.get_spectral_windows(self.inputs.spw):
            cen_freq = spw.centre_frequency
            lo_freq = cen_freq - bandwidth / 2.0
            hi_freq = cen_freq + bandwidth / 2.0
            minchan, maxchan = spw.channel_range(lo_freq, hi_freq)
            cmd = '{0}:{1}~{2}'.format(spw.id, minchan, maxchan)
            outspw.append(cmd)

        return ','.join(outspw)


@task_registry.set_equivalent_casa_task('hifa_bandpass')
@task_registry.set_casa_commands_comment(
    'The spectral response of each antenna is calibrated. A short-solint phase gain is calculated to remove '
    'decorrelation of the bandpass calibrator before the bandpass is calculated.'
)
class ALMAPhcorBandpass(sessionutils.ParallelTemplate):
    Inputs = ALMAPhcorBandpassInputs
    Task = SerialALMAPhcorBandpass


class SessionALMAPhcorBandpassInputs(ALMAPhcorBandpassInputs):
    # We want to apply bandpass calibrations from BANDPASS scans, not
    # fall back to calibration against PHASE or AMPLITUDE scans
    intent = vdp.VisDependentProperty(default='BANDPASS')

    # use common implementation for parallel inputs argument
    parallel = sessionutils.parallel_inputs_impl()

    def __init__(self, context, mode=None, hm_phaseup=None, phaseupbw=None, phaseupsolint=None, phaseupsnr=None,
                 phaseupnsols=None, hm_bandpass=None, solint=None, maxchannels=None, evenbpints=None, bpsnr=None,
                 minbpsnr=None, bpnsols=None, parallel=None, **parameters):
        super().__init__(context, mode=mode, hm_phaseup=hm_phaseup,
                                                             phaseupbw=phaseupbw, phaseupsolint=phaseupsolint,
                                                             phaseupsnr=phaseupsnr, phaseupnsols=phaseupnsols,
                                                             hm_bandpass=hm_bandpass, solint=solint,
                                                             maxchannels=maxchannels, evenbpints=evenbpints,
                                                             bpsnr=bpsnr, minbpsnr=minbpsnr,
                                                             bpnsols=bpnsols, **parameters)
        self.parallel = parallel





BANDPASS_MISSING = '___BANDPASS_MISSING___'


@task_registry.set_equivalent_casa_task('session_bandpass')
class SessionALMAPhcorBandpass(basetask.StandardTaskTemplate):
    Inputs = SessionALMAPhcorBandpassInputs

    is_multi_vis_task = True

    def prepare(self):
        inputs = self.inputs

        vis_list = sessionutils.as_list(inputs.vis)

        assessed = []
        with sessionutils.VDPTaskFactory(inputs, self._executor, SerialALMAPhcorBandpass) as factory:
            task_queue = [(vis, factory.get_task(vis)) for vis in vis_list]

            for (vis, (task_args, task)) in task_queue:
                # only launch jobs for MSes with bandpass calibrators.
                # The analyse() method will subsequently adopt the
                # appropriate bandpass calibration table from one of
                # the completed jobs.
                ms = inputs.context.observing_run.get_ms(vis)
                if 'BANDPASS' not in ms.intents:
                    assessed.append(sessionutils.VisResultTuple(vis, task_args, BANDPASS_MISSING))
                    continue
                try:
                    worker_result = task.get_result()
                except exceptions.PipelineException as e:
                    assessed.append(sessionutils.VisResultTuple(vis, task_args, e))
                else:
                    assessed.append(sessionutils.VisResultTuple(vis, task_args, worker_result))

        return assessed

    def analyse(self, assessed):
        # all results will be added to this object
        final_result = basetask.ResultsList()

        context = self.inputs.context

        session_groups = sessionutils.group_into_sessions(context, assessed)
        for session_id, session_results in session_groups.items():
            # get a list of MeasurementSet domain objects for all MSes
            # in this session
            session_mses = [context.observing_run.get_ms(vis_result.vis) for vis_result in session_results]

            # get a list of all bandpass scans in this session,
            # flattening the list of lists to form a single list of
            # scan domain objects
            bandpass_scans = list(itertools.chain(*[ms.get_scans(scan_intent='BANDPASS') for ms in session_mses]))

            # create a dict of scan objects to name of the MS
            # containing that scan
            scans_to_vis = {scan: ms.name
                            for scan in bandpass_scans
                            for ms in session_mses
                            if scan in ms.scans}

            # create a dict of scan object to results object for the MS
            # containing that scan
            scan_to_result = {scan: result
                              for vis, _, result in session_results
                              for scan in bandpass_scans
                              if vis == scans_to_vis[scan]}

            for vis, task_args, vis_result in session_results:
                if vis_result == BANDPASS_MISSING:
                    # No bandpass calibrator for this MS, so adopt the
                    # nearest bandpass calibration in time

                    # get bandpass closest in time, identified from the
                    # centre of the bandpass scan to the centre of this
                    # observation
                    no_bandpass_ms = context.observing_run.get_ms(vis)
                    centre_time = centre_datetime_from_epochs(no_bandpass_ms.start_time, no_bandpass_ms.end_time)
                    closest_scan = min(bandpass_scans, key=lambda scan: get_time_delta_seconds(centre_time, scan))

                    # identify which result contains this closest scan
                    # and adopt its CalApplications
                    result_to_add = scan_to_result[closest_scan]
                    adopted_ms = context.observing_run.get_ms(result_to_add.inputs['vis'])

                    LOG.info('Adopting calibrations from {!s} for {!s}'
                             ''.format(adopted_ms.basename, no_bandpass_ms.basename))
                    fake_result = BandpassResults(applies_adopted=True)
                    fake_result.inputs = task_args
                    fake_result.stage_number = result_to_add.stage_number

                    for calapp in result_to_add.final:
                        session_calto = calapp.calto
                        session_calfrom = calapp.calfrom

                        # remap spectral windows to apply calibration
                        # to
                        my_spw = sessionutils.remap_spw_str(adopted_ms, no_bandpass_ms, session_calto.spw)
                        my_calto = callibrary.CalTo(vis=vis, field='', spw=my_spw, antenna='', intent='')

                        for cf in session_calfrom:
                            # remap spectral windows to take
                            # calibration from
                            my_spwmap = sessionutils.remap_spw_int(adopted_ms, no_bandpass_ms, cf.spwmap)

                            my_calfrom = callibrary.CalFrom(gaintable=cf.gaintable,
                                                            gainfield=cf.gainfield,
                                                            interp=cf.interp,
                                                            spwmap=my_spwmap,
                                                            caltype=cf.caltype,
                                                            calwt=cf.calwt)

                            remapped_calapp = callibrary.CalApplication(my_calto, my_calfrom, origin=calapp.origin)
                            fake_result.final.append(remapped_calapp)

                        final_result.append(fake_result)

                elif isinstance(vis_result, Exception):
                    LOG.error('No bandpass solution created for {!s}'.format(os.path.basename(vis)))

                    fake_result = BandpassResults()
                    fake_result.inputs = task_args

                    final_result.append(fake_result)

                else:
                    # the bandpass job for an individual MS is wrapped
                    # in a ResultsList, hence [0].
                    final_result.append(vis_result)

        return final_result


def centre_datetime_from_epochs(epoch1, epoch2):
    """
    Get the time midpoint between two epochs.

    :param epoch1: epoch 1
    :param epoch2: epoch 2
    :return: time between epoch1 and epoch2
    :rtype: datetime.datetime
    """
    time1 = utils.get_epoch_as_datetime(epoch1)
    time2 = utils.get_epoch_as_datetime(epoch2)
    # use min & max so it doesn't depend on correct time ordering of
    # arguments
    start = min([time1, time2])
    end = max([time1, time2])
    return start + (end - start) / 2


def get_time_delta_seconds(time, scan):
    """
    Get the absolute time difference between a time t and a scan's time
    of observation. The time difference is calculated as the difference
    between t and the midpoint of the scan.

    :param time: time point
    :type time: datetime.datetime
    :param scan: scan to measure time to
    :type scan: Scan domain object
    :return: time between time and scan midpoint
    :rtype: datetime.timedelta
    """
    scan_centre = centre_datetime_from_epochs(scan.start_time, scan.end_time)
    dt = time - scan_centre
    return abs(dt.total_seconds())


def to_frequency(val: str) -> measures.Frequency:
    """
    Converts a string representation of a frequency value to a Frequency object.

    :param val: The string representation of the frequency value (e.g., '100MHz', '1GHz').
    :return: A Frequency object representing the frequency value.
    """
    qa = casa_tools.quanta
    as_quantity = qa.quantity(val)
    hz_quantity = qa.convert(as_quantity, 'Hz')
    hz_val = hz_quantity['value']
    as_frequency = measures.Frequency(hz_val, units=measures.FrequencyUnits.HERTZ)
    return as_frequency
