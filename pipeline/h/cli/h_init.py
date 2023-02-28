from casatasks import casalog

from . import cli
import pipeline.infrastructure.launcher as launcher
import pipeline.infrastructure.basetask as basetask


def h_init(pipelinemode='automatic', loglevel='info', plotlevel='default', weblog=True, overwrite=True, dryrun=False,
           acceptresults=True):

    """
    h_init ---- Initialize the interferometry pipeline

    
    The h_init task initializes the interferometry pipeline and optionally
    imports data.
    
    h_init  must be called before any other interferometry pipeline task. The
    pipeline can be initialized in one of two ways: by creating a new pipeline
    state (h_init) or be loading a saved pipeline state (h_resume).
    
    h_init creates an empty pipeline context but does not load visibility data
    into the context. hif_importdata or hsd_importdata can be used to load data.
    
    If pipeline mode is 'getinputs' then None is returned. Otherwise
    the results object for the pipeline task is returned.

    --------- parameter descriptions ---------------------------------------------

    pipelinemode  The pipeline operating mode. In 'automatic' mode the pipeline determines the values of all context defined pipeline inputs automatically.  In interactive mode the user can set the pipeline context defined parameters manually.  In 'getinputs' mode the user can check the settings of all pipeline parameters without running the task.
    loglevel      Log level for pipeline messages. Log messages below this threshold will not be displayed.
    plotlevel     Toggle generation of detail plots in the web log. A level of 'all' generates 
                  					 all plots; 'summary' omits detail plots; 'default' generates all plots 
                  					 apart from for the hif_applycal task.
    weblog        Generate the web log
    overwrite     Overwrite existing files on import
    dryrun        Run the task (False) or display the task command (True)
    acceptresults Add the results into the pipeline context

    --------- examples -----------------------------------------------------------

    
    Examples
    
    1. Create the pipeline context
    
    h_init()


    """

    # TBD: DECIDE WHETHER DRY RUN REALLY MAKES SENSE FOR THIS TASK AND IF
    # SO HOW TO IMPLEMENT IT.

    # TBD: CASA PARAMETER CHECKS BEFORE CREATING A CONTEXT ?

    # Create the pipeline and store the Pipeline object in the stack
    pipeline = launcher.Pipeline(loglevel=loglevel, plotlevel=plotlevel)
    cli.stack[cli.PIPELINE_NAME] = pipeline

    basetask.DISABLE_WEBLOG = not weblog

    return pipeline.context
