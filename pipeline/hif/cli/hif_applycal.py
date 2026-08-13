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

    An additional per-antenna QA score is computed from the calibrated Amplitude vs. Frequency and Phase
    vs. Frequency plots for each calibrator. For each antenna a linear function is fitted to the data per
    scan per polarisation, and the slope/offset is compared to the equivalent fit for all antennas. As of
    PL2025 outliers must exceed set thresholds (10% or 10% per 2 GHz for amplitude offset/slope, or 6 deg or
    6 deg per 2 GHz for phase offset/slope) to generate a QA message. Details of deviant antennas are reported
    in the expandable QA messages at the top of the page and in an ``applycalQA_outliers.txt`` file. Note
    that amplitude-frequency offsets symmetric in XX/YY and phase-frequency offsets for CHECK sources are
    excluded from the outlier QA.

    A uv-coverage plot (before and after calibration flags) is provided for the representative source and
    spw.

    Notes:
        Flagging QA: 0.0 if the additional flag fraction on the science target >= 50%; 1.0 if <= 5%;
        linearly interpolated between 0 and 1 for fractions between 5% and 50%.

    Examples:
        1. Apply the calibration to the target data:

        >>> hif_applycal(intent='TARGET')

    """
