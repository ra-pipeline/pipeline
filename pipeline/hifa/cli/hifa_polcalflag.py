import sys

import pipeline.h.cli.utils as utils


def hifa_polcalflag(vis=None, pipelinemode=None, dryrun=None, acceptresults=None):

    """
    hifa_polcalflag ---- Flag polarization calibrators

    
    This task flags corrected visibility outliers in the polarization calibrator
    data using the hif_correctedampflag heuristics.

    --------- parameter descriptions ---------------------------------------------

    vis           The list of input MeasurementSets. Defaults to the list of
                  MeasurementSets specified in the h_init or hif_importdata task.
                  '': use all MeasurementSets in the context
                  
                  Examples: 'ngc5921.ms', ['ngc5921a.ms', ngc5921b.ms', 'ngc5921c.ms']
    pipelinemode  The pipeline operating mode.
                  In 'automatic' mode the pipeline determines the values of all
                  context defined pipeline inputs automatically.
                  In 'interactive' mode the user can set the pipeline context
                  defined parameters manually.
                  In 'getinputs' mode the user can check the settings of all
                  pipeline parameters without running the task.
    dryrun        Run the task (False) or display task command (True)
    acceptresults Add the results of the task to the pipeline context (True) or
                  reject them (False).

    --------- examples -----------------------------------------------------------

    


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
