import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.gaincal.timegaincal.TimeGaincalInputs.__init__
@utils.cli_wrapper
def hifa_timegaincal(vis=None, calamptable=None, calphasetable=None, offsetstable=None, targetphasetable=None,
                     amptable=None, field=None, spw=None, antenna=None, calsolint=None, targetsolint=None, refant=None,
                     refantmode=None, solnorm=None, minblperant=None, calminsnr=None, targetminsnr=None, smodel=None):
    """Determine temporal gains from calibrator observations

    The time-dependent complex gains for each antenna/spwid are determined from
    the raw data (DATA column) divided by the model (MODEL column), for the
    specified fields. The gains are computed according to the spw-combination
    model determined in hifa_spwphaseup.

    Previous calibrations are applied on the fly.

    The complex gains are derived from the data column (raw data) divided by the
    model column (usually set with hif_setjy). The gains are obtained for the
    specified solution intervals, spw combination and field combination. One
    gain solution is computed for the science targets and one for the calibrator
    targets.

    Good candidate reference antennas can be determined using the hif_refant
    task.

    Previous calibrations that have been stored in the pipeline context are
    applied on the fly. Users can interact with these calibrations via the
    h_export_calstate and h_import_calstate tasks.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Compute standard per scan gain solutions that will be used to calibrate
        the target:

        >>> hifa_timegaincal()

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
