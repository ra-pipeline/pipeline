import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.fluxscale.gcorfluxscale.GcorFluxscaleInputs.__init__
@utils.cli_wrapper
def hifa_gfluxscale(vis=None, reference=None, transfer=None, refintent=None, transintent=None, refspwmap=None,
                    reffile=None, phaseupsolint=None, solint=None, minsnr=None, refant=None, hm_resolvedcals=None,
                    antenna=None, peak_fraction=None, amp_outlier_sigma=None, parallel=None):
    """Transfer the absolute flux scale from amplitude calibrator to secondary calibrators and science targets.

    Derives flux densities for point-source transfer calibrators using flux models for reference calibrators.
    The absolute flux scale is transferred from the amplitude calibrator to the phase calibrator and other
    secondary calibrators, which is subsequently transferred to the science target via :py:func:`hif_applycal <hif_applycal>`.

    The workflow (as illustrated in the WebLog logic diagram):

    .. figure:: /figures/PL2025_hifa_gfluxscale_all.png
       :scale: 60%
       :alt: Logical flow in hifa_gfluxscale

       Logical flow in ``hifa_gfluxscale``. Each box represents one ``gaincal``
       call per intent/field/Spectral Spec/EB. Italicized parameters originate
       from :py:func:`hifa_spwphaseup <hifa_spwphaseup>`.

    1. Phase-up calibration is performed for all science spws for each calibrator field using the spw
       mapping/combine parameters and ``solint``/``gaintype`` established in :py:func:`hifa_spwphaseup <hifa_spwphaseup>`.
    2. Amplitude-only solutions are computed (with ``gaintype='T'``, combining polarisations), pre-applying
       the phase solutions.
    3. Obvious outlier amplitude solutions are identified and flagged in the caltable.
    4. The flux scale is transferred from the reference calibrators to the transfer calibrators using
       ``refspwmap`` for windows without data in the reference calibrators.
    5. The computed flux density values are written to the MODEL_DATA column via ``setjy``.

    The WebLog lists the derived flux scale factors and calibrated flux densities (measured by vector-averaged
    calibrated visibility amplitude) for all non-amplitude calibrators, together with the ALMA Source Catalog
    values. Plots of amplitude vs. uv distance are shown.

    .. figure:: /figures/guide-img024.png
       :scale: 60%
       :alt: Limited uv ranges for resolved calibrators

       Example of limited uv ranges for deriving the flux scale on resolved
       solar system objects.

    .. figure:: /figures/guide-img025.png
       :scale: 60%
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
        in some spws causing amplitude noise bias, or atmospheric absorption lines). Check :py:func:`hif_applycal <hif_applycal>`
        to determine whether any low score represents a real science target issue.

        For very low SNR, the longer ``solint`` used in the phase-up can cause phase decoherence to be
        'baked in', artificially biasing amplitude gains upward and producing an incorrect flux scale.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Compute flux values for the phase calibrator using model data from the amplitude calibrator:

        >>> hifa_gfluxscale()

    """
