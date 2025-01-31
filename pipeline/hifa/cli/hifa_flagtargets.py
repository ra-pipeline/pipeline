import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.flagging.flagtargetsalma.FlagTargetsALMAInputs.__init__
@utils.cli_wrapper
def hifa_flagtargets(vis=None, template=None, filetemplate=None, flagbackup=None):
    """Do science target flagging

    The hifa_flagtargets task performs basic flagging operations on a list of
    science target MeasurementSets, including:

    - applying a flagging template

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Do basic flagging on a science target MeasurementSet:

        >>> hifa_flagtargets()

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
