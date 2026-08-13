import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.plotsummary.plotsummary.PlotSummaryInputs.__init__
@utils.cli_wrapper
def hifv_plotsummary(vis=None):
    """Create pipeline summary plots.

    Examples:
        1. Execute the pipeline plotting task:

        >>> hifv_plotsummary()

    """
