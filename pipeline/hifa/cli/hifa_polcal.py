import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.polcal.polcal.PolcalInputs.__init__
def hifa_polcal(vis=None, minpacov=None, solint_chavg=None, vs_stats=None, vs_thresh=None):
    """Derive instrumental polarization calibration for ALMA.

    Derive the instrumental polarization calibrations for ALMA using the
    polarization calibrators.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Compute the polarization calibrations:

        >>> hifa_polcal()

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
