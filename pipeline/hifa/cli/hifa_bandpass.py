import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.bandpass.almaphcorbandpass.ALMAPhcorBandpassInputs.__init__
@utils.cli_wrapper
def hifa_bandpass(vis=None, caltable=None, field=None, intent=None, spw=None, antenna=None, hm_phaseup=None,
                  phaseupbw=None, phaseupmaxsolint=None, phaseupsolint=None, phaseupsnr=None, phaseupnsols=None,
                  hm_phaseup_combine=None, hm_bandpass=None, solint=None, maxchannels=None, evenbpints=None, bpsnr=None,
                  minbpsnr=None, bpnsols=None, combine=None, refant=None, solnorm=None, minblperant=None, minsnr=None,
                  unregister_existing=None, hm_auto_fillgaps=None, parallel=None):
    """Performs temporal phase-up and derives bandpass calibration solutions.

    This task self-calibrates the bandpass calibrator by first obtaining
    phase-only solutions on a short time interval determined by signal-to-noise.
    It then calculates the antenna-based bandpass phase and amplitude solutions
    using an SNR-dependent frequency interval.

    Notes:
        **Temporal Phase-Up Workflow**

        As of PL2025, the `solint` and `combine` options are computed to achieve the
        target `phaseupsnr`. If `solint` is not `'int'`, the `combine` parameter is
        set to `'scan,spw'` to combine data from all spectral windows, thereby
        improving SNR. In this case, a temporary `gaincal` solution is made to
        obtain per-spw phase-offsets to align the phases of all spws. The
        `solint` is then calculated based on the SNR for the aggregate bandwidth.

        The logical workflow is illustrated below:

        .. figure:: /figures/PL2025_hifa_bandpass_phaseup.png
           :scale: 60%
           :alt: Workflow for hifa_bandpass temporal phase-up

           The logical workflow for the temporal phase-up process used in the
           :py:func:`hifa_bandpassflag <hifa_bandpassflag>` and :py:func:`hifa_bandpass <hifa_bandpass>` tasks that compute the
           `gaincal` `solint` and `combine` parameters.

        **Frequency Interval Calculation**

        The frequency interval for the final bandpass solution is determined by
        SNR. Since PL2024, this interval is rounded to counteract the `floor()`
        function in CASA, ensuring the interval has the desired number of
        channels. If the interval needed to reach the required SNR results in
        fewer than 8 channels, the interval is set to one-eighth of the
        bandwidth, and the result is assigned a QA subscore of 0.70.

        **WebLog Output and QA Metrics**

        The WebLog for this stage includes plots of amplitude and phase vs.
        frequency for the reference and a typical antenna, with the atmospheric
        transmission curve overlaid. QA metrics are calculated as follows:

        -   **Amplitude SNR Metric**: An error function with a 1-sigma deviation
            of 1.0 for the amplitude signal-to-noise ratio.

        -   **Phase Derivative Deviation (DD) Metric**: An error function with a
            1-sigma deviation of 0.03 for the "outlier fraction" (fraction of
            channels with a phase change > 5 MAD). This is mapped to a linear
            score:

            -   0.34 - 0.66 for DD < 0.2 (>12% outliers)
            -   0.67 - 0.9 for DD between 0.2 - 0.3
            -   0.91 - 1.0 for DD >= 0.3 (<8% outliers)

        -   A QA sub-score of 0.9 is assigned if spws were combined in the
            phase-up step (from PL2025).

        **BLC FDM Subband QA (PL2025+)**

        For data from FDM spectral windows using the Baseline Correlator (BLC),
        a new QA assesses anomalous features (e.g., offsets, jumps) at subband
        edges (effective width 58.59375 MHz). The score is based on five
        heuristics (two for phase, three for amplitude) per spw, antenna, and
        polarization that check for noisy subbands, offsets between subbands,
        and large amplitude spikes.

        -   If any heuristic is triggered, the QA score is between 0.35 and 0.65,
            based on the fraction of the affected spw.
        -   The evaluation is skipped and a score of 0.70 is assigned if an spw
            is narrow (< 125 MHz) or if low SNR requires a frequency interval
            >= the subband width.
        -   If no issues are found or the data is not BLC FDM, the score is 1.0.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Run with recommended settings:

        >>> hifa_bandpass()

    """
