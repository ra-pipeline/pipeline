import sys

import pipeline.h.cli.utils as utils


def hifa_lock_refant(vis=None, dryrun=None, acceptresults=None):

    """
    hifa_lock_refant ---- Lock reference antenna list

    hifa_lock_refant locks the reference antenna list, preventing
    modification of the refant list by subsequent tasks. After
    executing hifa_lock_refant, the default gaincal refantmode is
    set to 'strict'.

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
