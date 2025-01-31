import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.gaincalsnr.gaincalsnr.GaincalSnrInputs.__init__
@utils.cli_wrapper
def hifa_gaincalsnr(vis=None, field=None, intent=None, spw=None, phasesnr=None, bwedgefrac=None, hm_nantennas=None,
                    maxfracflagged=None):
    """Compute gaincal signal-to-noise ratios per spw

    The gaincal solution signal-to-noise is determined as follows:

    - For each data set the list of source(s) to use for the per-scan gaincal
      solution signal-to-noise estimation is compiled based on the values of the
      field, intent, and spw parameters.

    - Source fluxes are determined for each spw and source combination.

    - Fluxes in Jy are derived from the pipeline context.

    - Pipeline context fluxes are derived from the online flux calibrator
      catalog, the ASDM, or the user via the flux.csv file.

    - If no fluxes are available the task terminates.

    - Atmospheric calibration and observations scans are determined for each spw
      and source combination.

    - If intent is set to 'PHASE' are there are no atmospheric scans associated
      with the 'PHASE' calibrator, 'TARGET' atmospheric scans will be used
      instead.

    - If atmospheric scans cannot be associated with any of the spw and source
      combinations the task terminates.

    - Science spws are mapped to atmospheric spws for each science spw and
      source combinations.

    - If mappings cannot be determined for any of the spws the task terminates.

    - The median Tsys value for each atmospheric spw and source combination is
      determined from the SYSCAL table. Medians are computed first by channel,
      then by antenna, in order to reduce sensitivity to deviant values.

    - The science spw parameters, exposure time(s), and integration time(s) are
      determined.

    - The per scan sensitivity and signal-to-noise estimates are computed per
      science spectral window. Nominal Tsys and sensitivity values per receiver
      band provide by the ALMA project are used for this estimate.

    - The QA score is based on how many signal-to-noise estimates greater than
      the requested signal-to-noise ratio can be computed.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Estimate the per scan gaincal solution sensitivities and signal to noise
        ratios for all the science spectral windows:

        >>> hifa_gaincalsnr()

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
