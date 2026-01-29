import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.selfcal.selfcal.SelfcalInputs.__init__
@utils.cli_wrapper
def hifv_selfcal(vis=None, refantignore=None,
                 combine=None, selfcalmode=None, refantmode=None, overwrite_modelcol=None):
    """Perform phase-only self-calibration, per scan row, on VLASS SE images.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Basic selfcal task:

        >>> hifv_selfcal()

        2. VLASS-SE selfcal usage:

        >>> hifv_selfcal(selfcalmode='VLASS-SE', combine='field, spw')

    """
