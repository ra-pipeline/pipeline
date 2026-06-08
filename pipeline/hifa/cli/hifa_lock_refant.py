import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.lock_refant.lock_refant.LockRefAntInputs.__init__
@utils.cli_wrapper
def hifa_lock_refant(vis=None, unregister_spwphaseup=None):
    """Lock reference antenna list.

    hifa_lock_refant marks the reference antenna list as "locked" for specified
    MeasurementSets, preventing modification of the refant list by subsequent
    tasks.

    After executing hifa_lock_refant, all subsequent gaincal calls will by
    default be executed with refantmode='strict'.

    By default, executing hifa_lock_refant will unregister any caltable
    made by any hifa_spwphaseup stage run prior to hifa_lock_refant. In
    the current Pipeline use case these are 'phase offset' caltable(s). 
    For the polarization recipe where hifa_lock_refant is used, the
    hifa_spwphaseup stage will be called again.

    The refant list can be unlocked with the hifa_unlock_refant task, but 
    the unregistered hifa_spwphaseup caltables cannot be 're' registered.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Lock the refant list for all MSes in pipeline context:

        >>> hifa_lock_refant()

    """
