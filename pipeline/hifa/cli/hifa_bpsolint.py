import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.bpsolint.bpsolint.BpSolintInputs.__init__
@utils.cli_wrapper
def hifa_bpsolint(vis=None, field=None, intent=None, spw=None, phaseupsnr=None, minphaseupints=None, evenbpints=None,
                  bpsnr=None, minbpsnr=None, minbpnchan=None, hm_nantennas=None, maxfracflagged=None):
    """Compute optimal bandpass calibration solution intervals.

    The task estimates the optimal time and frequency solution intervals needed to
    achieve the required signal-to-noise ratio. This estimation is based on nominal
    ALMA array characteristics and the observation's metadata.

    The phaseup gain time and bandpass frequency intervals are determined as
    follows:

    - For each data set the list of source(s) to use for bandpass solution
      signal-to-noise estimation is compiled based on the values of the
      ``field``, ``intent``, and ``spw`` parameters.

    - Source fluxes are determined for each spw and source combination.

    - Fluxes in Jy are derived from the pipeline context.

    - Pipeline context fluxes are derived from the online flux calibrator
      catalog, the ASDM, or the user via the flux.csv file.

    - If no fluxes are available the task terminates.

    - Atmospheric calibration and observations scans are determined for each
      spw and source combination.

    - If ``intent`` is set to 'PHASE' are there are no atmospheric scans
      associated with the 'PHASE' calibrator, 'TARGET' atmospheric scans will be
      used instead.

    - If atmospheric scans cannot be associated with any of the spw and source
      combinations the task terminates.

    - Science spws are mapped to atmospheric spws for each science spw and
      source combination.

    - If mappings cannot be determined for any of the spws the task terminates.

    - The median Tsys value for each atmospheric spw and source combination is
      determined from the SYSCAL table. Medians are computed first by channel,
      then by antenna, in order to reduce sensitivity to deviant values.

    - The science spw parameters, exposure time(s), and integration time(s) are
      determined.

    - The phase-up time interval, in time units and number of integrations
      required to meet the ``phaseupsnr`` are computed, along with the
      sensitivity in mJy and the signal-to-noise per integration. Nominal Tsys
      and sensitivity values per receiver band provided by the ALMA project are
      used for this estimate.

    - Warnings are issued if estimated phase-up gain time solution would contain
      fewer than ``minphaseupints`` solutions.

    - The frequency interval, in MHz and number of channels required to meet the
      ``bpsnr`` are computed, along with the per channel sensitivity in mJy and
      the per channel signal-to-noise. Nominal Tsys and sensitivity values per
      receiver band provided by the ALMA project are used for this estimate.

    - Warnings are issued if estimated bandpass solution would contain fewer
      than ``minbpnchan`` solutions.

    - If strong atmospheric features are detected in the Tsys spectrum for a
      given spw, the frequency interval of bandpass solution is recalculated to
      meet the lower threshold ``minbpsnr``, i.e., a lower snr is tolerated in
      order to preserve enough frequency intervals to capture the atmospheric
      line.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Estimate the phaseup gain time interval and the bandpass frequency
        interval required to match the desired signal-to-noise for bandpass
        solutions:

        >>> hifa_bpsolint()

    """
