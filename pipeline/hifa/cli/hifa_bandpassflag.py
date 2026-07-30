import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.bandpassflag.bandpassflag.BandpassflagInputs.__init__
@utils.cli_wrapper
def hifa_bandpassflag(vis=None, caltable=None, intent=None, field=None, spw=None, antenna=None, hm_phaseup=None,
                      phaseupbw=None, phaseupmaxsolint=None, phaseupsolint=None, phaseupsnr=None, phaseupnsols=None,
                      hm_phaseup_combine=None, hm_bandpass=None, solint=None, maxchannels=None, evenbpints=None,
                      bpsnr=None, minbpsnr=None, bpnsols=None, combine=None, refant=None, minblperant=None,
                      minsnr=None, solnorm=None, antnegsig=None, antpossig=None, tmantint=None, tmint=None, tmbl=None,
                      antblnegsig=None, antblpossig=None, relaxed_factor=None, niter=None, hm_auto_fillgaps=None,
                      parallel=None):
    """Flag outlier visibilities in the bandpass calibrator data.

    Calculates an initial phase-up and bandpass solution (see :py:func:`hifa_bandpass <hifa_bandpass>`), applies it temporarily, then
    identifies outlier visibilities by statistically examining the scalar difference of calibrated amplitudes
    minus model amplitudes for the bandpass calibrator. If flags are found, a second iteration is performed.
    At the end the flagging state from before this task is restored and all flags found here are applied.

    Only amplitude outliers are assessed; the phase of the data is not evaluated.

    The WebLog shows two sets of amplitude vs. uv-distance plots for the bandpass calibrator: before flagging
    and after flagging. If no data were flagged, the 'after' plots are not generated.

    .. figure:: /figures/guide-img022.png
       :scale: 60%
       :alt: Before bandpass flagging

       Before flagging: example of outlier amplitudes.

    .. figure:: /figures/guide-img023.png
       :scale: 60%
       :alt: After bandpass flagging

       After flagging: the same data with outlier visibilities removed.

    Notes:
        The 'before' flagging fraction shown in the summary table may differ from the 'after' fraction shown
        in :py:func:`hifa_flagdata <hifa_flagdata>`, because the 'before' summary is computed on a data set that has already had
        calibration tables temporarily applied (and therefore some flagging already propagated). This is
        intentional: the before/after summary is designed to show clearly how much new flagging is introduced
        by this task.

        QA = 1 - (fraction of data newly flagged). An additional score of 0.8 is assigned if any spw has an
        antenna that is fully flagged.

    Examples:
        1. Run with recommended settings to create bandpass solution with flagging using recommended thresholds:

        >>> hifa_bandpassflag()

    """
