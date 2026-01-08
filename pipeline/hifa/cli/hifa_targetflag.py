import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.targetflag.targetflag.TargetflagInputs.__init__
@utils.cli_wrapper
def hifa_targetflag(vis=None, parallel=None):
    """Flag target source outliers.

    This task flags obvious outliers in the target source data. The calibration tables and
    flags accumulated in the cal library up to this point are pre-applied, then
    hif_correctedampflag is called for just the TARGET intent. Any resulting
    flags are applied and the calibration library is restored to the state before
    calling this task.

    Because science targets are generally not point sources, the flagging algorithm
    needs to be more clever than for point source calibrators. The algorithm identifies
    outliers by examining statistics within successive overlapping radial uv bins,
    allowing it to adapt to an arbitrary uv structure. Outliers must appear to be a
    potential outlier in two bins in order to be declared an outlier.  To further avoid
    overflagging of good data, only the highest threshold levels are used (+12/-13 sigma).
    This stage does can add significant processing time, particularly in making the plots.
    So to save time, the amp vs. time plots are created only if flags are generated, and
    the amp vs. uv distance plots are made for only those spws that generated flags.
    Also, to avoid confusion in mosaics and single field surveys, the amp vs. uv distance
    plots only show field IDs with new flags.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Run with recommended settings to flag outliers in science target(s):

        >>> hifa_targetflag()

    """
