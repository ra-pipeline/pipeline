import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.gaincal.timegaincal.TimeGaincalInputs.__init__
@utils.cli_wrapper
def hifa_timegaincal(vis=None, calamptable=None, calphasetable=None, offsetstable=None, targetphasetable=None,
                     amptable=None, field=None, spw=None, antenna=None, calsolint=None, targetsolint=None, refant=None,
                     refantmode=None, solnorm=None, minblperant=None, calminsnr=None, targetminsnr=None, smodel=None,
                     parallel=None):
    """Determine temporal gains from calibrator observations.

    The time-dependent complex gains for each antenna/spw are determined from
    the raw data (DATA column) divided by the model (MODEL column), for the
    specified fields. The gains are computed according to the spw
    mapping/combination, solint, and gaintype as determined in hifa_spwphaseup.

    Previous calibrations are applied on the fly.

    The process to solve for the various complex gains follows:

    - Phase solutions are produced for all intents (excluding the CHECK intent)
      using the spw mapping/combination and gaintype determined in
      hifa_spwphaseup, and using solint = 'inf' (per scan). The solutions
      only registered for the PHASE intent to transfer to itself (PHASE intent)
      and the TARGET (and CHECK) intent(s) in hif_applycal.

    - Phase (phase-up) solutions are produced for all intents using the spw mapping/
      combination, solint (typically 'int' if not low SNR data) and gaintype as
      determined in hifa_spwphaseup. The solutions are used for (1) on-the-fly
      application as to solve the subsequent amplitude gains, (2) final phase
      correction in hif_applycal of the BANDPASS, AMPLITUDE, DIFFGAIN,
      POLARIZATION intents (i.e. after hif_applycal, those intents are
      self-calibrated but PHASE and CHECK are not.) These short-solint phases
      are also shown as ``diagnostic`` plots.

    - Amplitude solutions are produced for all calibrator intents with the above
      phase-up solutions pre-applied. The time solint is 'inf' (scan), so solutions
      are found for each scan and spw. The solutions are registered for AMP gain
      correction of all intents to themselves, and the PHASE intent to the TARGET
      and CHECK intent(s). Note: for band-to-band observations, there are no
      'high frequency' observations of the PHASE intent, and the full AMP gains are
      transferred from the AMPLITUDE intent to the TARGET and CHECK intent(s).

    - Short term ``diagnostic`` amplitude solutions are produced for all calibrator
      intents using the same short solint as that used for the PHASE intent
      phase-up (typically 'int' except for low SNR cases). These solutions are
      plotted but not applied.

    - Diagnostic phase offsets solutions are produced with solint='inf' for
      the BANDPASS and PHASE intent, first solving and preapplying the phase
      as a function of time with combine='spw' (to ``zero`` the phases),
      and then then solving phase(time) per spw.
      Note: by definition the BANDPASS phase will be exactly zero. The phase
      solutions for the PHASE intent are used by QA heuristics to identify jumps
      and drifts of the spw-spw offsets as a function of time, but if the SNR
      is very low, such offsets will not be able to detected.

    Good candidate reference antennas were determined using the :py:func:`hif_refant <hif_refant>` task.
    During all solutions for standard observing modes, the reference antenna can
    change flexibly. For polarization observations a good, un-flagged common
    reference antenna is found and locked in time. For band-to-band observations,
    all solutions are also made strictly enforcing the use of the selected
    reference antenna.

    Previous calibrations that have been stored in the pipeline context are
    applied on the fly.

    The WebLog shows time-series plots of all gains (phase then amplitude), followed by diagnostic Phase
    vs. Time plots for the bandpass, flux, polarization, and diffgain calibrators, and the phase calibrator
    short-solint solutions. Phase offset plots (one per spw) show the residual per-spw phase offsets vs.
    time; if the instrument is stable, these should scatter about zero with no drift.

    .. figure:: /figures/PL2025_hifa_timegaincal_allinone.png
       :scale: 60%
       :alt: Gain solution workflow for hifa_timegaincal

       Gain solution workflow. Each box shows when ``combine='spw'`` may have been
       set, subsequent usage (applycal or diagnostic plotting), and whether 'offset'
       solves are used for diagnostic plotting and QA.

    Notes:
        QA scores for the spw phase offset assessment (per spw, per antenna/polarisation):

        - If the standard deviation of all offsets over all antennas (sigma_off) for a spw > 15 deg: QA = 0.82
          (too noisy to assess; no further tests).
        - Otherwise, QA = 0.5 if any of the following holds:

          - Maximum offset > 30 deg or > 6 x sigma_off
          - Mean offset > 30 deg or > 6 x sigma_off / sqrt(N_ant)
          - Number of scan solutions > 3 and standard deviation of offsets > 30 deg or > 4 x sigma_off

        - Otherwise, QA = 0.8 if any of the same tests hold using relaxed limits (15 deg, 5 deg, 15 deg for
          max, mean, and std respectively).
        - The above scores are decreased by 0.1 if the spw was mapped (phase offsets may affect
          calibration). If the spw is not mapped, offsets should calibrate out, and a corresponding
          message is shown.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Compute standard per scan gain solutions that will be used to calibrate the target:

        >>> hifa_timegaincal()

    """
