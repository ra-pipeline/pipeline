import sys

import pipeline.h.cli.utils as utils


@utils.cli_wrapper
def hifv_finalcals(vis=None, dryrun=None, acceptresults=None, weakbp=None, refantignore=None):

    """
    hifv_finalcals ---- Compute final gain calibration tables

    Compute final gain calibration tables

    --------- parameter descriptions ---------------------------------------------

    vis           List of visibility data files. These may be ASDMs, tar files of ASDMs,
                  MSes, or tar files of MSes, If ASDM files are specified, they will be
                  converted  to MS format.
                  example: vis=['X227.ms', 'asdms.tar.gz']
    dryrun        Run the commands (True) or generate the commands to be run but
                  do not execute (False).  This is a pipeline task execution mode.
    acceptresults Add the results of the task to the pipeline context (True) or
                  reject them (False).  This is a pipeline task execution mode.
    weakbp        Activate weak bandpass heuristics
    refantignore  String list of antennas to ignore

    --------- examples -----------------------------------------------------------

    
    Output:
    
    results -- The results object for the pipeline task is returned.
    
    
    Examples
    
    1. Create the final calibration tables to be applied to the data in the VLA CASA pipeline.
    
    hifv_finalcals()


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
