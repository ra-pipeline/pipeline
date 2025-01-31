import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.imageprecheck.imageprecheck.ImagePreCheckInputs.__init__
@utils.cli_wrapper
def hifa_imageprecheck(vis=None, desired_angular_resolution=None, calcsb=None, parallel=None):
    """Calculates the best Briggs robust parameter to achieve sensitivity and angular resolution goals.

    In this task, the representative source and the spw containing the representative
    frequency selected by the PI in the OT are used to calculate the synthesized beam
    and to make sensitivity estimates for the aggregate bandwidth and representative
    bandwidth for several values of the Briggs robust parameter. This information is
    reported in a table in the weblog. If no representative target/frequency information
    is available, it defaults to the first target and center of first spw in the data
    (e.g. pre-Cycle 5 data does not have this information available). The best Briggs
    robust parameter to achieve the PI's desired angular resolution is chosen
    automatically. See the User's guide for further details.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. run with recommended settings to perform checks prior to imaging:

        >>> hifa_imageprecheck()

        2. run to perform checks prior to imaging and force the re-calculation of
        sensitivities and beams:

        >>> hifa_imageprecheck(calcsb=True)

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
