import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.rawflagchans.rawflagchans.RawflagchansInputs.__init__
@utils.cli_wrapper
def hif_rawflagchans(vis=None, spw=None, intent=None,
                     flag_hilo=None, fhl_limit=None, fhl_minsample=None,
                     flag_bad_quadrant=None, fbq_hilo_limit=None,
                     fbq_antenna_frac_limit=None, fbq_baseline_frac_limit=None,
                     parallel=None):
    """Flag deviant baseline/channels in raw data.

    Detects severe baseline-based anomalies in the uncalibrated visibilities prior to antenna-based calibration.
    Bad data are often caused by hardware problems during the observation. Outlier channels and baselines are
    detected using data from the bandpass calibrator intent (default).

    Bad baseline/channels are flagged for all intents, not just the one that is the basis of the flagging views.

    For each spectral window the flagging view is a 2D image with axes 'channel' and 'baseline'. Each pixel is
    the time-average of the underlying unflagged raw data. The baseline axis is labelled as id1.id2 where id1
    and id2 are the IDs of the baseline antennas; each baseline appears twice so that bad antennas are easily
    identified by eye.

    The WebLog links to the flagging-view images. Flagged data are shown on the plots together with a summary of
    all flagging performed by this task.

    Two flagging rules are applied:

    **1. Bad quadrant matrix flagging rule** (``flag_bad_quadrant=True``):

    Outliers are first identified as data points whose value deviates from the median of all non-flagged data by
    more than ``fbq_hilo_limit`` (default: 8.0) times the MAD::

        flagging mask = (data - median(all non-flagged data)) > (MAD(all non-flagged data) * fbq_hilo_limit)

    The flagging view is then split into 4 equal channel quadrants. For each antenna and quadrant:

    1. Select baselines belonging to the antenna within the quadrant.
    2. Count newly found outlier datapoints in that selection.
    3. Count originally unflagged datapoints in that selection.
    4. Compute fraction = new outliers / originally unflagged.
    5. If fraction > ``fbq_antenna_frac_limit`` (default: 0.2), flag all channels in that quadrant for that
       antenna; otherwise take no action.

    Any remaining outliers not caught per-antenna are then evaluated per-baseline and per-quadrant:

    1. Select the baseline and channels within the quadrant.
    2. Compute fraction = new outliers / originally unflagged.
    3. If fraction > ``fbq_baseline_frac_limit`` (default: 1.0), flag all channels in that quadrant for that
       baseline; otherwise take no action.

    Suspect points are not individually flagged unless they are part of a bad antenna or baseline quadrant.

    **2. Outlier matrix flagging rule** (``flag_hilo=True``):

    Data points are flagged individually if their value deviates from the median of all non-flagged data by more
    than ``fhl_limit`` (default: 20.0) times the MAD::

        flagging mask = (data - median(all non-flagged data)) > (MAD(all non-flagged data) * fhl_limit)

    No flagging is attempted if the number of data points in the flagging view is less than ``fhl_minsample``
    (default: 5). As of PL2023, channels coinciding with strong ozone lines are excluded from the flagging list.

    Notes:
        The QA score for this stage is equal to ``1 - (fraction of data newly flagged)``.

    Examples:
        1. Flag bad quadrants and wild outliers, default method:

        >>> hif_rawflagchans()

        equivalent to:

        >>> hif_rawflagchans(flag_hilo=True, fhl_limit=20, flag_bad_quadrant=True, fbq_hilo_limit=8,
        ...                  fbq_antenna_frac_limit=0.2, fbq_baseline_frac_limit=1.0)

    """
