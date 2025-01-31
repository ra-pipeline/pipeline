import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.fluxcalflag.fluxcalflag.FluxcalFlagInputs.__init__
@utils.cli_wrapper
def hifa_fluxcalflag(vis=None, field=None, intent=None, spw=None, threshold=None, appendlines=None, linesfiles=None,
                     applyflags=None):
    """Locate and flag line regions in solar system flux calibrators

    Search the built-in solar system flux calibrator line catalog for overlaps with
    the science spectral windows. Generate a list of line overlap regions and
    flagging commands.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Locate known lines in any solar system object flux calibrators:

        >>> hifa_fluxcalflag()

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
