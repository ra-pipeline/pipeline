import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.makecutoutimages.makecutoutimages.MakecutoutimagesInputs.__init__
@utils.cli_wrapper
def hif_makecutoutimages(vis=None, offsetblc=None, offsettrc=None):
    """Cutout central 1 sq. degree from VLASS QL, SE, and Coarse Cube images.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Basic makecutoutimages task

        >>> hif_makecutoutimages()
    """
