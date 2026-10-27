import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.applycal.ifapplycal.IFApplycalInputs.__init__
@utils.cli_wrapper
def hif_applycal(vis=None, field=None, intent=None, spw=None, antenna=None, parang=None, applymode=None, calwt=None,
                 flagbackup=None, flagsum=None, flagdetailedsum=None, parallel=None):
    """Apply precomputed calibration tables to the visibility data.

    Applies all calibration tables stored in the pipeline context to the visibility data using
    predetermined field/spw maps and default interpolation parameters. Failed calibration solutions and
    flagged Tsys scans propagate as additional flags in the science data at this stage.

    The WebLog shows a summary of the additional flagging applied at this stage, and many plots of the
    calibrated data as a function of time and frequency. To reduce processing time, target plots include
    only the representative target (and for mosaics, only the brightest field).

    Outliers in these plots can indicate remaining bad data, particularly for sources that were
    self-calibrated (i.e. all calibrators except for check sources).  To help identify these, an additional
    per-antenna QA score is computed from the calibrated Amplitude vs. Frequency and Phase vs. Frequency
    plots for each calibrator. For each antenna a linear function is fitted to the data per scan per
    polarisation, and the slope/offset is compared to the equivalent fit for all antennas. Outliers must
    exceed set thresholds (10% or 10% per 2 GHz for amplitude offset/slope, or 6 deg or 6 deg per 2 GHz
    for phase offset/slope) to generate a QA score. For outliers above the set thresholds, a decreasing QA
    score from 0.74 to 0.34 is assigned based on how significant the outlier is. However, amplitude-frequency
    offsets that are symmetric in XX/YY are assigned a fixed score of 0.80 (since these do not affect imaging),
    and phase-frequency offsets for CHECK sources are assigned a fix score of 0.85 (since these are diagnostic
    and do not affect source calibration). An aggregated summary of outliers is reported in the expandable QA
    messages at the top of the page, and details reported in an `applycalQA_outliers.txt` file linked to at
    the bottom.


    It is important to note that not all reported outliers are (1) visible in the corresponding plots in
    hif_applycal (which are averaged over all scans), or (2) consequential to the final products (since the
    mean calibration solutions are still robust and adequate to calibrate the final data). However, if
    problems with the calibration are subsequently found, these messages provide clues on where to look
    for problems. For data that are delivered as QA2 Pass, one can assume that the data reviewers have
    checked these messages and concluded that the overall calibration is not significantly compromised.
    
    A uv-coverage plot is provided for the representative source and
    spw.

    Notes:
        Flagging QA: 0.0 if the additional flag fraction on the science target >= 79%; 1.0 if <= 24%;
        linearly interpolated between 0 and 1 for fractions between 79% and 24%.

    Examples:
        1. Apply the calibration to the target data:

        >>> hif_applycal(intent='TARGET')

    """
