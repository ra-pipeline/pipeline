import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.analyzealpha.analyzealpha.AnalyzealphaInputs.__init__
@utils.cli_wrapper
def hif_analyzealpha(vis=None, image=None, alphafile=None, alphaerrorfile=None):

    """Extract spectral index from intensity peak in VLA/VLASS images

    The results object for the pipeline task is returned.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Basic analyzealpha task

        >>> hif_analyzealpha()

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
