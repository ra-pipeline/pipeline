import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.polcalflag.polcalflag.PolcalflagInputs.__init__
@utils.cli_wrapper
def hifa_polcalflag(vis=None):
    """Flag polarization calibrators

    This task flags corrected visibility outliers in the polarization calibrator
    data using the hif_correctedampflag heuristics.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Run with recommended settings to flag visibility outliers in the
        polarization calibrator data:

        >>> hifa_polcalflag()

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
