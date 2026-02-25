import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.transformimagedata.transformimagedata.TransformimagedataInputs.__init__
@utils.cli_wrapper
def hif_transformimagedata(vis=None, outputvis=None, field=None, intent=None, spw=None, datacolumn=None, chanbin=None,
                           timebin=None, replace=None, clear_pointing=None, modify_weights=None, wtmode=None):
    """Extract fields for the desired VLASS image to a new MS and reset weights if desired.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Basic transformimagedata task

        >>> hif_transformimagedata()

    """
