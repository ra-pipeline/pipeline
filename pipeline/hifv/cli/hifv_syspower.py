import sys

from casatasks import casalog

import pipeline.h.cli.utils as utils


def hifv_syspower(vis=None, clip_sp_template=None, antexclude=None, usemedian=None, apply=None,
                  pipelinemode=None, dryrun=None, acceptresults=None):

    """
    hifv_syspower ---- Determine amount of gain compression affecting VLA data below Ku-band

    --------- parameter descriptions ---------------------------------------------

    vis              List of input visibility data
    clip_sp_template Acceptable range for Pdiff data; data are clipped outside this range and flagged
    antexclude       csv string list of antennas to exclude
    usemedian        If antexclude is specified with usemedian=False, the template values are replaced with 1.0.
                     If usemedian = True, the template values are replaced with the median of the good antennas.
    apply            Apply task results to RQ table
    pipelinemode     The pipeline operating mode. In 'automatic' mode the pipeline
                     determines the values of all context defined pipeline inputs
                     automatically.  In 'interactive' mode the user can set the pipeline
                     context defined parameters manually.  In 'getinputs' mode the user
                     can check the settings of all pipeline parameters without running
                     the task.
    dryrun           Run the commands (True) or generate the commands to be run but
                     do not execute (False).  This is a pipeline task execution mode.
    acceptresults    Add the results of the task to the pipeline context (True) or
                     reject them (False).  This is a pipeline task execution mode.

    --------- examples -----------------------------------------------------------

    
    Output:
    
    results -- If pipeline mode is 'getinputs' then None is returned. Otherwise
    the results object for the pipeline task is returned.
    
    
    Examples
    
    1. Basic syspower task
    
    hifv_syspower()


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
