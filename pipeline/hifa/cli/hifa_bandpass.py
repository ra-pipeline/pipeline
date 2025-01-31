import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.bandpass.almaphcorbandpass.ALMAPhcorBandpassInputs.__init__
@utils.cli_wrapper
def hifa_bandpass(vis=None, caltable=None, field=None, intent=None, spw=None, antenna=None, hm_phaseup=None,
                  phaseupsolint=None, phaseupbw=None, phaseupsnr=None, phaseupnsols=None, hm_bandpass=None, solint=None,
                  maxchannels=None, evenbpints=None, bpsnr=None, minbpsnr=None, bpnsols=None, combine=None, refant=None,
                  solnorm=None, minblperant=None, minsnr=None, unregister_existing=None, hm_auto_fillgaps=None):
    """Compute bandpass calibration solutions

    The hifa_bandpass task computes a bandpass solution for every specified
    science spectral window. By default, a 'phaseup' pre-calibration is
    performed and applied on the fly to the data, before the bandpass is
    computed.

    The hif_refant task may be used to pre-compute a prioritized list of
    reference antennas.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Compute a channel bandpass for all visibility files in the pipeline
        context using the CASA reference antenna determination scheme:

        >>> hifa_bandpass()

        2. Same as the above but precompute a prioritized reference antenna list:

        >>> hif_refant()
        >>> hifa_bandpass()

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
