import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hsd.tasks.applycal.applycal.SDApplycalInputs.__init__
@utils.cli_wrapper
def hsd_applycal(vis=None, field=None, intent=None, spw=None, antenna=None,
                 applymode=None, flagbackup=None, parallel=None):
    """Apply the calibration(s) to the data.

    hsd_applycal applies the precomputed calibration tables stored in the pipeline
    context to the set of visibility files using predetermined field and
    spectral window maps and default values for the interpolation schemes.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Apply the calibration to the target data

        >>> hsd_applycal(intent='TARGET')

        2. Specify fields and spectral windows

        >>> hsd_applycal(field='3C279, M82', spw='17', intent='TARGET')

    """
