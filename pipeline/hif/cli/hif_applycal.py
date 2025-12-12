import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.applycal.ifapplycal.IFApplycalInputs.__init__
@utils.cli_wrapper
def hif_applycal(vis=None, field=None, intent=None, spw=None, antenna=None, parang=None, applymode=None, calwt=None,
                 flagbackup=None, flagsum=None, flagdetailedsum=None, parallel=None):
    """Apply precomputed calibrations to the data.

    `hif_applycal` applies the precomputed calibration tables stored in the pipeline
    context to the set of visibility files using predetermined field and
    spectral window maps and default values for the interpolation schemes.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Apply the calibration to the target data

        >>> hif_applycal(intent='TARGET')

    """
