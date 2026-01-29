import pipeline.h.cli.utils as utils


@utils.cli_wrapper
def hifv_swpowcal(vis=None, caltable=None, spw=None):
    """Runs gencal in swpow mode.

    Args:
        vis: List of input visibility data.

        caltable: String name of caltable.

        spw: Spectral-window/frequency/channel: '' ==> all, spw="0:17~19"

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Load an ASDM list in the ../rawdata subdirectory into the context:

        >>> hifv_swpowcal()

    """
