import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.diffgaincal.diffgaincal.DiffGaincalInputs.__init__
@utils.cli_wrapper
def hifa_diffgaincal(vis=None):
    """Derive SpW phase offsets from differential gain calibrator.

    This task creates the spectral window phase gain offset table used to allow
    calibrating the "on-source" spectral setup with phase gains from a
    "reference" spectral setup. A bright point source Quasar, called the
    Differential Gain Calibrator (DIFFGAIN) source, is used for this purpose.
    This DIFFGAIN source typically observed in groups of interleaved "reference"
    and "on-source" scans, once at the start and once at the end of the
    observations. In very long observations, there may be a group of scans
    occurring during the middle. Scan groups are combined while solving for SpW
    offsets between "reference" and "on-source" spectral setups.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Derive SpW phase offsets from differential gain calibrator.

        >>> hifa_diffgaincal()

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
