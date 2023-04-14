import sys

from casatasks import casalog

import pipeline.h.cli.utils as utils


def hif_makecutoutimages(vis=None, offsetblc=None, offsettrc=None, pipelinemode=None, dryrun=None, acceptresults=None):

    """
    hif_makecutoutimages ---- Cutout central 1 sq. degree from VLASS QL, SE, and Coarse Cube images

    
    Cutout central 1 sq. degree from VLASS QL, SE, and Coarse Cube images
    
    Output:
    
    results -- If pipeline mode is 'getinputs' then None is returned. Otherwise
    the results object for the pipeline task is returned.

    --------- parameter descriptions ---------------------------------------------

    vis           List of visibility data files. 
                  These may be ASDMs, tar files of ASDMs, MSs, 
                  or tar files of MSs.
                  If ASDM files are specified, they will be converted to 
                  MS format.                                                
                  (can be set only in 'interactive mode')
                  
                  example: vis=['X227.ms', 'asdms.tar.gz']
    offsetblc     -x and -y offsets to the bottom lower corner (blc) 
                  in arcseconds
                  (can be set in any pipeline mode)
    offsettrc     +x and +y offsets to the top right corner (trc) 
                  in arcseconds
                   (can be set in any pipeline mode)
    pipelinemode  The pipeline operating mode. 
                  In 'automatic' mode the pipeline determines the values 
                  of all context defined pipeline inputs automatically.  
                  In 'interactive' mode the user can set the pipeline
                  context defined parameters manually.  
                  In 'getinputs' mode the user can check the settings of 
                  all pipeline parameters without running the task.
                  (can be set in any pipeline mode)
    dryrun        Run the commands (False) or generate the commands to be 
                  run but do not execute (True).
    acceptresults Add the results of the task to the pipeline context (True)
                  or reject them (False).

    --------- examples -----------------------------------------------------------

    
    1. Basic makecutoutimages task
    
    hif_makecutoutimages()


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
