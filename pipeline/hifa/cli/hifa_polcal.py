import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.polcal.polcal.PolcalInputs.__init__
@utils.cli_wrapper
def hifa_polcal(vis=None, minpacov=None, solint_chavg=None, vs_stats=None, vs_thresh=None):
    """Derive instrumental polarization calibration for ALMA.

    Derive the instrumental polarization calibrations for ALMA using the
    polarization calibrators.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Compute the polarization calibrations:

        >>> hifa_polcal()

    """
