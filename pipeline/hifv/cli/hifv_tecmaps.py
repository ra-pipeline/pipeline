import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.tecmaps.tecmaps.TecMapsInputs.__init__
@utils.cli_wrapper
def hifv_tecmaps(vis=None):
    """Base tecmaps task

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Basic tecmaps task:

        >>> hifv_tecmaps()

    """
