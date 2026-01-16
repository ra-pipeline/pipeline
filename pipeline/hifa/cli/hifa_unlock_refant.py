import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.unlock_refant.unlock_refant.UnlockRefAntInputs.__init__
@utils.cli_wrapper
def hifa_unlock_refant(vis=None):
    """Unlock reference antenna list.

    hifa_unlock_refant marks the reference antenna list as "unlocked" for
    specified MeasurementSets, allowing the list to be modified by subsequent
    tasks.

    After executing hifa_unlock_refant, all subsequent gaincal calls will by
    default be executed with refantmode='flex'.

    The refant list can be locked with the hifa_lock_refant task.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Unlock the refant list for all MSes in pipeline context:

        >>> hifa_unlock_refant()

    """
