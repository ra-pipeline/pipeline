import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.flagging.flagcal.FlagcalInputs.__init__
@utils.cli_wrapper
def hifv_flagcal(vis=None, caltable=None, clipminmax=None):
    """Flagcal task.

    Examples:
        1. Flag existing caltable:

        >>> hifv_flagcal()
    """
