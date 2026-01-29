import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.testBPdcals.testBPdcals.testBPdcalsInputs.__init__
@utils.cli_wrapper
def hifv_testBPdcals(vis=None, weakbp=None, refantignore=None, doflagundernspwlimit=None, flagbaddef=None, iglist=None, refant=None):
    """Runs initial delay and bandpass calibration to setup for RFI flagging.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Initial delay calibration to set up heuristic flagging:

        >>> hifv_testBPdcals()
    """
