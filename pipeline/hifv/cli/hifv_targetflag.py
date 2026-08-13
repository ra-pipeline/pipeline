import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.flagging.targetflag.TargetflagInputs.__init__
@utils.cli_wrapper
def hifv_targetflag(vis=None, intents=None):
    """Targetflag.

    Examples:
        1. Run rflag on both the science targets and calibrators:

        >>> hifv_targetflag()

    """
