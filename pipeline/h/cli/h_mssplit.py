from . import utils


# docstring and type hints: inherits from h.tasks.mstransform.mssplit.MsSplitInputs.__init__
@utils.cli_wrapper
def h_mssplit(vis=None, outputvis=None, field=None, intent=None, spw=None, datacolumn=None, chanbin=None, timebin=None,
              replace=None):
    """Select data from calibrated MS(s) to form new MS(s) for imaging.

    Create new MeasurementSets for imaging from the corrected column of the input
    MeasurementSet. By default all science target data is copied to the new MS. The new
    MeasurementSet is not re-indexed to the selected data in the new MS will have the
    same source, field, and spw names and ids as it does in the parent MS.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Create a 4X channel smoothed output MS from the input MS

        >>> h_mssplit(chanbin=4)

    """
