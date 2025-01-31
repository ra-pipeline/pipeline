import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.fluxscale.fluxboot.FluxbootInputs.__init__
@utils.cli_wrapper
def hifv_fluxboot(vis=None, caltable=None, fitorder=None, refantignore=None, refant=None):

    """Fluxboot

    Determine flux density bootstrapping for gain calibrators relative to flux calibrator.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. VLA CASA pipeline flux density bootstrapping:

        >>> hifv_fluxboot()

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
