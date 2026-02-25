import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.mstransform.mstransform.MstransformInputs.__init__
@utils.cli_wrapper
def hif_mstransform(vis=None, outputvis=None, field=None, intent=None, spw=None, chanbin=None, timebin=None,
                    parallel=None):
    """Create new MeasurementSets for science target imaging.

    Create new MeasurementSets for imaging from the corrected column of the input
    MeasurementSet via a single call to mstransform with all data selection parameters.
    By default, all science target data is copied to the new MS. The
    new MeasurementSet is not re-indexed to the selected data and the new MS will
    have the same source, field, and spw names and ids as it does in the parent MS.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Create a science target MS from the corrected column in the input MS.

        >>> hif_mstransform()

        2. Make a phase and bandpass calibrator targets MS from the corrected
        column in the input MS.

        >>> hif_mstransform(intent='PHASE,BANDPASS')

    """
