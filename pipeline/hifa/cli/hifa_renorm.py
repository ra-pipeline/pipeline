import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.renorm.renorm.RenormInputs.__init__
@utils.cli_wrapper
def hifa_renorm(vis=None, createcaltable=None, threshold=None, spw=None, excludechan=None,
                atm_auto_exclude=None, bwthreshspw=None, parallel=None):
    """ALMA renormalization.

    This task makes an assessment, and optionally applies a correction, to data
    suffering from incorrect amplitude normalization caused by bright
    astronomical lines detected in the autocorrelations of some target sources.

    For a full description of the effects of bright emission lines and the
    correction heuristics used in this task, please see the Pipeline User Guide.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Run with recommended settings to assess the need for an ALMA amplitude
        renormalization correction.

        >>> hifa_renorm()

        2. Run to assess the necessary ALMA amplitude renormalization correction,
        and apply this correction if it exceeds a threshold of 3% (1.03).

        >>> hifa_renorm(createcaltable=True, threshold=1.03)

    """
