import sys

import pipeline.h.cli.utils as utils


@utils.cli_wrapper
def hifv_pbcor(vis=None, dryrun=None, acceptresults=None):

    """
    hifv_pbcor ---- Apply primary beam correction to VLA and VLASS images

    Apply primary beam correction to VLA and VLASS images

    --------- parameter descriptions ---------------------------------------------

    vis           List of input visibility data
    dryrun        Run the commands (True) or generate the commands to be run but
                  do not execute (False).  This is a pipeline task execution mode.
    acceptresults Add the results of the task to the pipeline context (True) or
                  reject them (False).  This is a pipeline task execution mode.

    --------- examples -----------------------------------------------------------

    
    Output:
    
    results -- The results object for the pipeline task is returned.
    
    
    Examples
    
    1. Basic pbcor task
    
    hifv_pbcor()


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
