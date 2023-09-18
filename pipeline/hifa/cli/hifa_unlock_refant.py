import sys

import pipeline.h.cli.utils as utils


@utils.cli_wrapper
def hifa_unlock_refant(vis=None, dryrun=None, acceptresults=None):

    """
    hifa_unlock_refant ---- Unlock reference antenna list

    hifa_unlock_refant unlocks the reference antenna list, allowing the list to
    be modified by subsequent tasks. After hifa_unlock_refant, the default
    gaincal refantmode reverts to 'flex'.

    --------- parameter descriptions ---------------------------------------------

    vis           List of input MeasurementSets. Defaults to the list of
                  MeasurementSets specified in the pipeline context.
                  
                  Example: vis=['ngc5921.ms']
    dryrun        Run the task (False) or display task command (True)
    acceptresults Add the results into the pipeline context

    --------- examples -----------------------------------------------------------

    


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
