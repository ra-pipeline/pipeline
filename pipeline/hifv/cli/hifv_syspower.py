import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.syspower.syspower.SyspowerInputs.__init__
@utils.cli_wrapper
def hifv_syspower(vis=None, clip_sp_template=None, antexclude=None, apply=None, do_not_apply=None):
    """Determine amount of gain compression affecting VLA data below Ku-band.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Basic syspower task:

        >>> hifv_syspower()

    """
