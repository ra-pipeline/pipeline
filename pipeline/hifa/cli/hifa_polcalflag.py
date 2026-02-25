import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.polcalflag.polcalflag.PolcalflagInputs.__init__
@utils.cli_wrapper
def hifa_polcalflag(vis=None):
    """Flag polarization calibrators.

    This task flags corrected visibility outliers in the polarization calibrator
    data using the hif_correctedampflag heuristics.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Run with recommended settings to flag visibility outliers in the
        polarization calibrator data:

        >>> hifa_polcalflag()

    """
