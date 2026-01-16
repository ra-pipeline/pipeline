import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.semiFinalBPdcals.semiFinalBPdcals.SemiFinalBPdcalsInputs.__init__
@utils.cli_wrapper
def hifv_semiFinalBPdcals(vis=None, weakbp=None, refantignore=None, refant=None):
    """Runs a second delay and bandpass calibration and applies to calibrators to setup for RFI flagging.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Heuristic flagging:

        >>> hifv_semiFinalBPdcals()

    """
