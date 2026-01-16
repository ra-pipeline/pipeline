import pipeline.h.cli.utils as utils


@utils.cli_wrapper
def hifv_gaincurves(vis=None, caltable=None):
    """Runs gencal in gc mode.

    Args:
        vis: List of input visibility data.

        caltable: String name of caltable.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Load an ASDM list in the ../rawdata subdirectory into the context:

        >>> hifv_gaincurves()

    """
