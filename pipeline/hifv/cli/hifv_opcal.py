import pipeline.h.cli.utils as utils


@utils.cli_wrapper
def hifv_opcal(vis=None, caltable=None):
    """Runs gencal in opac mode.

    Args:
        vis: List of input visibility data.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Load an ASDM list in the ../rawdata subdirectory into the context:

        >>> hifv_opcal()

    """
