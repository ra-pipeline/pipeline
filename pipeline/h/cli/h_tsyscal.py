from . import utils


@utils.cli_wrapper
def h_tsyscal(vis=None, caltable=None, chantol=None, parallel=None):
    """Derive Tsys calibration tables for a list of ALMA MeasurementSets.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Standard call

        >>> h_tsyscal()
    """
