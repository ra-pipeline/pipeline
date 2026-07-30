import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.tsysflag.tsysflag.TsysflagInputs.__init__
@utils.cli_wrapper
def hifa_tsysflag(vis=None, caltable=None,
                  flag_nmedian=None, fnm_limit=None, fnm_byfield=None,
                  flag_derivative=None, fd_max_limit=None,
                  flag_edgechans=None, fe_edge_limit=None,
                  flag_fieldshape=None, ff_refintent=None, ff_max_limit=None,
                  flag_birdies=None, fb_sharps_limit=None,
                  flag_toomany=None, tmf1_limit=None, tmef1_limit=None,
                  metric_order=None, normalize_tsys=None, filetemplate=None,
                  parallel=None):
    """Flag deviant system temperatures in the Tsys calibration table.

    Flags erroneous Tsys measurements in the calibration table created by :py:func:`h_tsyscal <h_tsyscal>`. Detected anomalies include
    anomalously high Tsys over an entire spectral window, spikes or 'birdies', and discrepant spectral shape as a
    function of frequency. The WebLog provides details for each kind of flagging performed and plots all Tsys
    spectra after flagging. If a Tsys flag template file is provided via the ``filetemplate`` parameter, those
    manual flags are also applied.

    Six separate flagging metrics are evaluated in the order set by ``metric_order``
    (default: ``'nmedian, derivative, edgechans, fieldshape, birdies, toomany'``):

    **1. nmedian** — Flag time/antenna points with anomalously high median Tsys.
    A time x antenna matrix view is built per polarisation and spw. Points are flagged if their value exceeds
    ``fnm_limit`` (default: 2.0) times the median of all non-flagged data points. Individual sources are evaluated
    separately when ``fnm_byfield=True`` (default) to prevent elevation differences from causing spurious flags at
    high frequencies.

    **2. derivative** — Flag time/antenna points with high median channel-to-channel derivative (ringing).
    For each antenna/timestamp the view value is calculated as
    ``median(abs(valid_data - median(valid_data))) * 100.0``, where ``valid_data`` is the channel-to-channel
    difference of Tsys normalized by the frequency median of Tsys. Points are flagged if their absolute value
    exceeds ``fd_max_limit`` (default: 5).

    **3. edgechans** — Flag edge channels of the Tsys spectra.
    A median Tsys spectrum (over all antennas) is formed per spw per intent (ATMOSPHERE, BANDPASS, AMPLITUDE).
    Edge channels are flagged from the outermost inward until the first channel where the channel-to-channel
    difference falls below ``fe_edge_limit`` (default: 3.0) times the median channel-to-channel difference.

    **4. fieldshape** — Flag time/antenna points whose Tsys spectral shape differs from the reference.
    The view value is ``100 * mean(abs(normalized_Tsys - reference_normalized_Tsys))`` where the reference
    is formed from the ``ff_refintent`` (default: ``'BANDPASS'``) intent fields. Points are flagged if their
    value exceeds ``ff_max_limit`` (default: 13).

    **5. birdies** — Flag narrow spikes that appear in some but not all antennas.
    A difference spectrum (per-antenna median minus all-antenna median) is formed per spw/antenna. The
    'sharps' rule runs two passes:

    1. Flag channels whose absolute step to the next channel exceeds ``fb_sharps_limit`` (default: 0.15).
    2. Around each newly flagged channel, flag neighbours until the channel-to-channel difference drops below
       twice the median channel-to-channel difference.

    **6. toomany** — Flag entire timestamps or spws when too many antennas are already flagged.
    Uses the same time x antenna matrix as 'nmedian'. Two sub-rules are applied:

    - ``tmf`` (too many flags): Flag an entire timestamp if the fraction of flagged antennas exceeds
      ``tmf1_limit`` (default: 0.666).
    - ``tmef`` (too many entirely flagged): Flag all antennas in all timestamps within a (spw, pol) view if
      the fraction of entirely flagged antennas exceeds ``tmef1_limit`` (default: 0.666).

    Notes:
        QA = 0.0 if additional flagging fraction >= 50%, QA = 1.0 if <= 5%, linearly interpolated between 0 and 1
        for fractions between 5% and 50%. An additional score of 0.8 is assigned if any spw has an antenna that is
        fully flagged.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Flag Tsys measurements using currently recommended tests:

        >>> hifa_tsysflag()

        2. Flag Tsys measurements using all recommended tests apart from the 'fieldshape' metric:

        >>> hifa_tsysflag(flag_fieldshape=False)

    """
