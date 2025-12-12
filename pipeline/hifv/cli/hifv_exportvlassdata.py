import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.exportvlassdata.exportvlassdata.ExportvlassdataInputs.__init__
@utils.cli_wrapper
def hifv_exportvlassdata(vis=None):
    """Export Image data from QL, SE, and Coarse Cube modes of VLASS Survey.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Basic exportvlassdata task:

        >>> hifv_exportvlassdata()

    """
