import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.correctedampflag.correctedampflag.CorrectedampflagInputs.__init__
@utils.cli_wrapper
def hif_correctedampflag(
        vis=None, intent=None, field=None, spw=None, antnegsig=None,
        antpossig=None, tmantint=None,
        tmint=None, tmbl=None, antblnegsig=None,
        antblpossig=None, relaxed_factor=None, niter=None):

    """Flag corrected - model amplitudes based on calibrators.

    This task computes the flagging heuristics on a calibrator by calling hif_correctedampflag
    which looks for outlier visibility points by statistically examining the scalar
    difference of corrected amplitudes minus model amplitudes, and flags those outliers.
    The philosophy is that only outlier data points that have remained outliers after
    calibration will be flagged. The heuristic works equally well on resolved calibrators
    and point sources because it is not performing a vector difference, and thus is not
    sensitive to nulls in the flux density vs. uvdistance domain. Note that the phase of
    the data is not assessed.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        Run default flagging on bandpass calibrator with recommended settings:

        >>> hif_correctedampflag()

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
