import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.fluxscale.gcorfluxscale.GcorFluxscaleInputs.__init__
@utils.cli_wrapper
def hifa_gfluxscale(vis=None, reference=None, transfer=None, refintent=None, transintent=None, refspwmap=None,
                    reffile=None, phaseupsolint=None, solint=None, minsnr=None, refant=None, hm_resolvedcals=None,
                    antenna=None, peak_fraction=None, amp_outlier_sigma=None, parallel=None):
    """Derive flux density scales from standard calibrators.

    Derive flux densities for point source transfer calibrators using flux models
    for reference calibrators.

    Flux values are determined by:

    - computing phase-up solutions for all the science spectral windows
      using the calibrator data selected by the ``reference`` and ``refintent``
      parameters and the ``transfer`` and ``transintent`` parameters, with
      solint and gaintype parameters, and spw mapping or combination as
      determined in hifa_spwphaseup. If no solint is defined, ``phaseupsolint``
      is used (default = 'int').

    - computing amplitude only solutions for all the science spectral
      windows using calibrator data selected with ``reference`` and
      ``refintent`` parameters and the ``transfer`` and ``transintent``
      parameters.

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
    not currently used in later pipeline apply calibration steps because the
    relevant calibrator flux densities have been set in the MODEL_DATA column.

    Note that for very low SNR, noise bias already positively skews the amplitudes.
    The time solint could be greater for either ``transintent`` or ``refintent``,
    which has a compounding effect: if the phase stability is insufficient over
    that longer solint, an optimal phaseup will not be able to be calculated,
    and this also results in an artificial increase in amplitudes because
    the amplitude gains compensate for the uncorrected decorrelation.


    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Compute flux values for the phase calibrator using model data from
        the amplitude calibrator:

        >>> hifa_gfluxscale()

    """
