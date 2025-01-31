import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.gailcal.gaincalmode.GaincalModeInputs.__init__
@utils.cli_wrapper
def hif_gaincal(vis=None, caltable=None, field=None, intent=None, spw=None, antenna=None, hm_gaintype=None,
                calmode=None, solint=None, combine=None, refant=None, refantmode=None, solnorm=None, minblperant=None,
                minsnr=None, smodel=None, splinetime=None, npointaver=None, phasewrap=None):

    """Determine temporal gains from calibrator observations

    The complex gains are derived from the data column (raw data) divided by the
    model column (usually set with hif_setjy). The gains are obtained for a
    specified solution interval, spw combination and field combination.

    Good candidate reference antennas can be determined using the hif_refant
    task.

    Previous calibrations that have been stored in the pipeline context are
    applied on the fly. Users can interact with these calibrations via the
    h_export_calstate and h_import_calstate tasks.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        Compute standard per scan gain solutions that will be used to calibrate
        the target:

        >>> hif_gaincal()

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
