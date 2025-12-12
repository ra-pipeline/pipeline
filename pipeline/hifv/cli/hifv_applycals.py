import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.finalcals.applycals.ApplycalsInputs.__init__
@utils.cli_wrapper
def hifv_applycals(vis=None, field=None, intent=None, spw=None, antenna=None, applymode=None, flagbackup=None,
                   flagsum=None, flagdetailedsum=None, gainmap=None):
    """Apply calibration tables to input MeasurementSets.

    hifv_applycals applies the precomputed calibration tables stored in the pipeline
    context to the set of visibility files using predetermined field and
    spectral window maps and default values for the interpolation schemes.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Run the final applycals stage of the VLA CASA pipeline:

        >>> hifv_applycals()

    """
