import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.lock_refant.lock_refant.LockRefAntInputs.__init__
@utils.cli_wrapper
def hifa_lock_refant(vis=None):
    """Lock reference antenna list.

    hifa_lock_refant marks the reference antenna list as "locked" for specified
    MeasurementSets, preventing modification of the refant list by subsequent
    tasks.

    After executing hifa_lock_refant, all subsequent gaincal calls will by
    default be executed with refantmode='strict'.

    The refant list can be unlocked with the hifa_unlock_refant task.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Lock the refant list for all MSes in pipeline context:

        >>> hifa_lock_refant()

    """
