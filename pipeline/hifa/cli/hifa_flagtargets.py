import sys

from casatasks import casalog

import pipeline.h.cli.utils as utils


def hifa_flagtargets(vis=None, template=None, filetemplate=None, pipelinemode=None, flagbackup=None, dryrun=None,
                     acceptresults=None):

    """
    hifa_flagtargets ---- Do science target flagging

    
    The hifa_flagtargets task performs basic flagging operations on a list of
    science target MeasurementSets.
    
    Output
    
    results -- If pipeline mode is 'getinputs' then None is returned. Otherwise
    the results object for the pipeline task is returned.
    
    
    Description
    
    The hifa_flagtargets task performs basic flagging operations on a list of
    measurements including:
    
    o applying a flagging template
    
    
    Issues

    --------- parameter descriptions ---------------------------------------------

    vis           The list of input MeasurementSets. Defaults to the list 
                  of MeasurementSets defined in the pipeline context.
                  (can be set only in 'interactive mode')
    template      Apply flagging templates.
                  (can be set in any pipeline mode)
    filetemplate  The name of a text file that contains the flagging 
                  template for issues with the science target data etc. 
                  If the template flags files is undefined a name of the 
                  form 'msname_flagtargetstemplate.txt' is assumed.
                  (can be set in any pipeline mode)
    pipelinemode  The pipeline operating mode. 
                  In 'automatic' mode the pipeline determines the values
                  of all context defined pipeline inputs automatically. 
                  In interactive mode the user can set the pipeline 
                  context defined parameters manually. 
                  In 'getinputs' mode the user can check the settings of
                  all pipeline parameters without running the task.
    flagbackup    Back up any pre-existing flags.
                  (can be set only in 'interactive mode')
    dryrun        Run the commands (False) or generate the commands to be 
                  run but do not execute (True).
    acceptresults Add the results of the task to the pipeline context (True)
                  or reject them (False).

    --------- examples -----------------------------------------------------------

    
    1. Do basic flagging on a science target MeasurementSet:
    
    hifa_flagtargets()


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
