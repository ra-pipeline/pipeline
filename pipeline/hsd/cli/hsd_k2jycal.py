import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hsd.tasks.k2jycal.k2jycal.SDK2JyCalInputs.__init__
@utils.cli_wrapper
def hsd_k2jycal(dbservice=None, endpoint=None, reffile=None,
                infiles=None, caltable=None):
    """Derive Kelvin to Jy calibration tables.

    Derive the Kelvin to Jy calibration for list of MeasurementSets.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Compute the Kevin to Jy calibration tables for a list of MeasurementSets:

        >>> hsd_k2jycal()

    """
