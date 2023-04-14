import sys

from casatasks import casalog

import pipeline.h.cli.utils as utils


def hifv_testBPdcals(vis=None, pipelinemode=None, dryrun=None, acceptresults=None, weakbp=None, refantignore=None, doflagundernspwlimit=None):

    """
    hifv_testBPdcals ---- Runs initial delay and bandpass calibration to setup for RFI flagging

    --------- parameter descriptions ---------------------------------------------

    vis                  List of visibility data files. These may be ASDMs, tar files of ASDMs,
                         MSes, or tar files of MSes, If ASDM files are specified, they will be
                         converted  to MS format.
                         example: vis=['X227.ms', 'asdms.tar.gz']
    pipelinemode         The pipeline operating mode. In 'automatic' mode the pipeline
                         determines the values of all context defined pipeline inputs
                         automatically.  In 'interactive' mode the user can set the pipeline
                         context defined parameters manually.  In 'getinputs' mode the user
                         can check the settings of all pipeline parameters without running
                         the task.
    dryrun               Run the commands (True) or generate the commands to be run but
                         do not execute (False).  This is a pipeline task execution mode.
    acceptresults        Add the results of the task to the pipeline context (True) or
                         reject them (False).  This is a pipeline task execution mode.
    weakbp               Activate weak bandpass heuristics
    refantignore         String list of antennas to ignore
                         Example:  refantignore='ea02,ea03'
    doflagundernspwlimit If the number of bad spws is greater than zero, and the keyword is True, then spws are flagged individually.

    --------- examples -----------------------------------------------------------

    
    
    Output:
    
    results -- If pipeline mode is 'getinputs' then None is returned. Otherwise
    the results object for the pipeline task is returned.
    
    
    Examples
    
    1. Initial delay calibration to set up heuristic flagging.
    
    hifv_testBPdcals()


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
