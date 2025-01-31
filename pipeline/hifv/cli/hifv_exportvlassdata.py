import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.exportvlassdata.exportvlassdata.ExportvlassdataInputs.__init__
@utils.cli_wrapper
def hifv_exportvlassdata(vis=None):

    """Export Image data from QL, SE, and Coarse Cube modes of VLASS Survey.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Basic exportvlassdata task:

        >>> hifv_exportvlassdata()

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
