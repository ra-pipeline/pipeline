import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.flagging.checkflag.CheckflagInputs.__init__
@utils.cli_wrapper
def hifv_checkflag(vis=None, checkflagmode=None, growflags=None, overwrite_modelcol=None):
    """Run RFI flagging using flagdata in various modes.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Run RFLAG with associated heuristics in the VLA CASA pipeline:

        >>> hifv_checkflag()

    """
