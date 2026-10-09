import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.fluxscale.gcorfluxscale.GcorFluxscaleInputs.__init__
@utils.cli_wrapper
def hifa_gfluxscale(vis=None, reference=None, transfer=None, refintent=None, transintent=None, refspwmap=None,
                    reffile=None, phaseupsolint=None, solint=None, minsnr=None, refant=None, hm_resolvedcals=None,
                    antenna=None, peak_fraction=None, amp_outlier_sigma=None, parallel=None):
    """Transfer the absolute flux scale from amplitude calibrator to secondary calibrators and science targets.

    Derives flux densities for point-source transfer calibrators using flux models for reference calibrators.
    The absolute flux scale is transferred from the AMPLITUDE calibrator (often the same field as BANDPASS)
    to the PHASE calibrator and other secondary calibrators (CHECK, DIFFGAIN, and BANDPASS if not AMPLITUDE), 
    which is subsequently transferred to the science target via :func:`~pipeline.hif.cli.hif_applycal`.

    The workflow (as illustrated in the workflow logic diagram):

    .. figure:: /figures/PL2026_hifa_gfluxscale_workflowtitle.png
       :width: 60%
       :alt: Logical flow in hifa_gfluxscale

       Logical flow in ``hifa_gfluxscale``. Each box represents one ``gaincal``
       call per intent/field/Spectral Spec/EB. Italicized parameters originate
       from :func:`~pipeline.hifa.cli.hifa_spwphaseup`.

    1. Phase-up calibration is performed for all science spws for each calibrator field using the spw
       mapping/combine parameters and ``solint``/``gaintype`` established in :func:`~pipeline.hifa.cli.hifa_spwphaseup`.
       If there are other intents, e.g. BANDPASS, DIFFGAIN, that share the same field as the AMPLITUDE and
       are observed in different scans, then the phase-up is explicitly only performed on the intent
       AMPLITUDE and exclusively only that observing scan. Generally, ALMA uses the same field for
       BANDPASS and AMPLITUDE and it is usually observed in the same scan. During the gaincal processes for
       each field, if there are multiple fields per INTENT and/or more than one Spectral Spec (tuning setup)
       then a new caltable is created each time. Note that the phase solutions for the CHECK source(s)
       are saved and are shown in :func:`~pipeline.hifa.cli.hifa_timegaincal` in the plot of "Diagnostic Phase vs. time".
    2. Amplitude-only solutions are computed (with ``gaintype='T'``, combining polarizations), pre-applying
       the phase solutions.  ``gaintype='T'`` allows polarized calibrators to have differing flux densities
       in their calibrated XX and YY visibilities, and thereby avoids introducing any false polarization
       into the science targets. Again, if there are other intents that are the same field as the AMPLITUDE,
       only the AMPLITUDE intent is explicitly solved. For those intents that are the same field as the
       AMPLITUDE, a :func:`~casatasks.calibration.setjy` call is made to correctly set the flux scale.
    3. Obvious outlier amplitude solutions are identified and flagged in the caltable. Phase gaintables are not assessed.
    4. The flux scale is transferred from the reference calibrators to the transfer calibrators using
       ``refspwmap`` for windows without data in the reference calibrators.
    5. The computed flux density values are written to the MODEL_DATA column via :func:`~casatasks.calibration.setjy`.

    The WebLog lists the derived flux scale factors and calibrated flux densities (measured by vector-averaged
    calibrated visibility amplitude) for all non-amplitude calibrators, together with the ALMA Source Catalog
    values. Plots of amplitude vs. uv distance are shown.

    .. figure:: /figures/guide-img024.png
       :width: 60%
       :alt: Limited uv ranges for resolved calibrators

       Example of limited uv ranges for deriving the flux scale on resolved
       solar system objects.

    .. figure:: /figures/guide-img025.png
       :width: 60%
       :alt: Derived vs. catalog flux density plot

       Examples of derived vs. catalog flux density plots and associated QA
       messages.

    **Resolved calibrator antenna selection**: If the amplitude calibrator is resolved (i.e., it shows
    decreasing flux with increasing uv distance, which is assumed to apply only to solar system objects), only
    short baseline antennas are used in the calibration solves. The selection algorithm is:

    1. Estimate the solar system object calibrator size.
    2. Determine the longest observing wavelength across the science spws.
    3. Determine the shortest unprojected baseline to the reference antenna.
    4. Estimate the peak visibility amplitude at that baseline length.
    5. Find the baseline length where the transform of a uniform disk drops to 20% of that peak.
    6. Select antennas whose separation from the refant is within that length.
    7. If fewer than 3 antennas qualify, default to using all antennas.

    The selected antennas are listed in the WebLog table (blank entries mean all antennas were used, as is
    the case for quasar calibrators). The antenna selection can also be set manually via ``hm_resolvedcals``
    and ``antenna`` parameters.

    Notes:
        Three QA scores are computed for all non-FLUX calibrators:

        1. **Completeness**: fraction of spws with a derived flux determination (1.0 if all spws have a
           value, 0.5 if only half do, etc.).
        2. **SNR**: QA is blue (warning) if the flux determination SNR falls below 20, yellow (fail) if
           below 5, with linear interpolation between these limits.
        3. **Spectral consistency**: compares derived spectral index across spws to the Source Catalog.
           For each spw, R_spw = derived / catalog flux; K_spw = R_spw / R_spw(highest-SNR spw). QA
           score is based on max(\\|1 - K_spw\\|):

           - QA = 1.0 if max deviation < 0.1
           - QA = 0.75 if max deviation 0.1-0.2
           - QA = 0.5 if max deviation > 0.2

        The spectral consistency score can be low for reasons unrelated to the flux scale (e.g., low SNR
        in some spws causing amplitude noise bias, or atmospheric absorption lines). Check :func:`~pipeline.hif.cli.hif_applycal`
        to determine whether any low score represents a real science target issue.

        High values in the Flagged data summary table on the WebLog page are indicative of low SNR achieved
        on the corresponding object, even after attempting the best calibration possible according to 
        the :func:`~pipeline.hifa.cli.hifa_spwphaseup` low SNR cascade. In all cases, the percentages in both the before and 
        after columns will naturally be higher than the corresponding values seen on the later hif_applycal stage because in
        that stage the phase solutions are scan-based, and thus have a higher SNR.
    
        For very low SNR (low scores), the use of long ``solint`` in the phase-up can cause phase decoherence to be
        'baked in', artificially biasing amplitude gains upward and producing an incorrect flux scale.

        One QA score is computed for non-SSO AMPLITUDE calibrators:
 
        1. **Amplitude stability**: A QA score is calculated using the baseline-averaged calibrated visibility amplitude vs. time behavior during the scan. 
           If the spread of the amplitudes between the 1st and last quintiles is greater than 13% of the median amplitude, then a QA score of 0.66 is given, 
           decreasing linearly with a larger amplitude spread to a minimum score of 0.34 when the spread is greater than 26% of the median amplitude. 
           Low scores in this metric may indicate that the observing conditions are too unstable to trust the flux transfer from the amplitude 
           calibrator to the science fields. 


    Examples:
        1. Compute flux values for the phase calibrator using model data from the amplitude calibrator:

        >>> hifa_gfluxscale()

    """
