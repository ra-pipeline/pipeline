import sys

from casatasks import casalog

import pipeline.h.cli.utils as utils


def hifv_selfcal(vis=None, pipelinemode=None, dryrun=None, acceptresults=None, refantignore=None,
                 combine=None, selfcalmode=None, refantmode=None, overwrite_modelcol=None):

    """
    hifv_selfcal ---- Perform phase-only self-calibration, per scan row, on VLASS SE images

    Perform phase-only self-calibration, per scan row, on VLASS SE images
    
    Output:
    results -- If pipeline mode is 'getinputs' then None is returned. Otherwise
    the results object for the pipeline task is returned.

    --------- parameter descriptions ---------------------------------------------

    vis                List of visibility data files. These may be ASDMs, tar files of ASDMs,
                       MSes, or tar files of MSes, If ASDM files are specified, they will be
                       converted  to MS format.
                       example: vis=['X227.ms', 'asdms.tar.gz']
    pipelinemode       The pipeline operating mode. In 'automatic' mode the pipeline
                       determines the values of all context defined pipeline inputs
                       automatically.  In 'interactive' mode the user can set the pipeline
                       context defined parameters manually.  In 'getinputs' mode the user
                       can check the settings of all pipeline parameters without running
                       the task.
    dryrun             Run the commands (True) or generate the commands to be run but
                       do not execute (False).  This is a pipeline task execution mode.
    acceptresults      Add the results of the task to the pipeline context (True) or
                       reject them (False).  This is a pipeline task execution mode.
    refantignore       String list of antennas to ignore
    combine            Data axes which to combine for solve
                       Options: '','obs','scan','spw',field', or any
                       comma-separated combination in a single string
                       
                       Example: combine='scan,spw' - Extend solutions
                       over scan boundaries (up to the solint), and
                       combine spws for solving.
                       
                       In selfcalmode='VLASS-SE' use the default value.
    selfcalmode        Heuristics mode selection. Known modes are 'VLASS' and 'VLASS-SE'.
                       Default value is 'VLASS'.
    refantmode         Reference antenna mode
    overwrite_modelcol Always write the model column, even if it already exists

    --------- examples -----------------------------------------------------------

    
    Examples
    
    1. Basic selfcal task
    
    hifv_selfcal()
    
    2. VLASS-SE selfcal usage
    
    hifv_selfcal(selfcalmode='VLASS-SE', combine='field,spw')


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