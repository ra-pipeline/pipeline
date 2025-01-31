import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.bandpassflag.bandpassflag.BandpassflagInputs.__init__
@utils.cli_wrapper
def hifa_bandpassflag(vis=None, caltable=None, intent=None, field=None, spw=None, antenna=None, hm_phaseup=None,
                      phaseupsolint=None, phaseupbw=None, phaseupsnr=None, phaseupnsols=None, hm_bandpass=None,
                      solint=None, maxchannels=None, evenbpints=None, bpsnr=None, minbpsnr=None, bpnsols=None,
                      combine=None, refant=None, minblperant=None, minsnr=None, solnorm=None, antnegsig=None,
                      antpossig=None, tmantint=None, tmint=None, tmbl=None, antblnegsig=None, antblpossig=None,
                      relaxed_factor=None, niter=None, hm_auto_fillgaps=None):
    """Bandpass calibration flagging

    This task performs a preliminary phased-up bandpass solution and temporarily
    applies it, then computes the flagging heuristics by calling
    hif_correctedampflag which looks for outlier visibility points by statistically
    examining the scalar difference of the corrected amplitudes minus model
    amplitudes, and then flags those outliers. The philosophy is that only outlier
    data points that have remained outliers after calibration will be flagged. Note
    that the phase of the data is not assessed.

    Plots are generated at two points in this workflow: after bandpass calibration
    but before flagging heuristics are run, and after flagging heuristics have been
    run and applied. If no points were flagged, the 'after' plots are not generated
    or displayed.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. run with recommended settings to create bandpass solution with flagging
        using recommended thresholds:

        >>> hifa_bandpassflag()

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
