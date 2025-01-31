import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hsd.tasks.k2jycal.k2jycal.SDK2JyCalInputs.__init__
@utils.cli_wrapper
def hsd_k2jycal(dbservice=None, endpoint=None, reffile=None,
                infiles=None, caltable=None):

    """Derive Kelvin to Jy calibration tables.

    Derive the Kelvin to Jy calibration for list of MeasurementSets.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Compute the Kevin to Jy calibration tables for a list of MeasurementSets:

        >>> hsd_k2jycal()

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
