import sys

from casatasks import casalog

import pipeline.h.cli.utils as utils


def hif_uvcontsub(vis=None, field=None, intent=None, spw=None, applymode=None, pipelinemode=None, dryrun=None,
                  acceptresults=None):

    """
    hif_uvcontsub ---- Subtract the fitted continuum from the data

    
    hif_uvcontsub applies the precomputed uv continuum fit tables stored in the
    pipeline context to the set of visibility files using predetermined field and
    spectral window maps and default values for the interpolation schemes.
    
    Users can interact with the pipeline calibration state using the tasks
    h_export_calstate and h_import_calstate.
    
    results -- If pipeline mode is 'getinputs' then None is returned. Otherwise
    the results object for the pipeline task is returned

    --------- parameter descriptions ---------------------------------------------

    vis           The list of input MeasurementSets. Defaults to the list of
                  MeasurementSets specified in the h_init or hif_importdata task.
                  '': use all MeasurementSets in the context
                  
                  Examples: 'ngc5921.ms', ['ngc5921a.ms', ngc5921b.ms', 'ngc5921c.ms']
    field         The list of field names or field ids for which UV continuum
                  fits are computed. Defaults to all fields.
                  Eexamples: '3C279', '3C279, M82'
    intent        A string containing a comma delimited list of intents against
                  which the selected fields are matched.
                  '': Defaults to all data with TARGET intent.
    spw           The list of spectral windows and channels for which uv
                  continuum fits are computed.
                  '', Defaults to all science spectral windows.
                  
                  Example: '11,13,15,17'
    applymode     Calibration apply mode 
                  ''='calflagstrict': calibrate data and apply flags from
                    solutions using the strict flagging convention
                  'trial': report on flags from solutions, dataset entirely
                    unchanged
                  'flagonly': apply flags from solutions only, data not
                    calibrated
                  'calonly': calibrate data only, flags from solutions NOT
                    applied
                  'calflagstrict':
                  'flagonlystrict': same as above except flag spws for which
                    calibration is unavailable in one or more tables (instead
                    of allowing them to pass uncalibrated and unflagged)
    pipelinemode  The pipeline operating mode.
                  In 'automatic' mode the pipeline determines the values of all
                  context defined pipeline inputs automatically.
                  In 'interactive' mode the user can set the pipeline context
                  defined parameters manually.
                  In 'getinputs' mode the user can check the settings of all
                  pipeline parameters without running the task.
    dryrun        Run the task (False) or just display the command (True)
    acceptresults Add the results of the task to the pipeline context (True) or
                  reject them (False).

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
