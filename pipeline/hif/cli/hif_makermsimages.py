import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.makermsimages.makermsimages.MakermsimagesInputs.__init__
@utils.cli_wrapper
def hif_makermsimages(vis=None):
    """Create RMS images for VLASS data.

    Examples:
        1. Basic makermsimages task

        >>> hif_makermsimages()

    """
