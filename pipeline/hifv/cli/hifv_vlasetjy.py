import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.selmodel.vlasetjy.VLASetjyInputs.__init__
@utils.cli_wrapper
def hifv_vlasetjy(vis=None, field=None, intent=None, spw=None, model=None, reffile=None, fluxdensity=None, spix=None,
                  reffreq=None, scalebychan=None, standard=None):

    """Sets flux density scale and fills calibrator model to measurement set.

    The hifv_vlasetjy task does an initial run of setjy on the vis.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Initial run of setjy:

        >>> hifv_vlasetjy()

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
