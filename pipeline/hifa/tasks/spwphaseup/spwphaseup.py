import copy
import dataclasses
import os
import traceback
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import numpy

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.callibrary as callibrary
import pipeline.infrastructure.utils as utils
import pipeline.infrastructure.vdp as vdp
from pipeline.domain import SpectralWindow
from pipeline.domain.measurementset import MeasurementSet
from pipeline.h.tasks.common import commonhelpermethods
from pipeline.hif.tasks.gaincal import gtypegaincal
from pipeline.hif.tasks.gaincal.common import GaincalResults
from pipeline.hif.tasks.gaincal.gtypegaincal import GTypeGaincalInputs, GTypeGaincal
from pipeline.hifa.heuristics.phasemetrics import PhaseStabilityHeuristics
from pipeline.hifa.heuristics.phasespwmap import IntentField, SpwMapping
from pipeline.hifa.heuristics.phasespwmap import combine_spwmap
from pipeline.hifa.heuristics.phasespwmap import simple_n2wspwmap
from pipeline.hifa.heuristics.phasespwmap import snr_n2wspwmap
from pipeline.hifa.heuristics.phasespwmap import update_spwmap_for_band_to_band
from pipeline.hifa.tasks.fluxscale.qa import CaltableWrapperFactory
from pipeline.hifa.tasks.gaincalsnr import gaincalsnr
from pipeline.infrastructure import casa_tools
from pipeline.infrastructure import task_registry
from pipeline.infrastructure.utils.math import round_half_up

LOG = infrastructure.get_logger(__name__)

__all__ = [
    'SpwPhaseupInputs',
    'SpwPhaseup',
    'SpwPhaseupResults'
]

WEAK_CALIBRATOR_INTENTS = {'CHECK', 'PHASE'}

# Estimated SNR threshold for spw above which a gaintable will be generated. Equivalent
# to X in PIPE-2505 spec. Setting to -1 forces gaintable SNR estimation for all SPWs.
LOW_SNR_THRESHOLD = -1

# Multiplier applied to catalogue SNRs for their subsequent use in heuristics.
# Equivalent to Y in PIPE-2505 spec.
CATALOGUE_SNR_MULTIPLIER = 0.75

# Multiplier applied to gaintable SNRs for their subsequent use in heuristics.
# Equivalent to Z in PIPE-2505 spec.
GAINTABLE_SNR_MULTIPLIER = 1.0


@dataclass
class SNRTestResult:
    """
    Data structure to store the results of SNR tests.

    This class encapsulates the results of Signal-to-Noise Ratio (SNR) calculations for multiple
    spectral window (SpW) IDs. It tracks which SpWs have valid SNR results, the list of SNR values,
    and associated metadata such as reference and integration times.

    Attributes
    ----------
    spw_ids : list[int]
        List of spectral window (SpW) IDs for which SNR was derived.
    snr_values : list[float | None]
        List of derived SNR values, where None represents missing or undefined SNR.
    is_good_snr : list[bool | None]
        List of boolean values indicating whether the derived SNR is above a predefined threshold
        (considered good). None represents missing evaluation.
    reference_times : list[float | None]
        List specifying reference times in minutes, where None represents missing data.
    integration_times : list[float | None]
        List specifying integration times in minutes, where None represents missing data.
    """
    spw_ids: list[int] = dataclasses.field(default_factory=list)
    snr_values: list[float | None] = dataclasses.field(default_factory=list)
    is_good_snr: list[bool | None] = dataclasses.field(default_factory=list)
    reference_times: list[float | None] = dataclasses.field(default_factory=list)
    integration_times: list[float | None] = dataclasses.field(default_factory=list)

    @property
    def has_no_snrs(self) -> bool:
        """
        Indicates whether there are no SNRs available.

        This property checks the inverse state of another attribute to determine if no
        SNRs are present.

        Returns:
            bool: True if there are no SNRs, False otherwise.
        """
        return not self.has_snrs

    @property
    def has_snrs(self) -> bool:
        """
        Checks if the object has non-empty and non-None SNR (Signal-to-Noise Ratio)
        values.

        Returns
            bool: True if there are SNR values and at least one of them is not None,
                otherwise False.
        """
        return len(self.snr_values) > 0 and any(snr is not None for snr in self.snr_values)

    def has_all_snrs_greater_than(self, snr_limit: float) -> bool:
        """
        Determines if all SNR (Signal-to-Noise Ratio) values are greater than a specified limit.

        Returns a boolean indicating whether all defined SNR values in the list are greater
        than or equal to the provided limit. If the list of SNR values is empty, the method
        returns `False`.

        Args:
            snr_limit: A floating-point number representing the minimum threshold
                       for the SNR values.

        Returns:
            bool: True if all SNR values are greater than or equal to the limit,
                    False otherwise.
        """
        return self.has_snrs and all(snr >= snr_limit for snr in self.snr_values)


class SpwPhaseupInputs(gtypegaincal.GTypeGaincalInputs):
    # Spw mapping mode heuristics, options are:
    #  'auto': apply SNR-based heuristics to determine which type of spw
    #          mapping / combination is appropriate.
    #  'combine': force use of combined spw mapping
    #  'simple': force use of simple narrow-to-wide spw mapping.
    #  'default': use the standard mapping, mapping each spw to itself.
    hm_spwmapmode = vdp.VisDependentProperty(default='auto')

    @hm_spwmapmode.convert
    def hm_spwmapmode(self, value):
        allowed = ('auto', 'combine', 'simple', 'default')
        if value not in allowed:
            m = ', '.join(('{!r}'.format(i) for i in allowed))
            raise ValueError('Value not in allowed value set ({!s}): {!r}'.format(m, value))
        return value

    # Fraction of bandwidth to ignore on each edge of a spectral window
    # for SNR assessment.
    bwedgefrac = vdp.VisDependentProperty(default=0.03125)

    # Maximum fraction of data that can be flagged for an antenna before that
    # antenna is considered "flagged" and no longer considered in SNR
    # estimation.
    maxfracflagged = vdp.VisDependentProperty(default=0.90)

    # Maximum narrow bandwidth.
    maxnarrowbw = vdp.VisDependentProperty(default='300MHz')

    # Width of spw must be larger than minfracmaxbw * maximum bandwidth for
    # a spw to be a match.
    minfracmaxbw = vdp.VisDependentProperty(default=0.8)

    # Phase SNR threshold to use in spw mapping assessment to derive the optimal
    # solution interval (scan-time based).
    phasesnr = vdp.VisDependentProperty(default=32.0)

    # Phase SNR threshold to use in spw mapping assessment to derive the optimal
    # solution interval w.r.t. bright calibrators bandpass and differential
    # gain (integration-time based).
    intphasesnr = vdp.VisDependentProperty(default=5.0)

    # Phase SNR threshold to use in spw mapping assessment to derive the optimal
    # solution interval w.r.t. bright calibrator fields that cover the amplitude
    # calibrator intent.
    intphasesnrmin = vdp.VisDependentProperty(default=3.0)

    # Maximum phase-up solution interval.
    phaseupmaxsolint = vdp.VisDependentProperty(default=60.0)

    # Toggle to select whether to restrict spw matching to the same baseband.
    samebb = vdp.VisDependentProperty(default=True)

    # Antenna flagging heuristics parameter
    hm_nantennas = vdp.VisDependentProperty(default='all')

    @hm_nantennas.convert
    def hm_nantennas(self, value):
        allowed = ('all', 'unflagged')
        if value not in allowed:
            m = ', '.join(('{!r}'.format(i) for i in allowed))
            raise ValueError('Value not in allowed value set ({!s}): {!r}'.format(m, value))
        return value

    # Allow user to set custom filename for the phase offsets caltable.
    caltable = vdp.VisDependentProperty(default=None)

    # Intent to use in data selection for computing phase offsets caltable.
    intent = vdp.VisDependentProperty(default='BANDPASS')

    # PIPE-629: parameter to unregister existing phaseup tables before appending to callibrary
    unregister_existing = vdp.VisDependentProperty(default=False)

    # docstring and type hints: supplements hifa_spwphaseup
    def __init__(self, context, vis=None, output_dir=None, caltable=None, intent=None, hm_spwmapmode=None,
                 phasesnr=None, intphasesnr=None, intphasesnrmin=None, phaseupmaxsolint=None, bwedgefrac=None,
                 hm_nantennas=None, maxfracflagged=None, maxnarrowbw=None, minfracmaxbw=None, samebb=None,
                 unregister_existing=None, **parameters):
        """Initialize Inputs.

        Args:
            context: Pipeline context object containing state information.

            vis: The list of input MeasurementSets. Defaults to the list of
                MeasurementSets specified in the pipeline context.

                Example: ``vis=['M82A.ms', 'M82B.ms']``

            output_dir: Output directory.
                Defaults to None, which corresponds to the current working directory.

            caltable: The list of output calibration tables. Defaults to the standard
                pipeline naming convention.

                Example: ``caltable=['M82.gcal', 'M82B.gcal']``

            intent: A string containing a comma delimited list of intents against
                which the selected fields are matched. Defaults to the BANDPASS
                observations.

                Example: ``intent='PHASE'``

            hm_spwmapmode: The spectral window mapping mode. The options are: 'auto',
                'combine', 'simple', and 'default'. In 'auto' mode hifa_spwphaseup
                estimates the SNR of the phase calibrator observations and uses these
                estimates to choose between 'combine' mode (low SNR) and 'default' mode
                (high SNR). In combine mode all spectral windows are combined and mapped to
                one spectral window. In 'simple' mode narrow spectral windows are mapped to
                wider ones using an algorithm defined by 'maxnarrowbw', 'minfracmaxbw', and
                'samebb'. In 'default' mode the spectral window map defaults to the
                standard one to one mapping.

                Example:`` hm_spwmapmode='combine'``

            phasesnr: The required phase gaincal solution signal-to-noise.

                Example: ``phasesnr=20.0``

            intphasesnr: The required solint='int' phase gaincal solution signal-to-noise.

                Example: ``intphasesnr=4.0``

            intphasesnrmin: The required solint='int' phase gaincal solution
                signal-to-noise for fields that cover the AMPLITUDE calibrator
                intent.

                Example: ``intphasesnrmin=3.0``

            phaseupmaxsolint: Maximum phase correction solution interval (in
                seconds) allowed in very low-SNR cases. Used only when
                ``hm_spwmapmode`` = 'auto' or 'combine'.

                Example: ``phaseupmaxsolint=60.0``

            bwedgefrac: The fraction of the bandwidth edges that is flagged.

                Example: ``bwedgefrac=0.0``

            hm_nantennas: The heuristics for determines the number of antennas to use
                in the signal-to-noise estimate. The options are 'all' and 'unflagged'.
                The 'unflagged' options is not currently supported.

                Example: ``hm_nantennas='unflagged'``

            maxfracflagged: The maximum fraction of an antenna that can be flagged
                before it is excluded from the signal-to-noise estimate.

                Example: ``maxfracflagged=0.80``

            maxnarrowbw: The maximum bandwidth defining narrow spectral windows. Values
                must be in CASA compatible frequency units.

                Example: ``maxnarrowbw=''``

            minfracmaxbw: The minimum fraction of the maximum bandwidth in the set of
                spws to use for matching.

                Example: ``minfracmaxbw=0.75``

            samebb: Match within the same baseband if possible.

                Example: ``samebb=False``

            unregister_existing: Unregister previous spwphaseup calibrations from the pipeline context
                before registering the new calibrations from this task.

            field: The list of field names or field ids for which phase offset solutions
                are to be computed. Defaults to all fields with the default intent.

                Example: ``field='3C279'``, ``field='3C279, M82'``

            spw: The list of spectral windows and channels for which gain solutions are
                computed. Defaults to all the science spectral windows.

                Example: ``spw='13,15'``

            combine: Data axes to combine for solving. Options are ``''``, ``'scan'``, ``'spw'``,
                ``'field'`` or any comma-separated combination.

                Example: ``combine=''``

            refant: Reference antenna name(s) in priority order. Defaults to most recent
                values set in the pipeline context.  If no reference antenna is defined in
                the pipeline context the CASA defaults are used.

                Example: ``refant='DV01'``, ``refant='DV05,DV07'``

            minblperant: Minimum number of baselines required per antenna for each solve.
                Antennas with fewer baselines are excluded from solutions.

                Example: ``minblperant=2``

            minsnr: Solutions below this SNR are rejected.

        """
        super().__init__(context, vis=vis, output_dir=output_dir, **parameters)
        self.caltable = caltable
        self.intent = intent
        self.hm_spwmapmode = hm_spwmapmode
        self.phasesnr = phasesnr
        self.intphasesnr = intphasesnr
        self.intphasesnrmin = intphasesnrmin
        self.phaseupmaxsolint = phaseupmaxsolint
        self.bwedgefrac = bwedgefrac
        self.hm_nantennas = hm_nantennas
        self.maxfracflagged = maxfracflagged
        self.maxnarrowbw = maxnarrowbw
        self.minfracmaxbw = minfracmaxbw
        self.samebb = samebb
        self.unregister_existing = unregister_existing


@task_registry.set_equivalent_casa_task('hifa_spwphaseup')
class SpwPhaseup(gtypegaincal.GTypeGaincal):
    Inputs = SpwPhaseupInputs

    def prepare(self, **parameters):
        # Simplify the inputs
        inputs: SpwPhaseupInputs = self.inputs

        # Intents to derive separate SpW mappings for:
        spwmap_intents = 'AMPLITUDE,BANDPASS,CHECK,DIFFGAINREF,DIFFGAINSRC,PHASE'

        # Do not derive separate SpW mappings for fields that also cover any of
        # these calibrator intents:
        exclude_intents = 'POLARIZATION,POLANGLE,POLLEAKAGE'

        # PIPE-629: if requested, unregister old spwphaseup calibrations from
        # local copy of context, to stop these from being pre-applied during
        # this stage.
        if inputs.unregister_existing:
            self._unregister_spwphaseup()

        # Derive the mapping from phase fields to target/check fields.
        phasecal_mapping = self._derive_phase_to_target_check_mapping(inputs.ms)

        # Derive the optimal spectral window maps.
        spwmaps = self._derive_spwmaps(spwmap_intents, exclude_intents)

        # Compute the spw-to-spw phase offsets (historically misnamed as the
        # "phaseup") caltable and accept into local context.
        phaseupresult = self._do_phaseup()

        # Compute diagnostic phase caltables for all calibrator fields with SpW
        # mappings, with the spw-to-spw phase offset corrections included in
        # pre-apply.
        diag_phase_results = self._do_diagnostic_phasecal(spwmaps)

        # Compute what SNR is achieved for PHASE fields after the SpW phase-up
        # correction.
        snr_info = self._compute_median_snr(diag_phase_results)

        # Do the decoherence assessment
        phaserms_results, phaserms_cycletime, phaserms_totaltime, phaserms_antout \
            = self._do_decoherence_assessment()

        # Create the results object.
        result = SpwPhaseupResults(vis=inputs.vis, phasecal_mapping=phasecal_mapping, phaseup_result=phaseupresult,
                                   snr_info=snr_info, spwmaps=spwmaps, unregister_existing=inputs.unregister_existing,
                                   phaserms_totaltime=phaserms_totaltime, phaserms_cycletime=phaserms_cycletime,
                                   phaserms_results=phaserms_results, phaserms_antout=phaserms_antout)

        return result

    def analyse(self, result):
        # The caltable portion of the result is treated as if it were any other
        # calibration result. With no best caltable to find, our task is simply
        # to set the one caltable as the best result.

        # double-check that the caltable was actually generated
        on_disk = [ca for ca in result.phaseup_result.pool if ca.exists()]
        result.phaseup_result.final[:] = on_disk

        missing = [ca for ca in result.phaseup_result.pool if ca not in on_disk]
        result.phaseup_result.error.clear()
        result.phaseup_result.error.update(missing)

        return result

    @staticmethod
    def _derive_phase_to_target_check_mapping(ms: MeasurementSet) -> Dict[str, Set]:
        """
        Derive mapping between PHASE calibrator fields (by name) and
        corresponding fields (by name) with TARGET / CHECK intent that these
        PHASE calibrators should calibrate.

        PIPE-1154: This heuristic is intended for ALMA observing, and assumes
        that the first scan of a TARGET / CHECK field is always preceded by a
        scan of the corresponding PHASE calibrator. This method further assumes
        that scan IDs increase sequentially with observing time.

        Args:
            ms: MeasurementSet to derive mapping for.

        Returns:
            Dictionary of PHASE field names (key) and set of names of
            corresponding TARGET/CHECK fields (value).
        """
        # Get the PHASE field names.
        phase_fields = [f.name for f in ms.get_fields(intent='PHASE')]

        # Initialize the mapping for each PHASE calibrator field.
        mapping = {f: set() for f in phase_fields}

        # Get IDs of PHASE intent scans.
        phase_scan_ids = [s.id for s in ms.get_scans(scan_intent='PHASE')]

        for intent in ['CHECK', 'TARGET']:
            # Get field names for current intent.
            fields = [f.name for f in ms.get_fields(intent=intent)]

            for field in fields:
                # Get ID of first scan for current field with current intent.
                first_scan_id = ms.get_scans(field=field, scan_intent=intent)[0].id

                # PIPE-1154: in standard ALMA observing, each first scan of a
                # field with TARGET or CHECK intent should be preceded by a
                # scan of its corresponding PHASE calibrator.
                # Identify PHASE intent scans that preceded the first scan.
                preceding_phase_scan_ids = [i for i in phase_scan_ids if i < first_scan_id]
                if preceding_phase_scan_ids:
                    # Pick nearest in time PHASE intent scan as the match, and
                    # identify name of corresponding field.
                    matching_phase_scan_id = max(preceding_phase_scan_ids)
                else:
                    # Identify PHASE intent scans that followed the first scan.
                    following_phase_scan_ids = [i for i in phase_scan_ids if i > first_scan_id]
                    if following_phase_scan_ids:
                        # As a fall-back, pick nearest in time PHASE intent
                        # scan after first field scan, but raise warning.
                        matching_phase_scan_id = min(following_phase_scan_ids)
                        LOG.warning(f"{ms.basename}: no PHASE scans found prior to the first scan for field {field}"
                                    f" ({intent}), will match nearest PHASE scan that was taken after.")
                    else:
                        matching_phase_scan_id = None
                        LOG.warning(f"{ms.basename}: no PHASE scans found prior or after first scan for field {field}"
                                    f" ({intent}).")

                # If a matching PHASE scan was found, then update mapping to
                # link the corresponding PHASE field to current field.
                if matching_phase_scan_id:
                    matching_phase_field = [f.name for f in ms.get_scans(scan_id=matching_phase_scan_id)[0].fields][0]
                    mapping[matching_phase_field].add(field)

        return mapping

    def _derive_spwmaps(self, spwmap_intents: str, exclude_intents: str) -> Dict[IntentField, SpwMapping]:
        """
        Compute separate optimal spectral window mapping for each field
        covering one of the intents specified by "spwmap_intents", unless the
        field is already covered by a calibrator intent specified in
        "exclude_intents".

        Args:
            spwmap_intents: intents to derive separate SpW mappings for.
            exclude_intents: do not derive separate SpW mappings for fields
                that also cover any of these calibrator intents.

        Returns:
            Dictionary with (Intent, Field) combinations as keys and
            corresponding spectral window mapping as values.
        """
        # Simplify the inputs
        inputs: SpwPhaseupInputs = self.inputs

        # Report which spw mapping heuristics mode is being used.
        LOG.info(f"The spw mapping mode for {inputs.ms.basename} is \"{inputs.hm_spwmapmode}\"")

        # Initialize collection of spectral window maps and corresponding
        # SNR info.
        spwmaps = {}

        # Identify the combinations of intent and fields for which to derive a
        # separate spwmap.
        intent_field_to_assess = self._get_intent_field(inputs.ms, intents=spwmap_intents,
                                                        exclude_intents=exclude_intents)

        # Run derivation of spwmap for each intent, field combination.
        for intent, field in intent_field_to_assess:
            LOG.info(f'Deriving optimal spw mapping for {inputs.ms.basename}, intent={intent}, field={field}')
            spwmaps[IntentField(intent, field)] = self._derive_spwmap_for_intent_field(intent, field)

        return spwmaps

    def _derive_spwmap_for_intent_field(self, intent: str, field: str) -> SpwMapping:
        """
        Derive optimal spectral window mapping for specified intent and field.

        Args:
            intent: intent for which to derive SpW mapping.
            field: field for which to derive SpW mapping.

        Returns:
            SpwMapping object, representing the spectral window mapping.
        """
        # Simplify the inputs
        inputs: SpwPhaseupInputs = self.inputs
        quanta = casa_tools.quanta

        # PIPE-2499: restrict analysis to the science SpWs for current intent.
        spws = inputs.ms.get_spectral_windows(task_arg=inputs.spw, intent=intent)

        # Initialize default values for some of the task outputs, that may not
        # get updated further down depending on path through heuristics.
        solint = 'int'
        gaintype = 'G'
        combine = False
        spwmap = []  # i.e. each SpW is mapped to itself.
        # SNR tests are omitted for 'simple' or 'default' mapping, so populate a
        # default SNRTestResult instance to provide a common interface for methods calls
        # that operate on instances and instance properties
        snr_test_result = SNRTestResult()
        # snr_test_result will be modified in place, so create another instance to hold
        # catalogue SNRs
        calc_snr_result = SNRTestResult()
        # The list of combined SpW SNRs is empty; only updated if SpW
        # combination is necessary; needed for SNR info shown in task weblog.
        combined_snrs = []
        calc_combined_snrs = []
        # By default, set the SNR-threshold-used based on intent. Within this
        # task, this threshold is only used (and can be further tweaked) if an
        # SNR-based optimal solint gets computed. But even if the latter does
        # not happen (for example because the SNR test returns no results, so no
        # SNR-based solint can be computed), this default threshold is still
        # used in QA scoring and reported in the task weblog.
        snr_thr_used = self._snr_limit_for_intent(intent)

        # PIPE-1436: if there is only one SpW, then no SpW re-mapping can be
        # done. In this case, just run the SNR test, and compute an optimal
        # solint and gaintype if SNRs are available (PIPE-2499).
        if len(spws) == 1:
            LOG.info(f"{inputs.ms.basename}, intent={intent}, field={field}: only 1 science SpW found, so using"
                     f" standard SpW map for this data selection.")

            # Run a task to estimate the gaincal SNR for given intent, field,
            # and spectral windows.
            snr_test_result = self._do_snrtest(intent, field, spws)
            calc_snr_result = copy.deepcopy(snr_test_result)

            # Additionally, compute the SNRs empirically using a gain caltable
            self._compute_snr_from_gaincal(snr_test_result, field, intent)

            # No SNR estimates available, so stick with default values.
            if snr_test_result.has_no_snrs:
                LOG.warning(f"{inputs.ms.basename}, intent={intent}, field={field}: no SNR estimates for any SpWs,"
                            f" setting gaincal solint to {solint} and gaintype to {gaintype}.")
            else:
                # Compute the optimal solint and gaintype based on estimated SNR.
                solint, gaintype, snr_thr_used = self._compute_solint(
                    spwids=snr_test_result.spw_ids,
                    snrs=snr_test_result.snr_values,
                    ref_times=snr_test_result.reference_times,
                    int_times=snr_test_result.integration_times,
                    intent=intent,
                    mappingmode='single'
                )

        # If there are multiple SpWs, then continue with computing the SpW
        # optimal map according to the rules defined by each mapping mode.
        #
        # PIPE-2499: for the "hm_spwmapmode=auto" spw mapping mode (default),
        # run the SNR test and use the outcome to decide on optimal values for
        # spw mapping, solint, gaintype, and combine.
        elif inputs.hm_spwmapmode == 'auto':
            # Run a task to estimate the gaincal SNR for given intent, field,
            # and spectral windows.
            snr_test_result = self._do_snrtest(intent, field, spws)
            calc_snr_result = copy.deepcopy(snr_test_result)

            # Additionally, compute the SNRs empirically using a gain caltable
            self._compute_snr_from_gaincal(snr_test_result, field, intent)

            # PIPE-2499: set SNR limit to use in the derivation of any
            # subsequent SNR-based narrow-to-wide SpW mapping.
            snrlimit = self._snr_limit_for_intent(intent)

            # No SNR estimates available, default to simple narrow-to-wide SpW
            # mapping and stick to default values.
            if snr_test_result.has_no_snrs:
                spwmap = simple_n2wspwmap(spws, inputs.maxnarrowbw, inputs.minfracmaxbw, inputs.samebb)
                LOG.warning(f"{inputs.ms.basename}, intent={intent}, field={field}: no SNR estimates available for"
                            f" any SpWs, will force simple narrow-to-wide spw mapping {spwmap}, with solint={solint}"
                            f" and gaintype={gaintype}.")

            # PIPE-2499: all SpWs have good SNR estimates: in this case, check
            # whether the optimal solint is 'int' and if so use that + the
            # standard (empty) SpW mapping (i.e. each SpW mapped to itself).
            elif snr_test_result.has_all_snrs_greater_than(snrlimit):
                # Compute the optimal solint and gaintype based on estimated
                # SNR, while assuming no SpW-remapping mode.
                solint, gaintype, snr_thr_used = self._compute_solint(
                    spwids=snr_test_result.spw_ids,
                    snrs=snr_test_result.snr_values,
                    ref_times=snr_test_result.reference_times,
                    int_times=snr_test_result.integration_times,
                    intent=intent,
                    mappingmode='single'
                )

                # If the optimal solint is 'int', then proceed with this, and
                # the default of no SpW mapping.
                if solint == 'int':
                    LOG.info(f"{inputs.ms.basename}, intent={intent}, field={field}: high SNR estimates found for all"
                             f" spws and optimal solint='int', so will use default spw mapping {spwmap}.")
                # If the optimal solint is higher than 'int', then first
                # consider using SpW re-mapping after all, as SpW mapping is
                # preferable over time averaging. First check whether a simple
                # narrow-to-side SpW mapping with a customized SNR limit (based
                # on optimal solint) would result in a good mapping; if so, use
                # that, otherwise use SpW combination (and re-compute the
                # optimal solint in both outcomes).
                else:
                    LOG.info(f"{inputs.ms.basename}, intent={intent}, field={field}: high SNR estimates found for all"
                             f" spws, but optimal solint is larger than 'int', so will consider spw mapping or"
                             f" combination.")

                    # Scale the SNR limit based on the optimal solint and the
                    # integration time (converted to seconds).
                    integration_time_in_secs = snr_test_result.integration_times[0] * 60.0
                    snrlimit_scaled = snrlimit * numpy.sqrt(quanta.quantity(solint)['value'] / integration_time_in_secs)

                    # Compute an SNR-based narrow-to-wide SpW mapping with the
                    # scaled SNR limit.
                    goodmap, spwmap = snr_n2wspwmap(spws, snr_test_result.snr_values, snrlimit_scaled)

                    # If the SNR-based mapping with the new SNR limit gave a
                    # good match for all spws, then proceed to use this, and
                    # re-compute the optimal solint and gaintype assuming the
                    # "mapping" mode.
                    if goodmap:
                        LOG.info(f"{inputs.ms.basename}, intent={intent}, field={field}: found good match for all spws"
                                 f" using spw map {spwmap}.")
                        solint, gaintype, snr_thr_used = self._compute_solint(
                            spwids=snr_test_result.spw_ids,
                            snrs=snr_test_result.snr_values,
                            ref_times=snr_test_result.reference_times,
                            int_times=snr_test_result.integration_times,
                            intent=intent,
                            mappingmode='mapping'
                        )

                    # Otherwise, proceed with SpW combination instead of SpW
                    # mapping, and re-compute the optimal solint and gaintype
                    # assuming "combine" mode.
                    else:
                        LOG.warning(f"{inputs.ms.basename}, intent={intent}, field={field}: unable to find good match"
                                    f" for all spws using spw mapping, so will force combined spw mapping.")

                        # Create a spw mapping for combining spws.
                        spwmap = combine_spwmap(spws)
                        combine = True

                        # Re-compute the optimal solint and gaintype based on
                        # estimated SNR, while assuming SpW combination mode,
                        # and compute the expected combined SpW SNRs.
                        solint, gaintype, snr_thr_used = self._compute_solint(
                            spwids=snr_test_result.spw_ids,
                            snrs=snr_test_result.snr_values,
                            ref_times=snr_test_result.reference_times,
                            int_times=snr_test_result.integration_times,
                            intent=intent,
                            mappingmode='combine'
                        )
                        combined_snrs, calc_combined_snrs = self._process_combined_snrs(
                            snr_test_result,
                            calc_snr_result,
                            spwmap
                        )

            # No spws have good SNR values, so force combined spw mapping.
            elif not any(snr_test_result.is_good_snr):
                LOG.info(f"{inputs.ms.basename}, intent={intent}, field={field}: no spws have good enough SNR, so will"
                         f" force combined spw mapping.")

                # Report spws for which no SNR estimate was available.
                if None in snr_test_result.is_good_snr:
                    LOG.warning(
                        f"{inputs.ms.basename}, intent={intent}, field={field}: spws without SNR measurements "
                        f"{[spwid for spwid, goodsnr in zip(snr_test_result.spw_ids, snr_test_result.is_good_snr) if goodsnr is None]}."
                    )

                # Create a spw mapping for combining spws.
                spwmap = combine_spwmap(spws)
                combine = True

                # Re-compute the optimal solint and gaintype based on estimated
                # SNR, while assuming SpW combination mode, and compute the
                # expected combined SpW SNRs.
                solint, gaintype, snr_thr_used = self._compute_solint(
                    spwids=snr_test_result.spw_ids,
                    snrs=snr_test_result.snr_values,
                    ref_times=snr_test_result.reference_times,
                    int_times=snr_test_result.integration_times,
                    intent=intent,
                    mappingmode='combine'
                )
                combined_snrs, calc_combined_snrs = self._process_combined_snrs(
                    snr_test_result,
                    calc_snr_result,
                    spwmap
                )

            # If some, but not all, spws have good SNR values, then try to use
            # an SNR-based approach first, but fall back to combined spw mapping
            # if necessary.
            else:
                LOG.info(f"{inputs.ms.basename}, intent={intent}, field={field}: some spws have low SNR, so will"
                         f" consider spw mapping or combination.")

                # Report spws for which no SNR estimate was available.
                if None in snr_test_result.is_good_snr:
                    LOG.warning(
                        f"{inputs.ms.basename}, intent={intent}, field={field}: spws without SNR measurements "
                        f"{[spwid for spwid, goodsnr in zip(snr_test_result.spw_ids, snr_test_result.is_good_snr) if goodsnr is None]}."
                    )

                # Compute the SNR-based narrow-to-wide (low-SNR to high-SNR) SpW
                # mapping.
                goodmap, spwmap = snr_n2wspwmap(spws, snr_test_result.snr_values, snrlimit)

                # If the SNR-based mapping gave a good match for all spws, then
                # proceed to use this, and re-compute the optimal solint and
                # gaintype assuming the "mapping" mode.
                if goodmap:
                    LOG.info(f'Using spw map {spwmap} for {inputs.ms.basename}, intent={intent}, field={field}')
                    solint, gaintype, snr_thr_used = self._compute_solint(
                        spwids=snr_test_result.spw_ids,
                        snrs=snr_test_result.snr_values,
                        ref_times=snr_test_result.reference_times,
                        int_times=snr_test_result.integration_times,
                        intent=intent,
                        mappingmode='mapping'
                    )

                # Otherwise, proceed with SpW combination instead of SpW
                # mapping, and re-compute the optimal solint and gaintype
                # assuming "combine" mode.
                else:
                    LOG.warning(f"{inputs.ms.basename}, intent={intent}, field={field}: unable to find good match"
                                f" for all spws using spw mapping, so will force combined spw mapping.")

                    # Create a spw mapping for combining spws.
                    spwmap = combine_spwmap(spws)
                    combine = True

                    # Re-compute the optimal solint and gaintype based on
                    # estimated SNR, while assuming SpW combination mode,
                    # and compute the expected combined SpW SNRs.
                    solint, gaintype, snr_thr_used = self._compute_solint(
                        spwids=snr_test_result.spw_ids,
                        snrs=snr_test_result.snr_values,
                        ref_times=snr_test_result.reference_times,
                        int_times=snr_test_result.integration_times,
                        intent=intent,
                        mappingmode='combine'
                    )
                    combined_snrs, calc_combined_snrs = self._process_combined_snrs(
                        snr_test_result,
                        calc_snr_result,
                        spwmap
                    )

        # For the "hm_spwmapmode=combine" spw mapping mode, force the use of
        # SpW combination. PIPE-2499: still attempt to find optimal values for
        # solint and gaintype.
        elif inputs.hm_spwmapmode == 'combine':
            # Create a spw mapping for combining spws.
            spwmap = combine_spwmap(spws)
            combine = True
            LOG.info(f"{inputs.ms.basename}, intent={intent}, field={field}: using combined spw mapping {spwmap}.")

            # Run a task to estimate the gaincal SNR for given intent, field,
            # and spectral windows.
            snr_test_result = self._do_snrtest(intent, field, spws)
            calc_snr_result = copy.deepcopy(snr_test_result)

            # Additionally, compute the SNRs empirically using a gain caltable
            self._compute_snr_from_gaincal(snr_test_result, field, intent)

            # If no SNR estimates are available then set solint based on intent.
            if snr_test_result.has_no_snrs:
                # For CHECK and PHASE intent, override the solint to a quarter
                # of the scan (exposure) time, and set gaintype to T.
                if intent in WEAK_CALIBRATOR_INTENTS:
                    integration_time_in_secs = snr_test_result.integration_times[0] * 60.0
                    solint = quanta.tos(quanta.quantity(integration_time_in_secs / 4., 's'), 3)
                    gaintype = "T"
                    LOG.warning(f"{inputs.ms.basename}, intent={intent}, field={field}: no SNR estimates available for"
                                f" any SpWs, setting solint to 1/4 scan time and gaintype={gaintype}.")
                # For all other intents, stick to the default values for solint
                # and gaintype.
                else:
                    LOG.warning(f"{inputs.ms.basename}, intent={intent}, field={field}: no SNR estimates available for"
                                f" any SpWs, setting solint={solint}.")
            # Otherwise, compute the optimal solint and gaintype based on
            # estimated SNR assuming SpW combination mode, and compute expected
            # combined SpW SNRs.
            else:
                solint, gaintype, snr_thr_used = self._compute_solint(
                    spwids=snr_test_result.spw_ids,
                    snrs=snr_test_result.snr_values,
                    ref_times=snr_test_result.reference_times,
                    int_times=snr_test_result.integration_times,
                    intent=intent,
                    mappingmode='combine'
                )
                combined_snrs, calc_combined_snrs = self._process_combined_snrs(
                    snr_test_result,
                    calc_snr_result,
                    spwmap
                )

        # For the "hm_spwmapmode=simple" spw mapping mode, force the use of a
        # simple narrow-to-wide spw map.
        elif inputs.hm_spwmapmode == 'simple':
            spwmap = simple_n2wspwmap(spws, inputs.maxnarrowbw, inputs.minfracmaxbw, inputs.samebb)
            LOG.info(f"{inputs.ms.basename}, intent={intent}, field={field}: using simple narrow-to-wide spw mapping"
                     f" {spwmap}.")

        # Otherwise, for the remaining case of the hm_spwmapmode='default'
        # mapping mode, force the use of a standard (no) empty spw map (i.e.
        # map each SpW to itself).
        else:
            LOG.info(f"{inputs.ms.basename}, intent={intent}, field={field}: using standard SpW map {spwmap}.")

        # Report final choice of solint, gaintype, combine, and spwmap.
        LOG.info(f"{inputs.ms.basename}, intent {intent}, field {field}: the phase-up steps in subsequent"
                 f" Pipeline stages will use solint={solint}, gaintype={gaintype}, combine={combine}, and"
                 f" spwmap={spwmap}.")

        # PIPE-2059: for the PHASE calibrator in a BandToBand MS, adjust the
        # newly derived optimal SpW mapping to ensure that diffgain on-source
        # SpWs are remapped to an associated diffgain reference SpW.
        if self.inputs.ms.is_band_to_band and intent == 'PHASE':
            dg_refspws = inputs.ms.get_spectral_windows(task_arg=inputs.spw, intent='DIFFGAINREF')
            dg_srcspws = inputs.ms.get_spectral_windows(task_arg=inputs.spw, intent='DIFFGAINSRC')
            spwmap = update_spwmap_for_band_to_band(spwmap, dg_refspws, dg_srcspws)
            LOG.info(f"{inputs.ms.basename}, intent {intent}, field {field}: this is the phase calibrator for a"
                     f" band-to-band dataset, updated spw map to {spwmap}.")

        # Collect SNR info.
        snr_info = self._get_snr_info(snr_test_result, combined_snrs)

        # transform estimated SNRs into same structure for easier handling in renderer
        calc_snr_info = self._get_snr_info(calc_snr_result, calc_combined_snrs)

        return SpwMapping(combine, spwmap, snr_info, snr_thr_used, solint, gaintype, calc_snr_info)

    def _do_snrtest(self, intent: str, field: str, spws: list[SpectralWindow]) -> SNRTestResult:
        """
        Run gaincal SNR task to perform SNR test for specified intent and
        field.

        Args:
            intent: intent for which to perform SNR test.
            field: field for which to perform SNR test.
            spws: list of spectral window objects for which to perform SNR test.

        Returns:
            SnrTestResult that characterises the results of the gaincal SNR test
        """
        # Simplify inputs.
        inputs = self.inputs

        task_args = {
            'output_dir': inputs.output_dir,
            'vis': inputs.vis,
            'field': field,
            'intent': intent,
            'spw': ','.join(str(spw.id) for spw in spws),
            'bwedgefrac': inputs.bwedgefrac,
            'hm_nantennas': inputs.hm_nantennas,
            'maxfracflagged': inputs.maxfracflagged,
        }
        task_inputs = gaincalsnr.GaincalSnrInputs(inputs.context, **task_args)
        gaincalsnr_task = gaincalsnr.GaincalSnr(task_inputs)
        result = self._executor.execute(gaincalsnr_task)

        # PIPE-2499: based on the intent being analysed, set whether to use
        # "scan time" or "integration time" as the reference time, and select
        # corresponding values for SNRs and the SNR limit.
        # The weaker calibrators CHECK and PHASE will use an SNR limit of 32
        # (phasesnr) and scan-based values. The other, brighter, calibrators
        # typically use an SNR limit of 10 (intphasesnr).
        if intent in WEAK_CALIBRATOR_INTENTS:
            snrs = result.snrs
            snrlimit = inputs.phasesnr
            ref_times_to_use = result.scantimes
        else:
            snrs = result.snrsint
            snrlimit = inputs.intphasesnr
            ref_times_to_use = result.inttimes

        # Initialize and populate outputs.
        goodsnrs, ref_times, int_times = [], [], []
        for i, snr in enumerate(snrs):
            if snr is None:
                goodsnrs.append(None)
                ref_times.append(None)
                int_times.append(None)
            else:
                goodsnrs.append(snr >= snrlimit)
                ref_times.append(ref_times_to_use[i])
                int_times.append(result.inttimes[i])

        return SNRTestResult(
            spw_ids=result.spwids,
            snr_values=snrs,
            is_good_snr=goodsnrs,
            reference_times=ref_times,
            integration_times=int_times
        )

    def _do_combined_snr_test(self, spwlist: list, perspwsnr: list, spwmap: list) -> dict:
        """
        Compute combined SNRs from the "per-SpW SNR". Grouping of SpWs is
        specified by input parameter spwmap.

        For each grouped SpWs, combined SNR is calculated by:
            combined SNR = numpy.linalg.norm(list of per SpW SNR in a group)

        Args:
            spwlist: List of spw IDs to calculate combined SNR
            perspwsnr: List of SNRs of each SpW
            spwmap: List representing a spectral window map that specifies
                which SpW IDs should be combined.

        Returns:
            Dictionary containing for a given reference SpW the corresponding
            mapped SpWs and combined SNR.
        """
        LOG.info("Start combined SpW SNR test")
        LOG.debug('- spwlist to analyze: {}'.format(spwlist))
        LOG.debug('- per SpW SNR: {}'.format(perspwsnr))
        LOG.debug('- spwmap = {}'.format(spwmap))

        # Initialize return object.
        combined_snrs = {}

        # Filter reference SpW IDs of each group.
        unique_mappedspw = {spwmap[spwid] for spwid in spwlist}
        for mappedspwid in unique_mappedspw:
            snrlist = []
            combined_idx = []

            # only consider SpW IDs in spwlist for combination
            for i in range(len(spwlist)):
                spwid = spwlist[i]
                if spwmap[spwid] == mappedspwid:
                    snr = perspwsnr[i]
                    if snr is None:
                        continue
                    snrlist.append(snr)
                    combined_idx.append(i)

            if not snrlist:
                LOG.error('No SpW with valid SNR values; cannot calculate the combined SNR')
                return {}

            # calculate combined SNR from per spw SNR
            combined_snr = numpy.linalg.norm(snrlist)
            combined_spws = [spwlist[j] for j in combined_idx]
            LOG.info('Reference SpW ID = {} (Combined SpWs = {}) : Combined SNR = {}'
                     ''.format(mappedspwid, str(combined_spws), combined_snr))
            # For current reference SpW, store list of combined SpWs and
            # the combined SNR.
            combined_snrs[str(mappedspwid)] = (combined_spws, combined_snr)

        return combined_snrs

    def _do_gaincal(self, caltable: str | None = None, field: str | None = None, intent: str | None = None,
                    gaintype: str | None = None, solint: str | None = None, combine: str | None = None,
                    minblperant: int | None = None, minsnr: int | None = None) -> GaincalResults:
        """
        Runs gaincal worker task separately for each SpectralSpec present
        among the requested SpWs, each appending to the same caltable.

        The CalApplications in the result are modified to set calwt to False.

        Args:
            caltable: name of output caltable
            field: field selection string
            intent: intent selection string
            gaintype: gain type to use
            solint: solution interval to use
            combine: selects whether to combine SpWs
            minblperant: minimum baselines per antenna
            minsnr: minimum SNR

        Returns:
            Results object from gaincal worker task.
        """
        inputs = self.inputs
        ms = inputs.ms

        # Identify which science spws were selected by inputs parameter.
        request_spws = ms.get_spectral_windows(task_arg=inputs.spw)

        # Identify which scans covered the requested intent, field, and any of
        # the requested spws.
        targeted_scans = ms.get_scans(scan_intent=intent, spw=inputs.spw, field=field)

        # Among the requested spws, identify which have a scan among the
        # targeted scans.
        scan_spws = {spw for scan in targeted_scans for spw in scan.spws if spw in request_spws}

        # Create a separate phase solution caltable for each SpectralSpec
        # grouping of SpWs and collect the corresponding CalApplications from
        # the task results. Each caltable should have a unique filename since
        # the filename includes the SpW selection.
        calapps_pool, calapps_final = [], []
        for spectral_spec, tuning_spw_ids in utils.get_spectralspec_to_spwid_map(scan_spws).items():
            tuning_spw_str = ','.join([str(i) for i in sorted(tuning_spw_ids)])
            LOG.info('Processing spectral spec {}, spws {}'.format(spectral_spec, tuning_spw_str))

            scans_with_data = ms.get_scans(spw=tuning_spw_str, scan_intent=inputs.intent)
            if not scans_with_data:
                LOG.info('No data to process for spectral spec {}. Continuing...'.format(spectral_spec))
                continue

            # added in case not passed - PL2024 was hardcoded
            if not solint:
                solint = 'inf'

            # Initialize gaincal inputs.
            task_args = {
                'output_dir': inputs.output_dir,
                'vis': inputs.vis,
                'caltable': caltable,
                'field': field,
                'intent': intent,
                'spw': tuning_spw_str,
                'solint': solint,
                'gaintype': gaintype,
                'calmode': 'p',
                'minsnr': minsnr,
                'combine': combine,
                'refant': inputs.refant,
                'minblperant': minblperant,
            }
            task_inputs = gtypegaincal.GTypeGaincalInputs(inputs.context, **task_args)

            # Initialize and execute gaincal task.
            phasecal_task = gtypegaincal.GTypeGaincal(task_inputs)
            phasecal_result = self._executor.execute(phasecal_task)

            # Collect CalApplications.
            # PIPE-2752: calapps_final execludes expected caltables that were not successfully created.
            calapps_pool.extend(phasecal_result.pool)
            calapps_final.extend(phasecal_result.final)

        # Phase solution caltables should always be registered to be applied
        # with calwt=False (PIPE-1154). Create an updated version of each
        # CalApplication with the override to set calwt to False. Replace any
        # existing CalApplications in latest tuning result with complete list
        # of all updated CalApplications, and return this as the final result.
        phasecal_result.pool = [callibrary.copy_calapplication(c, calwt=False) for c in calapps_pool]
        phasecal_result.final = [callibrary.copy_calapplication(c, calwt=False) for c in calapps_final]

        return phasecal_result

    def _do_phaseup(self) -> GaincalResults:
        """
        Creates the SpW-to-SpW phase-up caltable, and merges the resulting
        table into the local task context.

        Returns:
            Results object from gaincal worker task.
        """
        inputs = self.inputs

        # Create spw-to-spw phaseup caltable.
        LOG.info(f'Computing spw phase-up table for {inputs.ms.basename}')
        tuning_result = self._do_gaincal(caltable=inputs.caltable, field=inputs.field, intent=inputs.intent,
                                         gaintype='G', combine=inputs.combine, minsnr=inputs.minsnr,
                                         minblperant=inputs.minblperant)

        # Accept this spw-to-spw phase offsets result into the local context,
        # to ensure the caltable is included in pre-apply for subsequent steps
        # in this task.
        tuning_result.accept(inputs.context)

        return tuning_result

    def _do_diagnostic_phasecal(self, spwmaps: dict[IntentField, SpwMapping]) -> list[GaincalResults]:
        """
        Creates diagnostic phase caltables for each phase calibrator field and
        each check source field, where the SpW-to-SpW phase-up caltable should
        be included in pre-apply (since it was merged into local context).

        These tables are used later in this stage to assess the median SNR
        achieved for each phase calibrator / check source in each SpW after the
        SpW-to-SpW phase-up is applied (PIPE-665).

        Use phase gaincal parameters appropriate for the SpW mapping derived
        earlier for each phase calibrator / check source field. Similar to
        hifa_timegaincal, set minblperant to 4 and minsnr to 3.

        Args:
            spwmaps: dictionary with (Intent, Field) combinations as keys and
                corresponding spectral window mapping as values.

        Returns:
            List of result objects from gaincal worker task(s) that produced
            the diagnostic phase caltable(s).
        """
        inputs = self.inputs

        # Derive separate phase solutions for each PHASE and each CHECK field.
        gaincal_results = []
        for (intent, field), spwmapping in spwmaps.items():
            # PIPE-2499: for the CHECK and PHASE calibrators, force the use of
            # solint='inf' in the upcoming diagnostic phase solve.
            if intent in WEAK_CALIBRATOR_INTENTS:
                solint = 'inf'
            else:
                solint = spwmapping.solint

            # Retrieve combine parameter from SpW mapping.
            combine = 'spw' if spwmapping.combine else ''

            # Create diagnostic phase caltables.
            # PIPE-665: for the diagnostic phase caltables, always use
            # minsnr=3, minblperant=4.
            LOG.info(f'Computing diagnostic phase caltable for {inputs.ms.basename}, intent={intent},'
                     f' field={field}.')
            gaincal_results.append(self._do_gaincal(field=field, intent=intent, gaintype=spwmapping.gaintype,
                                                    solint=solint, combine=combine, minblperant=4, minsnr=3))

        return gaincal_results

    def _compute_median_snr(self, gaincal_results: list[GaincalResults]) -> dict[tuple[str, str, str], float]:
        """
        This method evaluates the diagnostic phase caltable(s) produced in an
        earlier step to compute the median achieved SNR for each intent/field
        and for each SpW.

        Args:
            gaincal_results: List of gaincal worker task results representing
                the diagnostic phase caltable(s).

        Returns:
            Dictionary with intent, field name, and SpW as keys, and
            corresponding median achieved SNR as values.
        """
        inputs = self.inputs

        LOG.info(f'Computing median achieved phase SNR information for {inputs.ms.basename}.')
        snr_info = {}
        for result in gaincal_results:
            field = result.inputs['field']
            intent = result.inputs['intent']
            # Evaluate each CalApp in the result: for a given intent, field,
            # there can be separate gaintable (one per spectralspec).
            for calapp in result.final:
                # Get SpWs and SNR info from caltable.
                if not os.path.exists(calapp.gaintable):
                    # PIPE-2752: log a warning and skip a calapp if its caltable
                    # was not successfully created; ideally this should not
                    # happen since we are using result.final here.
                    LOG.warning(
                        'No caltable found at %s, cannot compute median SNR info for field=%s, intent=%s.',
                        calapp.gaintable,
                        field,
                        intent,
                    )
                    continue
                with casa_tools.TableReader(calapp.gaintable) as table:
                    spws = table.getcol("SPECTRAL_WINDOW_ID")
                    snrs = table.getcol("SNR")

                # Evaluate each unique SpW separately.
                for spw in sorted(set(spws)):
                    # Get indices in caltable data corresponding to current SpW.
                    ind_spw = numpy.where(spws == spw)[0]

                    # Get number of correlations for this SpW.
                    corr_type = commonhelpermethods.get_corr_products(inputs.ms, spw)
                    ncorrs = len(corr_type)

                    # Compute median achieved SNR and store in snr_info. If this
                    # SpW covers a single polarisation, then compute the median SNR
                    # using only the one corresponding column in the caltable.
                    if ncorrs == 1:
                        # Identify which column in caltable to use for computing
                        # the median SNR.
                        ind_col = commonhelpermethods.get_pol_id(inputs.ms, spw, corr_type[0])
                        snr_info[(intent, field, spw)] = numpy.median(snrs[ind_col, 0, ind_spw])
                    # Otherwise, i.e. SpW is multi-pol, use all columns.
                    else:
                        snr_info[(intent, field, spw)] = numpy.median(snrs[:, 0, ind_spw])

        return snr_info

    def _do_decoherence_assessment(self) -> Tuple[Optional[Dict], Optional[str], Optional[str], List]:
        try:
            LOG.info("Starting phase RMS structure function decoherence assessment.")

            # Initialize the phase RMS structure function assessment
            inputs = copy.deepcopy(self.inputs)
            phase_rms = PhaseStabilityHeuristics(inputs, outlier_limit=180.0, flag_tolerance=0.3, max_poor_ant=11)

            # Do the analysis
            phaserms_results, phaserms_cycletime, phaserms_totaltime, phaserms_antout = phase_rms.analysis()

        except Exception:
            phaserms_results, phaserms_cycletime, phaserms_totaltime = None, None, None
            phaserms_antout = []
            LOG.error("For {}, phase RMS structure function analysis failed".format(self.inputs.ms.basename))
            LOG.error(traceback.format_exc())

        return phaserms_results, phaserms_cycletime, phaserms_totaltime, phaserms_antout

    @staticmethod
    def _get_intent_field(ms: MeasurementSet, intents: str, exclude_intents: str = None) -> list[tuple[str, str]]:
        # If provided, convert "intents to exclude" into set of strings.
        if exclude_intents is None:
            exclude_intents = set()
        else:
            exclude_intents = set(exclude_intents.split(','))

        intent_field = []
        for intent in intents.split(','):
            for field in ms.get_fields(intent=intent):
                # Check whether found field also covers any of the intents to
                # skip.
                excluded_intents_found = field.intents.intersection(exclude_intents)

                # PIPE-2499: skip an AMPLITUDE field if it has overlap the
                # BANDPASS calibrator.
                if intent == 'AMPLITUDE' and 'BANDPASS' in field.intents:
                    LOG.info(f'{ms.basename}: will not derive spwmap for field {field.name} (#{field.id}) and intent'
                             f' {intent} because this field also covers the BANDPASS calibrator intent.')
                    continue

                if not excluded_intents_found:
                    intent_field.append((intent, field.name))
                else:
                    # Log a message to explain why no spwmap will be derived
                    # for this particular combination of field and intent.
                    excluded_intents_str = ", ".join(sorted(excluded_intents_found))
                    LOG.info(f'{ms.basename}: will not derive spwmap for field {field.name} (#{field.id}) and intent'
                             f' {intent} because this field also covers calibrator intent(s) {excluded_intents_str}')

        return intent_field

    def _compute_solint(
            self, spwids: list, snrs: list, ref_times: list, int_times: list, intent: str, mappingmode: str
    ) -> tuple[str, str, float]:
        """
        Compute the optimal solution interval and gaintype.

        Computes the optimal values to use for solution interval and gaintype
        in phase-up gaincal solutions. The ideal solution interval is a single
        integration time interval (solint='int'), but this method uses the SNR
        estimates provided to ensure that sufficient SNR is achieved, or whether
        some amount of time averaging (i.e. solint > 'int') is necessary.

        spwids, snrs, ref_times, and int_times are all passed from the SNR test
        function, where SNRs are based on the reference time (ref_times), and
        int_times is provided as the integration time (for each SpW).

        The mappingmode indicates what type of spw mapping is used in the
        phase-up solve:

          * single: uses no mapping (each spw mapped to itself); in this case,
            the value of the lowest (worst) SNR will be used.
          * mapping: uses spw re-mapping; in this case, the highest SNR will be
            used, as low-SNR SpWs will be re-mapped to this highest SNR SpW.
          * combine: uses spw combination; in this case, linearalg is used to
            compute the combined SNR that is then used to govern the solint.

        Args:
            spwids: List of the spectral window IDs.
            snrs: List of the SNR per SpW, calculated for the reference time.
            ref_times: List of the reference time per SPW, in minutes.
            int_times: List of the integration time per SPW, in minutes.
            intent: Intent to compute solint for.
            mappingmode: Type of spw mapping to be used in phase solve, with
                options: 'single', 'mapping', 'combine'.

        Returns:
            3-tuple containing:
              * Solution interval to use, as string (e.g. "int", or "10.0s")
              * Gaintype to use ("G" or "T")
              * SNR threshold used
        """
        inputs = self.inputs
        quanta = casa_tools.quanta

        # Set default SNR limit based on intent. This may get overridden further
        # below, e.g. case of optimal solint for bright calibrators.
        snr_threshold_used = self._snr_limit_for_intent(intent)

        # Restrict the input SpWs, SNRs, and times to the SpWs-to-use.
        #
        # Bright AMPLITUDE or BANDPASS calibrators in Band-to-Band datasets will
        # have scans in both the (high-freq) diffgain source SpWs and the
        # (low-freq) diffgain reference SpWs, and subsequent phase solves for
        # these calibrators will be done in a single call for all those SpWs.
        # For these calibrators, use only the diffgain source SpWs, expected to
        # have low SNR, to compute the optimal solution interval.
        if inputs.ms.is_band_to_band and intent in {'AMPLITUDE', 'BANDPASS'}:
            dgsrc_spwids = [spw.id for spw in inputs.ms.get_spectral_windows(intent='DIFFGAINSRC')]
            to_keep = [idx for idx, spwid in enumerate(spwids) if spwid in dgsrc_spwids]
        # For all other data, loop over the spectral specs and identify the
        # SpectralSpec with the lowest-usable-SNR SpW in it; this SpectralSpec
        # and its SpWs (and corresponding SNR values) will be used in the
        # subsequent evaluation of best solint / gaintype.
        # Standard datasets will typically contain a single spectral spec, but
        # spectral scans or multi-tuning datasets will contain multiple spectral
        # specs.
        else:
            scispws = inputs.ms.get_spectral_windows()
            to_keep = []
            snr_min = float('inf')
            spectralspec_to_spw_ids = utils.get_spectralspec_to_spwid_map(scispws)

            # Identify the spws with the lowest SNR that's still usable. This runs two
            # passes through the data:
            #     first pass: only consider SNRs above the threshold
            #     second pass: consider all SNRs if nothing was found in the first pass
            for above_threshold in (True, False):
                for spwids_in_spec in spectralspec_to_spw_ids.values():
                    # Gets indices of SpWs that are in current spectral spec
                    spw_index = [i for i, spwid in enumerate(spwids) if spwid in spwids_in_spec]
                    # and their corresponding SNR values
                    spectralspec_snrs = [snrs[i] for i in spw_index]
                    # filter out SNRs below threshold for first pass
                    if above_threshold:
                        spectralspec_snrs = [s for s in spectralspec_snrs if s > snr_threshold_used]
                    # find the minimum and the corresponding spw to keep
                    if spectralspec_snrs:
                        min_snr = min(spectralspec_snrs)
                        if min_snr < snr_min:
                            to_keep, snr_min = spw_index, min_snr
                # if we found an SNR, we're done - otherwise, loop again with above_threshold=False
                if to_keep:
                    break

        # Filter SNRs and times for SpWs to keep.
        # PIPE-2499: for reference and integration time, it is assumed this is
        # the same across all SpWs, so pick the first element as representative,
        # and convert these times from minutes to seconds.
        snrs = [snrs[idx] for idx in to_keep]
        int_time = int_times[to_keep[0]] * 60.
        ref_time = ref_times[to_keep[0]] * 60.

        # Select what SNR (among SNRs for all considered SpWs) to let govern the
        # optimal solution interval based on what type of SpW mapping mode will
        # be used in subsequent phase-up solves.
        match mappingmode:
            case 'single':
                # If no mapping is used (each spw mapped to itself), then use the
                # lowest (worst) SNR to govern the optimal solint.
                snr_to_use = min(snrs)
            case 'mapping':
                # Use lowest SNR of all 'good' SNRs, i.e. those above snr_threshold_used.
                # As 'mapping' is only set when there is least one good SNR, we do not need
                # to provide a default or handle the ValueError that would be raised by taking
                # min() of an empty list
                snr_to_use = min([snr for snr in snrs if snr > snr_threshold_used])
            case 'combine':
                # If using SpW combination, then compute the Euclidean norm of the
                # SNR values to represent the combined SNR.
                snr_to_use = numpy.linalg.norm(snrs)
            case _:
                raise ValueError(f"Invalid mappingmode: {mappingmode}")

        # Set SNR for integration time and required SNR based on the intent.
        if intent in WEAK_CALIBRATOR_INTENTS:
            # For the potentially weaker calibrators, scale the SNR thresholds.
            int_snr = numpy.sqrt(int_time/ref_time) * snr_to_use
            req_snr = numpy.sqrt(int_time/ref_time) * inputs.phasesnr
        else:
            # No scaling for the other calibrators (BANDPASS, DIFFGAIN, ...).
            int_snr = snr_to_use
            req_snr = inputs.intphasesnr

        # Compute the required solint by scaling the integration time by the
        # ratio of required SNR over integration-time-based SNR.
        req_solint = int_time * (req_snr/int_snr)**2
        # By default, assume that the phase-up will use gaintype='G', i.e. solve
        # for the standard complex polarization-specific gain.
        gaintype = "G"

        # If the required solint after rounding would be at/below the
        # integration time (i.e. < 1.5 integration time), then 'int' is already
        # the optimal (lowest) solint to use, so return early with this (and 'G'
        # as the corresponding default gaintype).
        if req_solint < 1.5 * int_time:
            return 'int', gaintype, snr_threshold_used

        # If the required solint (with default gaintype) is above 'int', and the
        # phase-up will use SpW combination, then prefer to use gaintype "T",
        # i.e. solving across polarizations. Since this improves the SNR,
        # re-check whether with gaintype='T' the required solint would fall at
        # or below 'int'.
        if mappingmode == 'combine':
            gaintype = 'T'
            # Scale the integration-time based SNR threshold, assuming that with
            # gaintype='T' the signal is combined from at least 2 polarizations;
            # and re-compute the required solint with this scaled int-time SNR.
            int_snr = int_snr * numpy.sqrt(2)
            req_solint = int_time * (req_snr/int_snr)**2
            # If the required solint with gaintype='T' after rounding is
            # at/below the integration time, then return early with this as the
            # optimal solint.
            if req_solint < 1.5 * int_time:
                return 'int', gaintype, snr_threshold_used

        # If the required solint is definitely above the integration time, even
        # after considering the options of using SpW combination and
        # gaintype='T' then proceed to compute the optimal solint above 'int',
        # using different approaches for the weaker "CHECK" and "PHASE"
        # calibrators vs. all other (assumed bright) calibrators.
        if intent in WEAK_CALIBRATOR_INTENTS:
            # For CHECK and PHASE calibrators, the required SNR will have been
            # based on scan times (passed along as the reference time).
            scan_time = ref_time

            # If the required solint is more than half the scan time, then cap
            # the optimal solint to a maximum of half the scan time.
            if req_solint > scan_time / 2.:
                LOG.info(f"{inputs.ms.basename}, intent={intent}: setting the optimal gaincal solint to half the scan"
                         f" time.")
                solint = scan_time / 2.
            # Otherwise, the required solint is larger than the integration time
            # but less than half the scan time, so proceed to find the best
            else:
                # Compute how many integration times fit in the required solint
                # and in the scan time. The results should be >= 2, as the case
                # of 1 (after rounding) would have resulted in an early return
                # in a preceding step.
                req_solint_in_int = round_half_up(req_solint / int_time)
                max_solints_in_scan = round_half_up(scan_time / int_time)

                # Identify candidate solints as multiples of the integration
                # time, between 2x int and half of the scan time, that also work
                # as an exact division of the scan time, i.e. resulting in
                # exact equal solution intervals with no remainder.
                time_factors = [t for t in range(2, int(max_solints_in_scan / 2))
                                if max_solints_in_scan % t == 0]
                valid_factors = [t for t in time_factors if t >= req_solint_in_int]

                # If any valid integer multiple candidates were found, then use
                # the lowest factor to set the solution interval.
                if valid_factors:
                    solint = min(valid_factors) * int_time
                # Otherwise, revert to PL2024 heuristic and set solint to a
                # quarter of the scan time, without forcing to nearest integer
                # multiple of integration time.
                else:
                    LOG.info(f"{inputs.ms.basename}, intent={intent}: unable to find optimal number of integrations"
                             f" within a scan of the SNR requirement; setting the gaincal solint to 1/4 scan time.")
                    solint = scan_time / 4.

        # Optimal solint determination for all other (i.e. bright) calibrators.
        else:
            # Set solint to nearest integer multiple of the integration time.
            solint = round_half_up(req_solint / int_time) * int_time

            # If any of the fields for this bright calibrator are used as the
            # flux calibrator, then use the lowest allowed integration-time
            # based SNR limit instead, to minimize the solint and associated
            # decoherence error that would impact flux scaling (PIPE-2499).
            if any("AMPLITUDE" in f.intents for f in inputs.ms.get_fields(intent=intent)):
                LOG.info(f"{inputs.ms.basename}: the optimal solution interval found for intent {intent} is larger than"
                         f" 'int', but this intent is shared with the AMPLITUDE intent on at least one field, and the"
                         f" amplitude calibrator requires the shortest viable solint. Re-computing optimal solint based"
                         f" on reduced SNR limit of {inputs.intphasesnrmin} ('intphasesnrmin').")

                # Re-compute the required solint based on re-scaling from
                # normal integration-time based SNR threshold to the minimum
                # integration-time based SNR threshold. First, propagate the
                # SNR scaling from the working 'req_solint' (i.e. unrounded)
                req_solint = req_solint * (inputs.intphasesnrmin / inputs.intphasesnr) ** 2
                # now round it according to a unit of integration time
                solint = round_half_up(req_solint / int_time) * int_time
                snr_threshold_used  = inputs.intphasesnrmin

                # If this adjusted solint after rounding would be at/below the
                # integration time (i.e. < 1.5 integration time), then return
                # early with 'int' as the optimal solint.
                if solint < 1.5 * int_time:
                    return 'int', gaintype, snr_threshold_used

            # If the optimal solint exceeds the maximum solint threshold, then
            # set the final solint to this maximum threshold, rounded to nearest
            # integer multiple of the integration time.
            if solint >= inputs.phaseupmaxsolint:
                LOG.warning(f"{inputs.ms.basename}, intent={intent}: optimal solint {solint:.3f}s exceeds the maximum"
                            f" allowed limit of {inputs.phaseupmaxsolint}s, and will be capped to this limit (rounded"
                            f" to nearest integer multiple of integration time). Phase-up in subsequent Pipeline stages"
                            f" will have low solution SNR.")
                solint = round_half_up(inputs.phaseupmaxsolint / int_time) * int_time

        # Finally, convert the optimal solint to a string, and use "int" if
        # the optimal solint was below the integration time.
        if solint <= int_time:
            solint = 'int'
        else:
            solint = quanta.tos(quanta.quantity(solint, 's'), 3)

        return solint, gaintype, snr_threshold_used

    def _unregister_spwphaseup(self):
        inputs = self.inputs
        ms = inputs.ms

        # predicate function that triggers when the spwphaseup caltable is detected
        def spwphaseup_matcher(_: callibrary.CalToArgs, calfrom: callibrary.CalFrom) -> bool:
            return 'hifa_spwphaseup' in calfrom.gaintable

        LOG.info('Temporarily unregistering previous spwphaseup tables while task executes')
        inputs.context.callibrary.unregister_calibrations(spwphaseup_matcher)

        # Reset the spwmaps registered in the MS. This will be restored if the
        # result is not accepted.
        LOG.info('Temporarily resetting spwmaps for %s', ms.basename)
        ms.spwmaps = {}

    def _get_snr_info(self, snr_test_result: SNRTestResult, combined_snrs: dict) -> list[tuple[str, float]]:
        """
        Helper method that takes phase SNR info from the SNR test, and returns
        phase SNR info for all SpWs specified in inputs.spw.

        Parameters:
            snr_test_result: SnrTestResult
                SnrTestResult used as reference source for SNRs per spectral
                window
            combined_snrs: dict
                Dictionary of reference SpWs with list of corresponding
                combined SpW and combined phase SNR.

        Returns:
            List of tuples, specifying string representing SpW(s) and
            corresponding phase SNR.
        """
        spw_snr = {str(spw_id): snr
                   for spw_id, snr in zip(snr_test_result.spw_ids, snr_test_result.snr_values)}
        snr_info = []

        # Create entry for each SpW specified by inputs.
        for spwid in self.inputs.spw.split(','):
            # If this SpW is the reference SpW for a group of combined SpWs
            # then add an entry to list the combined SNR.
            if spwid in combined_snrs:
                combined_spws = ', '.join(str(s) for s in combined_snrs[spwid][0])
                combined_snr = combined_snrs[spwid][1]
                snr_info.append((f'Combined ({combined_spws})', combined_snr))

            # Retrieve SNR info for individual SpW if available.
            snr = spw_snr.get(spwid, None)
            snr_info.append((str(spwid), snr))

        return snr_info

    def _compute_snr_from_gaincal(
            self,
            snr_result: SNRTestResult,
            field: str,
            intent: str,
            low_snr_threshold: float = None,
            catalogue_snr_multiplier: float = None,
            gaintable_snr_multiplier: float = None
    ):
        """
        Estimates the Signal-to-Noise Ratio (SNR) by generating and analyzing a gaincal
        calibration table. Updates the SNR values in the provided SnrTestResult object
        based on the analysis results.

        This function implements the SNR estimation logic described in PIPE-2505:
        - For SPWs with SNR below threshold: applies a scaling factor (catalogue_snr_multiplier)
          to avoid calibration failures
        - For SPWs with SNR above threshold: computes new SNR estimates using gaincal analysis,
          applying a scaling factor to the measured values.

        Parameters:
            snr_result: SnrTestResult
                Object containing SNR test results, including spw_ids and snr_values that
                will be updated based on the analysis.
            field: str
                Field identifier to use for the gaincal calculation.
            intent: str
                Intent identifier to use for the gaincal calculation.
            low_snr_threshold: float, optional
                Threshold below which SPWs are considered low SNR and gaincal is not attempted.
                Default is -1 (corresponds to 'X' in PIPE-2505), forcing gaincal
                for all SPWs.
            catalogue_snr_multiplier: float, optional
                Scaling factor applied to SNR values derived from the flux catalogue.
                Default is 0.75 (corresponds to 'Y' in PIPE-2505).
            gaintable_snr_multiplier: float, optional
                Scaling factor applied to SNR values measured from the temporary gaintable.
                Default is 1.0 (corresponds to 'Z' in PIPE-2505).

        Returns:
            None
                The function updates the snr_result object in place.
        """
        if snr_result.has_no_snrs:
            return

        # these variables can't be arg defaults as it would make them impossible to change post-import
        if low_snr_threshold is None:
            low_snr_threshold = LOW_SNR_THRESHOLD
        if catalogue_snr_multiplier is None:
            catalogue_snr_multiplier = CATALOGUE_SNR_MULTIPLIER
        if gaintable_snr_multiplier is None:
            gaintable_snr_multiplier = GAINTABLE_SNR_MULTIPLIER

        # dict to map spw IDs to corrected SNR values
        snr_corrections = {spw_id: snr for spw_id, snr in zip(snr_result.spw_ids, snr_result.snr_values)
                           if snr is not None}

        # identify spws above/below the low-SNR threshold (='X' in PIPE-2505 spec)
        low_snr_spws, high_snr_spws = self._classify_spws_by_snr(snr_corrections, low_snr_threshold)

        # running gaincal minsnr=2 would result in failure for low-SNR spws. For these
        # low-SNR spws, set the estimated SNR to Y * SNR
        self._update_snr_for_low_snr_spws(snr_corrections, low_snr_spws, low_snr_threshold, catalogue_snr_multiplier)

        # For the remaining high SNR windows, generate a G caltable and set the
        # estimated SNR to Z * median SNR, as measured from the caltable
        if high_snr_spws:
            caltable_filename = self._generate_gain_caltable(field, intent, high_snr_spws)
            self._update_snr_for_high_snr_spws(snr_corrections, high_snr_spws, caltable_filename, gaintable_snr_multiplier)

        snr_limit = self._snr_limit_for_intent(intent)
        self._update_snr_result(snr_result, snr_corrections, snr_limit)

    def _snr_limit_for_intent(self, intent: str) -> float:
        """
        Determines the appropriate signal-to-noise ratio (SNR) limit based on the given intent.

        The method compares the provided intent with a predefined set of weak calibrator
        intents to decide which SNR limit should be applied.

        Parameters:
            intent (str): the intent to evaluate

        Returns:
            float: the applicable SNR limit based on the provided intent.
        """
        return self.inputs.phasesnr if intent in WEAK_CALIBRATOR_INTENTS else self.inputs.intphasesnr

    @staticmethod
    def _classify_spws_by_snr(snr_corrections: dict[int, float], threshold: float) -> tuple[set[int], set[int]]:
        """
        Classifies spectral windows (SPWs) into two sets based on their Signal-to-Noise
        Ratio (SNR) compared to a provided threshold. This method identifies and
        categorizes SPWs with low SNR and high SNR, returning them as two separate sets.

        Parameters:
            snr_corrections (dict[int, float]): A dictionary mapping SPW IDs to their
                corresponding SNR values.
            threshold (float): The SNR threshold for classification. SPWs with SNRs
                lower than this value are categorized as low SNR, while the rest are
                categorized as high SNR.

        Returns:
            tuple[set[int], set[int]]: A tuple containing two sets:
                - The first set contains the SPW IDs of SPWs with SNR lower than the
                  threshold (low SNR).
                - The second set contains the SPW IDs of SPWs with SNR equal to or
                  higher than the threshold (high SNR).
        """
        low_snr_spws = {spw_id for spw_id, snr in snr_corrections.items() if snr < threshold}
        high_snr_spws = set(snr_corrections.keys()) - low_snr_spws
        return low_snr_spws, high_snr_spws

    def _update_snr_for_low_snr_spws(
            self,
            snr_corrections: dict[int, float],
            low_snr_spws: set[int],
            threshold: float,
            multiplier: float
    ) -> None:
        """
        Handles low signal-to-noise ratio (SNR) spectral windows (spws) by applying a
        multiplier to their SNR values. This method modifies the provided
        `snr_corrections` dictionary in place.

        Parameters:
            snr_corrections (dict[int, float]): A dictionary mapping spw IDs to their
                SNR values. The SNR values are updated for spws that meet the low-SNR
                condition.
            low_snr_spws (set[int]): A set of spw IDs that are identified as having
                low SNR values (below the threshold).
            threshold (float): The SNR threshold used for identifying spws as low-SNR
                spws.
            multiplier (float): The multiplication factor applied to the SNR values of
                low-SNR spws.

        Returns:
            None
        """
        for spw_id in sorted(low_snr_spws):
            old_snr = snr_corrections[spw_id]
            snr_corrections[spw_id] *= multiplier
            LOG.info(f"Estimated SNR for {self.inputs.vis} spw {spw_id} is below threshold "
                     f"{threshold}. Skipping gaincal; setting SNR for combine heuristics to "
                     f"{snr_corrections[spw_id]:.3f} = {multiplier} * {old_snr:.3f}.")

    def _generate_gain_caltable(self, field: str, intent: str, high_snr_spws: set[int]) -> str:
        """
        Generates a gain caltable for high SNR spectral windows.

        Parameters:
            field (str): The field to calibrate.
            intent (str): The scan intent to process
            high_snr_spws (set[int]): A set of spectral window indices with high
                signal-to-noise ratios

        Returns:
            filename (str): The name of the generated gain caltable.
        """
        solint = 'inf' if intent in WEAK_CALIBRATOR_INTENTS else 'int'

        inputs = GTypeGaincalInputs(
            context=self.inputs.context,
            vis=self.inputs.vis,
            field=field,
            intent=intent,
            # note: we only select the high SNR spws here
            spw=','.join(map(str, sorted(high_snr_spws))),
            calmode='p',
            solint=solint,
            minsnr=2,
            append=False,
        )
        task = GTypeGaincal(inputs)
        _ = self._executor.execute(task)
        return inputs.caltable

    def _update_snr_for_high_snr_spws(
            self,
            snr_corrections: dict[int, float],
            high_snr_spws: set[int],
            caltable_filename: str,
            multiplier: float
    ) -> None:
        """
        Processes high Signal-to-Noise Ratio (SNR) spectral windows (spws) and updates
        the SNR corrections dictionary with computed or default values based on the
        filtered calibrated table data.

        Parameters:
            snr_corrections (dict[int, float]): A dictionary to store SNR corrections
                for each spectral window where the keys are the spectral window IDs,
                and the values are the corresponding corrections.
            high_snr_spws (set[int]): A set containing IDs of the spectral windows
                determined to have high SNR values.
            caltable_filename (str): filename of the caltable to analyse
            multiplier (float): A multiplier factor applied to the median SNR values
                for applying a scaling adjustment to the estimated SNR.

        Returns:
            None
                This function updates the snr_corrections dict in place.
        """
        try:
            caltable = CaltableWrapperFactory.from_caltable(caltable_filename)
        except OSError:
            LOG.info(f'Caltable for {self.inputs.vis} is missing, most likely due to zero'
                     f'solutions. Estimated SNR set to zero for all spws.')
            for spw_id in high_snr_spws:
                snr_corrections[spw_id] = 0
            return

        for spw in high_snr_spws:
            try:
                snr_data = caltable.filter(spw=spw).data['SNR']
            except KeyError:
                LOG.info(f'No SNR data present in temporary gain table for {self.inputs.vis} '
                         f'spw {spw}. Setting estimated SNR to zero.')
                snr_corrections[spw] = 0
                continue

            # Get number of correlations for this SpW.
            corr_type = commonhelpermethods.get_corr_products(self.inputs.ms, spw)
            ncorrs = len(corr_type)
            is_single_polarisation = ncorrs == 1

            if is_single_polarisation:
                # For single pol, one column will be populated with zeroes or nulls.
                # Identify which column holds data for the median SNR calculation
                idx_for_pol = commonhelpermethods.get_pol_id(self.inputs.ms, spw, corr_type[0])
                # note the use of numpy.median over numpy.ma.median: we WANT to include
                # the masked/flagged values in the median calculation. To avoid triggering
                # the UserWarning that results from operating on a masked array, we operate
                # on data
                # See https://open-jira.nrao.edu/browse/PIPE-2505?focusedId=237663&page=com.atlassian.jira.plugin.system.issuetabpanels:comment-tabpanel#comment-237663
                median_snr = numpy.median(snr_data.data[:, idx_for_pol])
            else:
                # otherwise, calculate the median over all pols. As obove, including masked values
                median_snr = numpy.median(snr_data.data)

            if median_snr in (numpy.inf, numpy.nan):
                LOG.info(f'No valid data in temporary gain table for {self.inputs.vis} '
                         f'spw {spw}. Setting estimated SNR to zero.')
                snr_corrections[spw] = 0
            else:
                snr_corrections[spw] = float(median_snr * multiplier)
                LOG.info(f'Based on a temporary gain table, calculated SNR for {self.inputs.vis} '
                         f'spw {spw} = {median_snr:.3f}. Setting SNR for combine heuristics to '
                         f'{snr_corrections[spw]:.3f} = {multiplier} * {median_snr:.3f}')

    def _update_snr_result(self, snr_result: SNRTestResult, snr_corrections: dict[int, float], snr_limit: float) -> None:
        """
        Updates the snr_result object with corrected SNR values based on the given
        snr_corrections. The function maps each spectral window's (SPW) ID from
        snr_result to a corrected SNR value using the snr_corrections dictionary. If
        no correction is found for a particular SPW ID, the original SNR value is
        retained.

        Parameters:
            snr_result (SNRTestResult): An object of type SnrTestResult. It contains
                the SPW IDs and their corresponding SNR values to be updated.
            snr_corrections (dict[int, float]): A dictionary mapping SPW IDs (int) to
                corrected SNR values (float).
            snr_limit (float): The SNR threshold used to identify spws with acceptable
                SNR.

        Returns:
            None
        """
        new_snrs = [snr_corrections.get(spw, snr)
                    for spw, snr in zip(snr_result.spw_ids, snr_result.snr_values)]

        # recompute good_snrs and has_no_snrs as they are used as triggers in the mapping process
        good_snrs = [snr >= snr_limit for snr in new_snrs]

        snr_result.snr_values = new_snrs
        snr_result.is_good_snr = good_snrs

    def _process_combined_snrs(
            self,
            snr_result: SNRTestResult,
            calc_snr_result: SNRTestResult,
            spwmap: list[int]
    ) -> tuple[dict[str, tuple[list[int], float]], dict[str, tuple[list[int], float]]]:
        """
        Process SNR results for combined spws for both empirical and catalogue SNRs
        using the same spwmap.

        Args:
            snr_result: SNRTestResult object containing empirical SNR values
            calc_snr_result: SNRTestResult object containing catalogue SNR values
            spwmap: list representing spectral window mapping

        Returns:
            tuple: (combined_snrs, calc_combined_snrs) containing the combined SNR results
        """
        combined_snrs = self._do_combined_snr_test(
            snr_result.spw_ids,
            snr_result.snr_values,
            spwmap
        )

        calc_combined_snrs = self._do_combined_snr_test(
            calc_snr_result.spw_ids,
            calc_snr_result.snr_values,
            spwmap
        )

        return combined_snrs, calc_combined_snrs


class SpwPhaseupResults(basetask.Results):
    def __init__(self, vis: str = None, phasecal_mapping: Dict = None, phaseup_result: GaincalResults = None,
                 snr_info: Dict = None, spwmaps: Dict = None, unregister_existing: Optional[bool] = False,
                 phaserms_totaltime: str = None, phaserms_cycletime: str = None,
                 phaserms_results: Optional[Dict] = None, phaserms_antout: Optional[List] = None):
        """
        Initialise the phaseup spw mapping results object.
        """
        super().__init__()

        if spwmaps is None:
            spwmaps = {}
        if phaserms_antout is None:
            phaserms_antout = []

        self.vis = vis
        self.phasecal_mapping = phasecal_mapping
        self.phaseup_result = phaseup_result
        self.snr_info = snr_info
        self.spwmaps = spwmaps
        self.unregister_existing = unregister_existing
        self.phaserms_totaltime = phaserms_totaltime
        self.phaserms_cycletime = phaserms_cycletime
        self.phaserms_results = phaserms_results
        self.phaserms_antout = ",".join(phaserms_antout)

    def merge_with_context(self, context):
        if self.vis is None:
            LOG.error(' No results to merge ')
            return

        if not self.phaseup_result.final:
            LOG.error(' No results to merge ')
            return

        # PIPE-629: if requested, unregister previous spwphaseup caltables from
        # the context before merging in the newly derived caltable.
        if self.unregister_existing:
            # Identify the MS to process
            vis: str = os.path.basename(self.vis)

            # predicate function that triggers when the spwphaseup caltable is
            # detected for this MS
            def spwphaseup_matcher(calto: callibrary.CalToArgs, calfrom: callibrary.CalFrom) -> bool:
                calto_vis = {os.path.basename(v) for v in calto.vis}
                do_delete = 'hifa_spwphaseup' in calfrom.gaintable and vis in calto_vis
                if do_delete:
                    LOG.info(f'Unregistering previous spwphaseup tables for {vis}')
                return do_delete

            context.callibrary.unregister_calibrations(spwphaseup_matcher)

        # Merge the spw phaseup offset table
        self.phaseup_result.merge_with_context(context)

        ms = context.observing_run.get_ms(name=self.vis)
        if ms:
            # Merge the spectral window mappings.
            ms.spwmaps = self.spwmaps

            # Merge the phase calibrator mapping.
            ms.phasecal_mapping = self.phasecal_mapping

    def __repr__(self):
        if self.vis is None or not self.phaseup_result:
            return ('SpwPhaseupResults:\n'
                    '\tNo spw phaseup table computed')
        else:
            s = f'SpwPhaseupResults:\nvis={self.vis}\n'
            for (intent, field), spwmapping in self.spwmaps.items():
                s += f'\t{intent}, {field}:\n'
                s += f'\t\tCombine = {spwmapping.combine}\n'
                s += f'\t\tSpwmap = {spwmapping.spwmap}\n'
                s += f'\t\tSolint = {spwmapping.solint}\n'
                s += f'\t\tGaintype = {spwmapping.gaintype}\n'
            return s
