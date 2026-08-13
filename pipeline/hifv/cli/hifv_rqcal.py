import pipeline.h.cli.utils as utils


@utils.cli_wrapper
def hifv_rqcal(vis=None, caltable=None):
    """Runs gencal in rq mode.

    Args:
        vis: List of input visibility data.

        caltable: String name of caltable.

    Examples:
        1. Load an ASDM list in the ../rawdata subdirectory into the context:

        >>> hifv_rqcal()

    """
