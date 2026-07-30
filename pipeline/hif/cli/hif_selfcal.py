import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.selfcal.selfcal.SelfcalInputs.__init__
@utils.cli_wrapper
def hif_selfcal(vis=None, field=None, spw=None, contfile=None, hm_imsize=None, hm_cell=None,
                apply=None, recal=None, restore_only=None, overwrite=None,
                refantignore=None, restore_resources=None,
                n_solints=None, amplitude_selfcal=None, gaincal_minsnr=None,
                minsnr_to_proceed=None, delta_beam_thresh=None,
                apply_cal_mode_default=None, rel_thresh_scaling=None,
                dividing_factor=None, check_all_spws=None, inf_EB_gaincal_combine=None,
                usermask=None, usermodel=None, allow_wproject=None,
                parallel=None):
    """Perform iterative self-calibration on science targets with sufficient signal.

    Attempts phase-only self-calibration on each science target for which the estimated SNR per-EB
    per-antenna exceeds 3. The task channels-averages the science data to 15.625 MHz, flags
    line channels (from :py:func:`hif_findcont <hif_findcont>`), splits each source into a temporary MS, and then
    iterates through a series of gain solution intervals.

    The pipeline tracks multiple data type labels to manage regular and self-calibrated data:

    - ``REGCAL_CONTLINE_SCIENCE``: data with regular calibrations applied (``DATA`` column of
      ``*_targets.ms``).
    - ``SELFCAL_CONTLINE_SCIENCE``: data with self-calibration solutions applied (``CORRECTED``
      column of ``*_targets.ms``).
    - ``REGCAL_LINE_SCIENCE`` / ``SELFCAL_LINE_SCIENCE``: equivalent line (continuum-subtracted)
      datatypes in ``*_targets_line.ms``.

    **Solution interval sequence**: The first interval is always ``inf_EB`` (``combine='scan'``,
    ``solint='inf'``, ``gaintype='G'``), covering one entire EB and initially solving per-spw,
    per-polarization. Subsequent intervals use ``combine='spw'``, ``gaintype='T'``: ``inf``
    (one solution per scan), intermediate intervals splitting the median scan time, and finally
    ``int`` (one solution per integration). The target is 5 total intervals including ``inf`` and
    ``int``. Only the final successful interval and ``inf_EB`` (if not the final) are applied;
    intermediate successful intervals are discarded.

    **Solution acceptance**: A solution interval is accepted if all of the following hold:

    - The synthesized beam area does not increase by more than 5% compared with the pre-selfcal
      image.
    - The SNR of the post-selfcal image exceeds the SNR of the pre-selfcal image.
    - The near-field SNR (rms measured in an annulus just outside the clean mask) also improves.
    - The rms does not increase by more than 5%.

    If self-calibration succeeds, results are applied to both ``*_targets.ms`` and
    ``*_targets_line.ms``. The final image is cleaned to the minimum of ``3 x rms`` (from the
    final successful interval) and the pre-selfcal clean threshold.

    The WebLog shows a summary table of solution intervals attempted, SNR/rms before and after
    each interval, and whether self-calibration succeeded. Per-interval QA plot pages show
    before/after images and gain solutions per EB and antenna.

    .. figure:: /figures/selfcal_weblog.png
       :scale: 60%
       :alt: Self-calibration WebLog

       Example WebLog. The 'List of Self-cal Targets' table shows targets, imaging
       parameters, solution intervals, and success status. The 'Self-cal Target Details'
       section shows before/after SNR, rms, beam size, and images, and describes why
       self-calibration stopped.

    Notes:
        QA scores:

        - QA = 1.0 if self-calibration was not attempted (SNR too low).
        - QA = 0.99 if attempted but unsuccessful (solutions not applied).
        - QA = 0.98 if attempted and applied successfully.
        - QA = 0.85 if applied but the RMS got worse for at least one source.
        - QA = 0.90 if a new/experimental mode (e.g. mosaic self-calibration) was used.
        - QA = N/A for unsupported modes (e.g. ephemeris targets).

    Examples:
        1. Run self-calibration on all science targets:

        >>> hif_selfcal()

        2. Run self-calibration on a single science target:

        >>> hif_selfcal(field='3C279')

        3. Use a more relaxed beam-size acceptance threshold:

        >>> hif_selfcal(delta_beam_thresh=0.15)

    """
