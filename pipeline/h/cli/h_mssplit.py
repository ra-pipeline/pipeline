import sys

from . import utils


# docstring and type hints: inherits from h.tasks.mstransform.mssplit.MsSplitInputs.__init__
@utils.cli_wrapper
def h_mssplit(vis=None, outputvis=None, field=None, intent=None, spw=None, datacolumn=None, chanbin=None, timebin=None,
              replace=None):

    """Select data from calibrated MS(s) to form new MS(s) for imaging

    Create new MeasurementSets for imaging from the corrected column of the input
    MeasurementSet. By default all science target data is copied to the new MS. The new
    MeasurementSet is not re-indexed to the selected data in the new MS will have the
    same source, field, and spw names and ids as it does in the parent MS.

    The results object for the pipeline task is returned.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Create a 4X channel smoothed output MS from the input MS

        >>> h_mssplit(chanbin=4)

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
