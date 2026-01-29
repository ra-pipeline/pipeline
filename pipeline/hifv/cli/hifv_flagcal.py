import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.flagging.flagcal.FlagcalInputs.__init__
@utils.cli_wrapper
def hifv_flagcal(vis=None, caltable=None, clipminmax=None):
    """Flagcal task.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Flag existing caltable:

        >>> hifv_flagcal()
    """
