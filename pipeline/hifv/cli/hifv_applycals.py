import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.finalcals.applycals.ApplycalsInputs.__init__
@utils.cli_wrapper
def hifv_applycals(vis=None, field=None, intent=None, spw=None, antenna=None, applymode=None, flagbackup=None,
                   flagsum=None, flagdetailedsum=None, gainmap=None):

    """Apply calibration tables to input MeasurementSets.

    hifv_applycals applies the precomputed calibration tables stored in the pipeline
    context to the set of visibility files using predetermined field and
    spectral window maps and default values for the interpolation schemes.

    Users can interact with the pipeline calibration state using the tasks
    h_export_calstate and h_import_calstate.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Run the final applycals stage of the VLA CASA pipeline:

        >>> hifv_applycals()

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
