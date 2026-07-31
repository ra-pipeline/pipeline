import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.lowgainflag.lowgainflag.LowgainflagInputs.__init__
@utils.cli_wrapper
def hif_lowgainflag(vis=None, intent=None, spw=None, refant=None, flag_nmedian=None, fnm_lo_limit=None,
                    fnm_hi_limit=None, tmef1_limit=None):
    """Flag antennas with persistently discrepant amplitude gains.

    Detects antennas with outlier amplitude gains calculated from the bandpass calibrator observation. The
    WebLog links to greyscale images of the relative gain per antenna and indicates which antennas, if any,
    were flagged.

    The task performs the following steps:

    1. Performs an initial phase-up for the BANDPASS intent.
    2. Creates a bandpass calibration table.
    3. Creates a gain phase calibration table.
    4. Creates a gain amplitude calibration table.
    5. Uses the gain amplitude table to identify antennas with outlier gains per spw.
    6. Applies flagging commands for the identified outlier antennas to the entire MS.

    A separate time x antenna matrix view is created per spw. Each point is the absolute gain amplitude for
    that antenna/timestamp. Antennas are flagged if their gain is:

    - Below ``fnm_lo_limit`` (default: 0.5) times the median of all non-flagged data points, or
    - Above ``fnm_hi_limit`` (default: 1.5) times the median of all non-flagged data points.

    If any antennas are significantly flagged, the reference antenna ranked list is reordered with the flagged
    antennas moved to the end; an 'Attention' notification appears at the top of the WebLog page.

    Notes:
        QA = 0.0 if additional flagging fraction >= 50%, QA = 1.0 if <= 5%, linearly interpolated between 0
        and 1 for fractions between 5% and 50%. An additional score of 0.8 is assigned if any spw has an
        antenna that is fully flagged.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Flag antennas with low or high gain using recommended thresholds:

        >>> hif_lowgainflag()

    """
