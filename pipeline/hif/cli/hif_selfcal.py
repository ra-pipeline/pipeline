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
    """Determine and apply self-calibration with the science target data.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Run self-calibration and apply solutions to all science targets and spws

        >>> hif_selfcal()

        2. Run self-calibration and apply solutions to a single science target

        >>> hif_selfcal(field="3C279")

        3. Run self-calibration with a more relaxed allowed fractional change in the beam size for a solution interval to be successful

        >>> hif_selfcal(delta_beam_thresh=0.15)

    """
