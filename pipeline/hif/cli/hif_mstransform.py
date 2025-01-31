import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.mstransform.mstransform.MstransformInputs.__init__
@utils.cli_wrapper
def hif_mstransform(vis=None, outputvis=None, field=None, intent=None, spw=None, chanbin=None, timebin=None):

    """Create new MeasurementSets for science target imaging

    Create new MeasurementSets for imaging from the corrected column of the input
    MeasurementSet via a single call to mstransform with all data selection parameters.
    By default, all science target data is copied to the new MS. The
    new MeasurementSet is not re-indexed to the selected data and the new MS will
    have the same source, field, and spw names and ids as it does in the parent MS.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Create a science target MS from the corrected column in the input MS.

        >>> hif_mstransform()

        2. Make a phase and bandpass calibrator targets MS from the corrected
        column in the input MS.

        >>> hif_mstransform(intent='PHASE,BANDPASS')

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
