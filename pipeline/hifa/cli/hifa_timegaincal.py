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
    mapping/combination, ``solint``, and ``gaintype`` as determined in :func:`~pipeline.hifa.cli.hifa_spwphaseup`.
    All previous calibrations that have been stored in the pipeline context are
    applied on-the-fly.

    The process to solve for the various complex gains follows (see the workflow diagram):

    - Phase solutions are produced for all intents (excluding the CHECK intent)
      using the spw mapping/combination and ``gaintype`` determined in
      :func:`~pipeline.hifa.cli.hifa_spwphaseup`, and using ``solint = 'inf'`` (per scan). The solutions
      are only registered for the PHASE intent to conduct phase transfer to itself (PHASE intent)
      and the TARGET (and CHECK) intent(s) in :func:`~pipeline.hif.cli.hif_applycal`.

    - Phase (phase-up) solutions are produced for all intents using the spw mapping/
      combination, ``solint`` (typically 'int' if not low SNR data) and ``gaintype`` as
      determined in :func:`~pipeline.hifa.cli.hifa_spwphaseup`. The solutions are used for (1) on-the-fly
      application as to solve the subsequent amplitude gains in :func:`~pipeline.hifa.cli.hifa_timegaincal`,
      (2) final phase correction in :func:`~pipeline.hif.cli.hif_applycal` of the BANDPASS, AMPLITUDE, DIFFGAIN,
      POLARIZATION intents (i.e. in :func:`~pipeline.hif.cli.hif_applycal` those intents are
      self-calibrated with the shortest ``solint`` solve, ideally 'int', whereas the  PHASE
      and CHECK intents are not). These short-solint phases are also shown as `diagnostic` plots
      in the WebLog.

    - Amplitude solutions are produced for all calibrator intents with the above
      phase-up solutions pre-applied. The ``solint='inf'``, such that solutions
      are found for each scan and spw. The solutions are registered for amplitude gain
      correction of all intents to themselves, and the PHASE intent to the TARGET
      and CHECK intent(s) that are applied in :func:`~pipeline.hif.cli.hif_applycal`.
      Note: for band-to-band observations, there are no
      'high frequency' observations of the PHASE intent, and amplitude gains are
      transferred exclusively from the AMPLITUDE intent to the TARGET and CHECK intent(s).

    - Short term `diagnostic` amplitude solutions are also produced for all calibrator
      intents using the short ``solint`` as that used for the PHASE intent
      phase-up (typically 'int' except for low SNR cases - see :func:`~pipeline.hifa.cli.hifa_spwphaseup`).
      These solutions are only plotted in the Weblog and are not applied.

    - Diagnostic phase offsets solutions are produced with ``solint='inf'`` for
      the BANDPASS and PHASE intents. First if ``combine='spw'`` was not already used for
      the PHASE intent, then re-solve the phases using ``solint`` as established in 
      in :func:`~pipeline.hifa.cli.hifa_spwphaseup` and forcing ``combine='spw'``. These
      solutions are then pre-applied before solving the phases again (i.e. the offsets),
      explicitly per spw and using ``solint='inf'``. By definition the BANDPASS phase
      will be exactly zero as the stored calibration for the per-spw offsets from :func:`~pipeline.hifa.cli.hifa_spwphaseup`
      is pre-applied. Only the phase solutions for the PHASE intent are used by QA heuristics to identify jumps
      and drifts of the spw-to-spw offsets as a function of time. If the SNR
      is very low, such offsets will not be determinable within the noise spread.
      For band-to-band data the DIFFGAIN is solved and shown but not assessed.

    Good candidate reference antennas were determined using the :func:`~pipeline.hif.cli.hif_refant` task.
    During all solutions for standard observing modes, the reference antenna can
    change flexibly. For polarization observations a good, un-flagged common
    reference antenna is found and locked in time :func:`~pipeline.hifa.cli.hifa_lock_refant`.
    For band-to-band observations, the PHASE intent per scan solutions using
    ``solint='inf'`` also enforce ``refantmode='strict'`` such that only the
    initially selected reference antenna is used. 


    The WebLog shows time-series plots of all gains:

    - Phase vs. time ``solint='inf'``.
    - Amplitude vs. time ``solint='inf'``.
    - Diagnostic phase vs. time short-solint (usually ``solint='int'``).
    - Phase offset plots, i.e. the residual per-spw phase offsets vs. time ``solint='inf'`; if the
      instrument is stable, these should scatter about zero with no drift or outliers.
    - Diagnostic amplitude vs. time short-solint (set by ``solint`` for PHASE
      intent in :func:`~pipeline.hifa.cli.hifa_spwphaseup`).
    
    .. figure:: /figures/PL2025_hifa_timegaincal_allinone.png
       :width: 60%
       :alt: Gain solution workflow for hifa_timegaincal

       Gain solution workflow. Each box shows when ``combine='spw'`` may have been
       set, subsequent usage (applycal or diagnostic plotting), and whether 'offset'
       solves are used for diagnostic plotting and QA.

    Notes:
        QA scores for the spw phase offset assessment (per spw, per antenna/polarization):

        - If the standard deviation of all offsets over all antennas (sigma_off) for a spw > 15 deg: QA = 0.82
          (too noisy to assess; no further tests).
        - Otherwise, if any of the following holds:

          - Maximum offset > 30 deg or > 6 x sigma_off
          - Mean offset > 30 deg or > 6 x sigma_off / sqrt(N_ant)
          - Number of scan solutions > 3 and standard deviation of offsets > 30 deg or > 4 x sigma_off
 
          Then QA = 0.5 if the spw is mapped, otherwise QA = 0.75.

        - Otherwise, if any of the same tests hold using relaxed limits (15 deg, 5 deg, 15 deg for
          max, mean, and std respectively) then QA = 0.7 if the spw is mapped, else QA = 0.8

    Examples:
        1. Compute standard per scan gain solutions that will be used to calibrate the target:

        >>> hifa_timegaincal()

    """
