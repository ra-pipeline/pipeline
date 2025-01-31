import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.priorcals.priorcals.PriorcalsInputs.__init__
@utils.cli_wrapper
def hifv_priorcals(vis=None, show_tec_maps=None, apply_tec_correction=None, apply_gaincurves=None, apply_opcal=None, apply_rqcal=None,
                   apply_antpos=None, apply_swpowcal=None, swpow_spw=None, ant_pos_time_limit=None):

    """Runs gaincurves, opacities, requantizer gains, antenna position corrections, tec_maps, switched power.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Run gaincurves, opacities, requantizer gains and antenna position corrections:

        >>> hifv_priorcals()

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
