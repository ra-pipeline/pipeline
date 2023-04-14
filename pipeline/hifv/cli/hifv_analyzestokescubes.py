import sys

from casatasks import casalog

import pipeline.h.cli.utils as utils


def hifv_analyzestokescubes(vis=None, pipelinemode=None, dryrun=None, acceptresults=None):

    """
    hifv_analyzestokescubes ---- Characterize stokes IQUV flux densities as a function of frequency for VLASS coarse cube images

    Characterize stokes IQUV flux densities as a function of frequency for VLASS coarse cube images

    --------- parameter descriptions ---------------------------------------------

    vis           List of input visibility data
    pipelinemode  The pipeline operating mode
    dryrun        Run the task (False) or display task command (True)
    acceptresults Add the results into the pipeline context
    [1;42mRETURNS[1;m          void

    --------- examples -----------------------------------------------------------

    
    The hifv_analyzestokescubes task
    
    Keyword arguments:
    
    ---- pipeline parameter arguments which can be set in any pipeline mode
    
    vis -- List of visisbility  data files. These may be ASDMs, tar files of ASDMs,
    MSs, or tar files of MSs, If ASDM files are specified, they will be
    converted  to MS format.
    default: []
    example: vis=['X227.ms', 'asdms.tar.gz']
    
    
    
    pipelinemode -- The pipeline operating mode. In 'automatic' mode the pipeline
    determines the values of all context defined pipeline inputs
    automatically.  In 'interactive' mode the user can set the pipeline
    context defined parameters manually.  In 'getinputs' mode the user
    can check the settings of all pipeline parameters without running
    the task.
    default: 'automatic'.
    
    ---- pipeline context defined parameter argument which can be set only in
    'interactive mode'
    
    
    --- pipeline task execution modes
    
    dryrun -- Run the commands (True) or generate the commands to be run but
    do not execute (False).
    default: True
    
    acceptresults -- Add the results of the task to the pipeline context (True) or
    reject them (False).
    default: True
    
    Output:
    
    results -- If pipeline mode is 'getinputs' then None is returned. Otherwise
    the results object for the pipeline task is returned.
    
    
    Examples
    
    1. Basic analyzestokescubes task
    
    hifv_analyzestokescubes()


    """


    #                                                                        #
    #  CASA task interface boilerplate code starts here. No edits should be  #
    #  needed beyond this point.                                             #
    #                                                                        #

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