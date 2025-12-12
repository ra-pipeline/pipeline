import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.flagging.flagtargetsdata.FlagtargetsdataInputs.__init__
@utils.cli_wrapper
def hifv_flagtargetsdata(vis=None, template=None, filetemplate=None, flagbackup=None):
    """Apply a flagtemplate to target data prior to running imaging pipeline tasks.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Basic flagtargetsdata task:

        >>> hifv_flagtargetsdata()

    """
