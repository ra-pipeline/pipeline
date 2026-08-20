import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.lock_refant.lock_refant.LockRefAntInputs.__init__
@utils.cli_wrapper
def hifa_lock_refant(vis=None, unregister_spwphaseup=None):
    """Lock the reference antenna to a single antenna with ``refantmode='fixed'``.

    Sets the reference antenna to a single antenna and sets ``refantmode='fixed'`` for all subsequent
    calibration tasks, preventing any subsequent modification of the refant list.

    In the polarization (polcal and polcalimage) recipes, :func:`~pipeline.hifa.cli.hifa_bandpass` and :func:`~pipeline.hifa.cli.hifa_spwphaseup` are each
    called a second time after this stage to ensure those calibration tables are computed using the fixed
    reference antenna.

    By default, executing :func:`~pipeline.hifa.cli.hifa_lock_refant` will unregister any caltable made by any :func:`~pipeline.hifa.cli.hifa_spwphaseup`
    stage run prior to :func:`~pipeline.hifa.cli.hifa_lock_refant`. The unregistered :func:`~pipeline.hifa.cli.hifa_spwphaseup` caltables cannot be
    're-registered'. In the current Pipeline use case, these are 'phase offset' caltable(s). For the
    polarization recipe where :func:`~pipeline.hifa.cli.hifa_lock_refant` is used, the :func:`~pipeline.hifa.cli.hifa_spwphaseup` stage will be called
    again.

    The refant list can be unlocked with the :func:`~pipeline.hifa.cli.hifa_unlock_refant` task, although that is not needed in
    the standard polcal and polcalimage recipes.

    Notes:
        Only used in polarization recipes.

    Examples:
        1. Lock the refant list for all MSes in pipeline context:

           >>> hifa_lock_refant()

    """
