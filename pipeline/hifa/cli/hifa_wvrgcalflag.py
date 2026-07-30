import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.wvrgcalflag.wvrgcalflag.WvrgcalflagInputs.__init__
@utils.cli_wrapper
def hifa_wvrgcalflag(vis=None, caltable=None, offsetstable=None, hm_toffset=None, toffset=None, segsource=None,
                     sourceflag=None, hm_tie=None, tie=None, nsol=None, disperse=None, wvrflag=None, hm_smooth=None,
                     smooth=None, scale=None, maxdistm=None, minnumants=None, mingoodfrac=None, refant=None,
                     flag_intent=None, qa_intent=None, qa_bandpass_intent=None, accept_threshold=None, flag_hi=None,
                     fhi_limit=None, fhi_minsample=None, ants_with_wvr_thresh=None, parallel=None):
    """Generate and apply a WVR phase correction table, flagging antennas with bad radiometers.

    Water Vapor Radiometer (WVR) sky brightness temperature measurements in four sub-bands surrounding the
    183 GHz water line are converted by the CASA task ``wvrgcal`` into a phase correction table. The phase
    rms during observation of the bandpass calibrator, measured with and without the WVR correction, is used
    to (1) detect poorly performing WVR units on individual antennas and (2) determine whether the overall
    WVR correction is beneficial.

    For heterogeneous arrays the task will only attempt a correction if at least ``ants_with_wvr_nr_thresh``
    (default: 3) 12-m antennas have WVRs **and** the fraction of WVR-equipped antennas is at least
    ``ants_with_wvr_thresh`` (default: 0.2). If these thresholds are not met, no WVR caltable is created.

    For each qualifying MS the workflow is:

    1. Generate a gain table from the WVR data.
    2. Apply the WVR calibration to the data specified by ``flag_intent``; compute per-scan flagging views
       showing the ratio ``phase-rms(with WVR) / phase-rms(without WVR)`` — a ratio < 1 indicates
       improvement.
    3. Search the views for antennas with anomalously high ratios. If found, recalculate the WVR calibration
       with those antennas excluded (``wvrflag``), interpolating results from nearby antennas within
       ``maxdistm`` (default: 500 m) provided at least ``minnumants`` (default: 2) are available.
    4. If after flagging the remaining WVR-equipped antennas fall below the count/fraction thresholds,
       reject the WVR caltable and do not use it in subsequent calibration.
    5. If the overall QA score exceeds ``accept_threshold`` the WVR caltable is merged into the context.

    For heterogeneous arrays, 7-m (CM) antennas are never removed from the reference antenna list.

    The WebLog shows the effects of the phase correction, which antennas (if any) had their WVR data flagged,
    per-antenna path-length RMS ('RMS') and channel-to-channel discrepancy ('Disc') values, and a warning if
    the correction is not helpful enough to apply.

    Notes:
        QA is produced per MS via a two-stage metric:

        - Stage 1: assess the RMS improvement ratio for BANDPASS and PHASE calibrator sources. The CASA log
          lists the ratios of with-WVR phase RMS / without-WVR phase RMS (i.e. 1 / improvement). If the
          PHASE calibrator has low SNR with phase RMS > 90 deg on longer baselines, it is excluded and only
          the BANDPASS improvement ratio is used.
        - Stage 2: cap the score for issues such as flagged antennas, RMS or Disc values > 0.5 mm, low SNR,
          or high atmospheric phase variation. The final score is determined by fixed-range linear fits from
          the scoring tree shown below.

        .. figure:: /figures/hifa_wvrgcalflag_scoring_PL2023.png
           :scale: 60%
           :alt: QA scoring workflow for hifa_wvrgcalflag

           QA scoring workflow showing initial and secondary scoring criteria, the resulting
           QA metric score range and corresponding color, the meaning of each score, and
           instructions for QA analysts reviewing the WebLog.

        The final stage score is the lowest score across all MeasurementSets.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Compute the WVR calibration for all the MeasurementSets:

        >>> hifa_wvrgcalflag(hm_tie='automatic')

    """
