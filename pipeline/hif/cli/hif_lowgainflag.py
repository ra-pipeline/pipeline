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

    1. Performs an initial phase-up for the BANDPASS intent and creates a bandpass calibration table.
       For ALMA data, since PL2026 this follows the low SNR heuristic process from
       :func:`~pipeline.hifa.cli.hifa_bandpass` (``almaphcorbandpass.py``) that can trigger
       ``combine='spw'`` if any spectral window has a phaseup SNR
       lower than ``phaseupsnr=5``.
    2. Creates a gain phase calibration table. The phase solve for ALMA data inherits any
       low SNR parameters for ``combine`` and ``solint``. Default values are no combine, and ``solint='int'``.
       If ``combine='spw'``, then before the phaseup solve, an additional phase offset calibration is made 
       per spw using ``solint='inf'``.
    3. Creates a gain amplitude calibration table. This uses parameters ``solint='inf'`` and ``gaintype='T'``.
    4. Uses the gain amplitude table to identify antennas with outlier gains per spw.
    5. Applies flagging commands for the identified outlier antennas to the entire MS.

    All temporary gain tables are discarded after the task.

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

    Examples:
        1. Flag antennas with low or high gain using recommended thresholds:

        >>> hif_lowgainflag()

    """
