import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.finalcals.finalcals.FinalcalsInputs.__init__
@utils.cli_wrapper
def hifv_finalcals(vis=None, weakbp=None, refantignore=None, refant=None):
    """Compute final gain calibration tables.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Create the final calibration tables to be applied to the data in the VLA CASA pipeline:

        >>> hifv_finalcals()
    """
