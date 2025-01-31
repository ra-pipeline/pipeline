import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.bandpass.phcorbandpass.PhcorBandpassInputs.__init__
@utils.cli_wrapper
def hif_bandpass(vis=None, caltable=None, field=None, intent=None, spw=None, antenna=None, phaseup=None,
                 phaseupsolint=None, phaseupbw=None, solint=None, combine=None, refant=None, solnorm=None,
                 minblperant=None, minsnr=None):

    """Compute bandpass calibration solutions

    Compute amplitude and phase as a function of frequency for each spectral
    window in each MeasurementSet.

    Previous calibration can be applied on the fly.

    hif_bandpass computes a bandpass solution for every specified science
    spectral window. By default a 'phaseup' pre-calibration is performed
    and applied on the fly to the data, before the bandpass is computed.

    The hif_refant task may be used to precompute a prioritized list of
    reference antennas.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Compute a channel bandpass for all visibility files in the pipeline
        context using the CASA reference antenna determination scheme:

        >>> hif_bandpass()

        2. Same as the above but precompute a prioritized reference antenna list:

        >>> hif_refant()
        >>> hif_bandpass()

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
