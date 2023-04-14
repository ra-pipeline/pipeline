import sys

from casatasks import casalog

import pipeline.h.cli.utils as utils


def hifa_fluxcalflag(vis=None, field=None, intent=None, spw=None, pipelinemode=None, threshold=None, appendlines=None,
                     linesfiles=None, applyflags=None, dryrun=None, acceptresults=None):

    """
    hifa_fluxcalflag ---- Locate and flag line regions in solar system flux calibrators

    
    Search the built-in solar system flux calibrator line catalog for overlaps with
    the science spectral windows. Generate a list of line overlap regions and
    flagging commands.
    
    
    Output
    
    results -- If pipeline mode is 'getinputs' then None is returned. Otherwise
    the results object for the pipeline task is returned.

    --------- parameter descriptions ---------------------------------------------

    vis           The list of input MeasurementSets. Defaults to the list of
                  MeasurementSets defined in the pipeline context.
    field         The list of field names or field ids for which the models are
                  to be set. Defaults to all fields with intent 'AMPLITUDE'.
                  
                  example: field='3C279', field='3C279, M82'
    intent        A string containing a comma delimited list of intents against
                  which the selected fields are matched. Defaults to all data
                  with amplitude intent.
                  
                  example: intent='AMPLITUDE'
    spw           spectral windows and channels for which bandpasses are
                  computed. Defaults to all science spectral windows.
                  
                  example: spw='11,13,15,17'
    pipelinemode  The pipeline operating mode. In 'automatic' mode the pipeline
                  determines the values of all context defined pipeline inputs automatically.
                  In interactive mode the user can set the pipeline context defined
                  parameters manually. In 'getinputs' mode the user can check the settings of
                  all pipeline parameters without running the task.
    threshold     If the fraction of an spw occupied by line regions is greater
                  than threshold flag the entire spectral window.
    appendlines   Append user defined line regions to the line dictionary.
    linesfile     
    applyflags    
    dryrun        Run the commands (True) or generate the commands to be run but
                  do not execute (False).
    acceptresults Add the results of the task to the pipeline context (True) or
                  reject them (False).

    --------- examples -----------------------------------------------------------

    
    1. Locate known lines in any solar system object flux calibrators:
    
    hifa_fluxcalflag()


    """


    ##########################################################################
    #                                                                        #
    #  CASA task interface boilerplate code starts here. No edits should be  #
    #  needed beyond this point.                                             #
    #                                                                        #
    ##########################################################################

    # create a dictionary containing all the arguments given in the
    # constructor
    all_inputs = vars()

    # get the name of this function for the weblog, eg. 'hif_flagdata'
    task_name = sys._getframe().f_code.co_name

    # get the context on which this task operates
    context = utils.get_context()

    # execute the task
    results = utils.execute_task(context, task_name, all_inputs)

    return results
