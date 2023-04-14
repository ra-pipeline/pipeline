from casatasks import casalog

from pipeline import show_weblog


def h_weblog(pipelinemode=None, relpath=None):

    """
    h_weblog ---- Open the pipeline weblog in a browser

    h_weblog opens the weblog in a new browser tab or window.

    --------- parameter descriptions ---------------------------------------------

    pipelinemode The pipeline operating mode. In 'automatic' mode the pipeline
                 determines the values of all context defined pipeline inputs
                 automatically. In 'interactive' mode the user can set the pipeline
                 context defined parameters manually. In 'getinputs' mode the user
                 can check the settings of all pipeline parameters without running
                 the task.
    relpath      Relative path to the weblog index file. This file must be located
                 in a child directory of the CASA working directory. If relpath
                 is left unspecified, the most recent weblog will be located and
                 displayed.
    --------- examples -----------------------------------------------------------

    """

    show_weblog(index_path=relpath)
