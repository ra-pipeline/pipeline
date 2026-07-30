import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.flagging.flagtargetsalma.FlagTargetsALMAInputs.__init__
@utils.cli_wrapper
def hifa_flagtargets(vis=None, template=None, filetemplate=None, flagbackup=None, parallel=None):
    """Apply observatory-scientist flagging templates to science target data.

    Applies custom flagging commands to the science target MeasurementSets if determined to be
    necessary by an observatory scientist. The commands are read from the ``flagtargetstemplate.txt``
    files linked from the WebLog page. The WebLog also displays a summary table of any flagging
    performed, including the number and fraction of data flagged per antenna, spw, and intent.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Apply the science target flagging template:

        >>> hifa_flagtargets()

    """
