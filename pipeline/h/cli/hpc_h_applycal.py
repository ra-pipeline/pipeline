import sys

from casatasks import casalog

from . import utils


def hpc_h_applycal(vis=None, field=None, intent=None, spw=None, antenna=None, applymode=None, flagbackup=None,
                   flagsum=None, flagdetailedsum=None, pipelinemode=None, dryrun=None, acceptresults=None,
                   parallel=None):

    """
    hpc_h_applycal ---- Apply the calibration(s) to the data

    
    Apply precomputed calibrations to the data.
    
    hif_applycal applies the precomputed calibration tables stored in the pipeline
    context to the set of visibility files using predetermined field and
    spectral window maps and default values for the interpolation schemes.
    
    Users can interact with the pipeline calibration state using the tasks
    h_export_calstate and h_import_calstate.
    
    Issues
    
    There is some discussion about the appropriate values of calwt. Given
    properly scaled data, the correct value should be the CASA default of True.
    However at the current time ALMA is suggesting that calwt be set to True for
    applying observatory calibrations, e.g. antenna positions, WVR, and system
    temperature corrections, and to False for applying instrument calibrations,
    e.g. bandpass, gain, and flux.
    
    Output:
    
    results -- If pipeline mode is 'getinputs' then None is returned. Otherwise
    the results object for the pipeline task is returned
    

    --------- parameter descriptions ---------------------------------------------

    vis             The list of input MeasurementSets. Defaults to the list of MeasurementSets
                    in the pipeline context. Parameter is not available when pipelinemode='automatic'.
                    example: ['X227.ms']
    field           A string containing the list of field names or field ids to which
                    the calibration will be applied. Defaults to all fields in the pipeline
                    context. Parameter is not available when pipelinemode='automatic'.
                    example: '3C279', '3C279, M82'
    intent          A string containing the list of intents against which the
                    selected fields will be matched. Defaults to all supported intents
                    in the pipeline context. Parameter is not available when pipelinemode='automatic'.
                    example: '*TARGET*'
    spw             The list of spectral windows and channels to which the calibration
                    will be applied. Defaults to all science windows in the pipeline
                    context. Parameter is not available when pipelinemode='automatic'.
                    example: '17', '11, 15'
    antenna         The list of antennas to which the calibration will be applied.
                    Defaults to all antennas. Not currently supported.
                    Parameter is not available when pipelinemode='automatic'.
    applymode       Calibration apply mode
                    ''='calflagstrict': calibrate data and apply flags from solutions using
                        the strict flagging convention
                    'trial': report on flags from solutions, dataset entirely unchanged
                    'flagonly': apply flags from solutions only, data not calibrated
                    'calonly': calibrate data only, flags from solutions NOT applied
                    'calflagstrict':
                    'flagonlystrict':same as above except flag spws for which calibration is
                        unavailable in one or more tables (instead of allowing them to pass
                        uncalibrated and unflagged)
    flagbackup      Backup the flags before the apply
    flagsum         Compute before and after flagging summary statistics
    flagdetailedsum Compute detailed before and after flagging statistics summaries.
                    Parameter available only when if flagsum is True.
    pipelinemode    The pipeline operating mode. In 'automatic' mode the pipeline
                    determines the values of all context defined pipeline inputs automatically.
                    In interactive mode the user can set the pipeline context defined parameters
                    manually.  In 'getinputs' mode the user can check the settings of all
                    pipeline parameters without running the task.
    dryrun          Run task (False) or display the command(True).
                    Parameter is available only when pipelinemode='interactive'.
    acceptresults   Add the results of the task to the pipeline context (True) or
                    reject them (False). Parameter is available only when pipelinemode='interactive'.
    parallel        Execute using CASA HPC functionality, if available.

    --------- examples -----------------------------------------------------------

    
    1. Apply the calibration to the target data
    
    h_session_applycal(intent='TARGET')
    


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
