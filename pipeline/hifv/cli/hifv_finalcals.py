import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.finalcals.finalcals.FinalcalsInputs.__init__
@utils.cli_wrapper
def hifv_finalcals(vis=None, weakbp=None, refantignore=None, refant=None):

    """Compute final gain calibration tables.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Create the final calibration tables to be applied to the data in the VLA CASA pipeline:

        >>> hifv_finalcals()

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
