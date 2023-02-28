import sys

from . import utils


def h_tsyscal(vis=None, caltable=None, chantol=None, pipelinemode=None,
    dryrun=None, acceptresults=None):

    """
    h_tsyscal ---- Derive a Tsys calibration table

    
    Derive the Tsys calibration for list of ALMA MeasurementSets.
    
    Issues
    
    
    Output:
    
    results -- If pipeline mode is 'getinputs' then None is returned. Otherwise
    the results object for the pipeline task is returned.

    --------- parameter descriptions ---------------------------------------------

    vis           List of input visibility files.
                  Parameter is not available when pipelinemode='automatic'.
                  example: vis=['ngc5921.ms']
    caltable      Name of output gain calibration tables.
                  Parameter is not available when pipelinemode='automatic'.
                  example: caltable='ngc5921.gcal'
    chantol       The tolerance in channels for mapping atmospheric calibration
                  windows (TDM) to science windows (FDM or TDM).
                  example: chantol=5
    pipelinemode  The pipeline operating mode. In 'automatic' mode the pipeline
                  determines the values of all context defined pipeline inputs automatically.
                  In interactive mode the user can set the pipeline context defined
                  parameters manually. In 'getinputs' mode the user can check the settings of
                  all pipeline parameters without running the task.
    dryrun        Run the task (False) or list commands (True).
                  Parameter is available only when pipelinemode='interactive'.
    acceptresults Add the results of the task to the pipeline context (True) or
                  Parameter is available only when pipelinemode='interactive'.

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
