import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.pbcor.pbcor.PbcorInputs.__init__
@utils.cli_wrapper
def hifv_pbcor(vis=None):
    """Apply primary beam correction to VLA and VLASS images.

    Examples:
        1. Basic pbcor task:

        >>> hifv_pbcor()

    """
