import pipeline.h.cli.utils as utils


@utils.cli_wrapper
def hif_analyzealpha(image=None, alphafile=None, alphaerrorfile=None):
    """Extract spectral index from intensity peak in VLASS images.


    Examples:
        1. Basic analyzealpha task

        >>> hif_analyzealpha()
    """
