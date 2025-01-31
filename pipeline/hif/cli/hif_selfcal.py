import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.selfcal.selfcal.SelfcalInputs.__init__
@utils.cli_wrapper
def hif_selfcal(vis=None, field=None, spw=None, contfile=None,
                apply=None, recal=None, refantignore=None, restore_resources=None,
                n_solints=None, amplitude_selfcal=None, gaincal_minsnr=None,
                minsnr_to_proceed=None, delta_beam_thresh=None,
                apply_cal_mode_default=None, rel_thresh_scaling=None,
                dividing_factor=None, check_all_spws=None, inf_EB_gaincal_combine=None,
                parallel=None):
    """Determine and apply self-calibration with the science target data

    Determine and apply self-calibration with the science target data

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Run self-calibration and apply solutions to all science targets and spws

        >>> hif_selfcal()

        2. Run self-calibration and apply solutions to a single science target

        >>> hif_selfcal(field="3C279")

        3. Run self-calibration with a more relaxed allowed fractional change in the beam size for a solution interval to be successful

        >>> hif_selfcal(delta_beam_thresh=0.15)

    """

    #                                                                        #
    #  CASA task interface boilerplate code starts here. No edits should be  #
    #  needed beyond this point.                                             #
    #                                                                        #

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
