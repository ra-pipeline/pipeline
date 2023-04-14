import sys

from casatasks import casalog

import pipeline.h.cli.utils as utils


def hifv_vlassmasking(vis=None, vlass_ql_database=None, maskingmode=None, catalog_search_size=None,
                      pipelinemode=None, dryrun=None, acceptresults=None):

    """
    hifv_vlassmasking ---- Create clean masks for VLASS SE images

    Create clean masks for VLASS SE images

    --------- parameter descriptions ---------------------------------------------

    vis                 List of visibility data files. These may be ASDMs, tar files of ASDMs,
                        MSes, or tar files of MSes, If ASDM files are specified, they will be
                        converted  to MS format.
                        example: vis=['X227.ms', 'asdms.tar.gz']
    vlass_ql_database   vlass_ql_database - usage in Socorro: /home/vlass/packages/VLASS1Q.fits
    maskingmode         maskingmode options are vlass-se-tier-1 or vlass-se-tier-2
    catalog_search_size catalog_search_size in units of degrees
    pipelinemode        The pipeline operating mode. In 'automatic' mode the pipeline
                        determines the values of all context defined pipeline inputs
                        automatically.  In 'interactive' mode the user can set the pipeline
                        context defined parameters manually.  In 'getinputs' mode the user
                        can check the settings of all pipeline parameters without running
                        the task.
    dryrun              Run the commands (True) or generate the commands to be run but
                        do not execute (False).  This is a pipeline task execution mode.
    acceptresults       Add the results of the task to the pipeline context (True) or
                        reject them (False).  This is a pipeline task execution mode.

    --------- examples -----------------------------------------------------------

    
    The hifv_vlassmasking task
    
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
    
    1. Basic vlassmasking task
    
    hifv_vlassmasking()


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
