import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.flagging.flagdeteralma.FlagDeterALMAInputs.__init__
@utils.cli_wrapper
def hifa_flagdata(vis=None, autocorr=None, shadow=None, tolerance=None, scan=None, scannumber=None, intents=None,
                  edgespw=None, fracspw=None, fracspwfps=None, online=None, partialpol=None, lowtrans=None,
                  mintransrepspw=None, mintransnonrepspws=None, fileonline=None, template=None, filetemplate=None,
                  hm_tbuff=None, tbuff=None, qa0=None, qa2=None, flagbackup=None, parallel=None):
    """Do metadata based flagging of a list of MeasurementSets.

    The ``hifa_flagdata`` task performs basic flagging operations on a list of MeasurementSets including:

    - applying online flags (XML format, including QA0 flags for antenna pointing calibration failures)
    - applying a flagging template
    - partial polarization flagging
    - autocorrelation data flagging
    - shadowed antenna data flagging
    - scan-based flagging by intent or scan number
    - edge channel flagging, as needed
    - low atmospheric transmission flagging

    The WebLog page shows whether any data in these categories were flagged (a check mark means yes, an X means no).
    The Flagged data summary table shows the percentage of flagged data per MS. The ``Before Task`` column contains
    only the effect of the Binary Data Flags (BDF) from the correlator applied during :py:func:`hifa_importdata <hifa_importdata>`. The
    additional flags are applied in the order of columns shown in the table, with each column reflecting the
    additional amount of data flagged when applying that flag reason.

    The Low Transmission flagging agent flags spws whose transmission across 60% of their bandwidth is less than
    10% on non-representative spws and less than 5% on the representative spw. This heuristic can be disabled with
    the boolean value ``lowtrans`` in the PPR. The thresholds can be adjusted via ``mintransnonrepspws`` (default
    10%) and ``mintransrepspw`` (default 5%). The following fixed meteorological values are used to avoid
    susceptibility to faulty weather station values: pressure=563 mb, altitude=5059 m, temperature=273 K,
    maxAltitude=48 km, humidity=20%, water vapor scale height h0=1.0 km, initial pressure step dP=5.0 mb, and
    multiplicative factor dPm=1.1. The PWV is the actual median across the EB; the airmass is the mean of the
    first and final integration of the scan.

    About the spectral window edge channel flagging:

    - For TDM spectral windows, a number of edge channels are always flagged, according to the ``fracspw`` and
      ``fracspwfps`` parameters (the latter operates only on spectral windows with 62, 124, or 248 channels). With
      the default setting of ``fracspw``, the number of channels flagged on each edge is 2, 4, or 8 for 64, 128,
      or 256-channel spectral windows, respectively.

    - For most FDM spectral windows, no edge flagging is done. The only exceptions are ACA spectral windows that
      encroach too close to the baseband edge. Channels that lie closer to the baseband edge than the following
      values are flagged: 62.5, 40, 20, 10, and 5 MHz for spectral windows with bandwidths of 1000, 500, 250, 125,
      and 62.5 MHz, respectively. A warning is generated in the weblog if flagging occurs due to proximity to the
      baseband edge. By definition, 2000 MHz spectral windows always encroach the baseband edge on both sides, and
      thus are always flagged on both sides in order to achieve 1875 MHz bandwidth (flagged by 62.5 MHz on each
      side); thus no warning is generated.

    Notes:
        **QA Scoring**

        The QA score based on BDF+QA0+online+template+shadow flags: 0.0 if the flag fraction is >=60%, 1.0 if
        <=5%, linearly interpolated in between. An additional QA score of 0.8 results if the baseband frequency
        range could not be calculated for a spw. For Low Transmission flagging: 1.0 if no spw is flagged, 0.9 if
        a non-representative spw is flagged, 0.33 if the representative spw is flagged.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Do basic flagging on a MeasurementSet:

        >>> hifa_flagdata()

        2. Do basic flagging on a MeasurementSet flagging additional scans selected
        by number as well:

        >>> hifa_flagdata(scannumber='13,18')

    """
