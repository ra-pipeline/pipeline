import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.vlassmasking.vlassmasking.VlassmaskingInputs.__init__
@utils.cli_wrapper
def hifv_vlassmasking(vis=None, vlass_ql_database=None, maskingmode=None, catalog_search_size=None):
    """Create clean masks for VLASS Single Epoch (SE) images.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Basic vlassmasking task:

        >>> hifv_vlassmasking()

    """
