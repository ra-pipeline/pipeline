import sys

import pipeline.h.cli.utils as utils


@utils.cli_wrapper
def hifv_hanning(vis=None, dryrun=None, acceptresults=None):

    """
    hifv_hanning ---- Hanning smoothing on a dataset

    The hifv_hanning task will hanning smooth a VLA dataset

    --------- parameter descriptions ---------------------------------------------

    vis           List of visibility data files. These may be ASDMs, tar files of ASDMs,
                  MSs, or tar files of MSs, If ASDM files are specified, they will be
                  converted  to MS format.
                  example: vis=['X227.ms', 'asdms.tar.gz']
    dryrun        Run the commands (True) or generate the commands to be run but
                  do not execute (False).  This is a pipeline task execution mode.
    acceptresults Add the results of the task to the pipeline context (True) or
                  reject them (False).  This is a pipeline task execution mode.

    --------- examples -----------------------------------------------------------

    
    
    Output:
    
    results -- The results object for the pipeline task is returned.
    
    
    Examples
    
    1. Run the task to execute hanning smoothing on a VLA CASA pipeline loaded MeasurementSet.
    
    hifv_hanning()


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
