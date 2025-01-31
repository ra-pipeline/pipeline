import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.fluxscale.solint.SolintInputs.__init__
@utils.cli_wrapper
def hifv_solint(vis=None, limit_short_solint=None, refantignore=None, refant=None):

    """Determines different solution intervals.

    The hifv_solint task determines different solution intervals. Note that the short solint value is switched to 'int' when
    the minimum solution interval corresponds to one integration.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Determines different solution intervals:

        >>> hifv_solint()

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
