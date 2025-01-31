import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.transformimagedata.transformimagedata.TransformimagedataInputs.__init__
@utils.cli_wrapper
def hif_transformimagedata(vis=None, outputvis=None, field=None, intent=None, spw=None, datacolumn=None, chanbin=None,
                           timebin=None, replace=None, clear_pointing=None, modify_weights=None, wtmode=None):

    """Extract fields for the desired VLASS image to a new MS and reset weights if desired

    Extract fields for the desired VLASS image to a new MS and reset weights if desired

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Basic transformimagedata task

        >>> hif_transformimagedata()

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
