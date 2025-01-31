import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hsd.tasks.skycal.skycal.SDSkyCalInputs.__init__
@utils.cli_wrapper
def hsd_skycal(calmode=None, fraction=None, noff=None,
                 width=None, elongated=None, parallel=None,
                 infiles=None, field=None,
                 spw=None, scan=None):

    """Calibrate data.

    The hsd_skycal generates a caltable for sky calibration that stores
    reference spectra, which is to be subtracted from on-source spectra to filter
    out non-source contribution.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Generate caltables for all data managed by context.

        >>> default(hsd_skycal)
        >>> hsd_skycal()

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
