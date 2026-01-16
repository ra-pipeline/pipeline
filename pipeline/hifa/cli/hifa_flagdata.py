import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.flagging.flagdeteralma.FlagDeterALMAInputs.__init__
@utils.cli_wrapper
def hifa_flagdata(vis=None, autocorr=None, shadow=None, tolerance=None, scan=None, scannumber=None, intents=None,
                  edgespw=None, fracspw=None, fracspwfps=None, online=None, partialpol=None, lowtrans=None,
                  mintransrepspw=None, mintransnonrepspws=None, fileonline=None, template=None, filetemplate=None,
                  hm_tbuff=None, tbuff=None, qa0=None, qa2=None, flagbackup=None, parallel=None):
    """Do metadata based flagging of a list of MeasurementSets.

    The hifa_flagdata data performs basic flagging operations on a list of
    measurements including:

    - applying online flags
    - applying a flagging template
    - partial polarization flagging
    - autocorrelation data flagging
    - shadowed antenna data flagging
    - scan-based flagging by intent or scan number
    - edge channel flagging, as needed
    - low atmospheric transmission flagging

    About the spectral window edge channel flagging:

    - For TDM spectral windows, a number of edge channels are always flagged,
      according to the ``fracspw`` and ``fracspwfps`` parameters (the latter
      operates only on spectral windows with 62, 124, or 248 channels). With the
      default setting of ``fracspw``, the number of channels flagged on each edge
      is 2, 4, or 8 for 64, 128, or 256-channel spectral windows, respectively.

    - For most FDM spectral windows, no edge flagging is done. The only exceptions
      are ACA spectral windows that encroach too close to the baseband edge.
      Channels that lie closer to the baseband edge than the following values are
      flagged: 62.5, 40, 20, 10, and 5 MHz for spectral windows with bandwidths of
      1000, 500, 250, 125, and 62.5 MHz, respectively. A warning is generated in
      the weblog if flagging occurs due to proximity to the baseband edge.
      By definition, 2000 MHz spectral windows always encroach the baseband edge on
      both sides of the spectral window, and thus are always flagged on both sides
      in order to achieve 1875 MHz bandwidth (in effect, they are flagged by
      62.5 MHz on each side), and thus no warning is generated.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Do basic flagging on a MeasurementSet:

        >>> hifa_flagdata()

        2. Do basic flagging on a MeasurementSet flagging additional scans selected
        by number as well:

        >>> hifa_flagdata(scannumber='13,18')

    """
