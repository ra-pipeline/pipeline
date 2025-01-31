import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.fluxscale.gcorfluxscale.GcorFluxscaleInputs.__init__
@utils.cli_wrapper
def hifa_gfluxscale(vis=None, reference=None, transfer=None, refintent=None, transintent=None, refspwmap=None,
                    reffile=None, phaseupsolint=None, solint=None, minsnr=None, refant=None, hm_resolvecals=None,
                    antenna=None, peak_fraction=None, amp_outlier_sigma=None):
    """Derive flux density scales from standard calibrators

    Derive flux densities for point source transfer calibrators using flux models
    for reference calibrators.

    Flux values are determined by:

    - computing phase only solutions for all the science spectral windows
      using the calibrator data selected by the ``reference`` and ``refintent``
      parameters and the ``transfer`` and ``transintent`` parameters, the value
      of the ``phaseupsolint`` parameter, and any spw combination determined
      in hifa_spwphaseup.

    - computing complex amplitude only solutions for all the science spectral
      windows using calibrator data selected with ``reference`` and
      ``refintent`` parameters and the ``transfer`` and ``transintent``
      parameters, the value of the ``solint`` parameter.

    - examining the amplitude-only solutions for obvious outliers and flagging
      them in the caltable.

    - transferring the flux scale from the reference calibrators to the transfer
      calibrators using ``refspwmap`` for windows without data in the reference
      calibrators.

    - inserting the computed flux density values into the MODEL_DATA column.

    Resolved calibrators are handled via antenna selection either automatically
    (``hm_resolvedcals`` = 'automatic') or manually (``hm_resolvedcals`` =
    'manual'). In the former case, antennas closer to the reference antenna than
    the uv distance where visibilities fall to ``peak_fraction`` of the peak are
    used. In manual mode, the antennas specified in ``antenna`` are used.

    Note that the flux corrected calibration table computed internally is
    not currently used in later pipeline apply calibration steps.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Compute flux values for the phase calibrator using model data from
        the amplitude calibrator:

        >>> hifa_gfluxscale()

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
