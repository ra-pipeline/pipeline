import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.flagging.flagtargetsalma.FlagTargetsALMAInputs.__init__
@utils.cli_wrapper
def hifa_flagtargets(vis=None, template=None, filetemplate=None, flagbackup=None, parallel=None):
    """Do science target flagging.

    The hifa_flagtargets task performs basic flagging operations on a list of
    science target MeasurementSets, including:

    - applying a flagging template

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Do basic flagging on a science target MeasurementSet:

        >>> hifa_flagtargets()

    """
