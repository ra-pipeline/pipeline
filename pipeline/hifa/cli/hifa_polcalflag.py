import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.polcalflag.polcalflag.PolcalflagInputs.__init__
@utils.cli_wrapper
def hifa_polcalflag(vis=None, examineCrossPolSum=None):
    """Flag outlier visibilities in the polarization calibrator data.

    Performs a temporary calibration and applies it, then identifies and flags outlier visibilities in the
    polarization calibrator by examining the scalar difference of calibrated amplitudes minus model
    amplitudes (the same approach as :py:func:`hifa_bandpassflag <hifa_bandpassflag>` and :py:func:`hifa_gfluxscaleflag <hifa_gfluxscaleflag>`). The polarization
    calibrator is always treated as a multi-scan calibrator.

    The WebLog shows amplitude vs. uv-distance and amplitude vs. time plots before flagging and (if any
    flags were found) after flagging.

    Notes:
        QA = 1 - (fraction of data newly flagged). An additional score of 0.8 is assigned if any spw has
        an antenna that is fully flagged.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Run with recommended settings to flag visibility outliers in the polarization calibrator data:

        >>> hifa_polcalflag()

    """
