import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.launcher as launcher

from . import cli, utils


@utils.cli_wrapper
def h_init(loglevel='info', plotlevel='default', weblog=True, processing_intents=None):
    """Initialize the pipeline state and context.

    `h_init`  must be called before any other pipeline task. The pipeline
    can be initialized in one of two ways: by creating a new pipeline
    state (`h_init`) or be loading a saved pipeline state (`h_resume`).

    `h_init` creates an empty pipeline context but does not load visibility data
    into the context. Any of the pipeline `h*_importdata` tasks can be used to load data.

    Args:
        loglevel: Log level for pipeline messages. Log messages below this threshold will not be displayed.

        plotlevel: Toggle generation of detail plots in the web log. A level of 'all' generates all plots;
            'summary' omits detail plots; 'default' generates all plots apart from for the hif_applycal task.

        weblog: Generate the web log

        processing_intents: Dictionary of processing intents for the current pipeline run.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Create the pipeline context

        >>> h_init()

    """
    # Create the pipeline and store the Pipeline object in the stack
    pipeline = launcher.Pipeline(loglevel=loglevel, plotlevel=plotlevel, processing_intents=processing_intents)
    cli.stack[cli.PIPELINE_NAME] = pipeline

    basetask.DISABLE_WEBLOG = not weblog

    return pipeline.context
