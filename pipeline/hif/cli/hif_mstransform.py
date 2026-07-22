import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.mstransform.mstransform.MstransformInputs.__init__
@utils.cli_wrapper
def hif_mstransform(vis=None, outputvis=None, field=None, intent=None, spw=None, chanbin=None, timebin=None,
                    per_spw=None, parallel=None):
    """Create new MeasurementSets for science target self-calibration and imaging.

    Create new MeasurementSets for self-calibration from the corrected column of the
    input MeasurementSet or from the data column of the self-calibrated MeasurementSet
    via a single call to mstransform with all data selection parameters.
    By default, all science target data is copied to the new MS. The
    new MeasurementSets are not re-indexed to the selected data and the new MSes will
    have the same source, field, and spw names and ids as it does in the parent MSes.
    The imaging MSes are re-gridded to the source native frequency frame (currently
    only for LSRK).

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Create a science target MS from the corrected column in the input MS.

        >>> hif_mstransform()

        2. Make a phase and bandpass calibrator targets MS from the corrected
        column in the input MS.

        >>> hif_mstransform(intent='PHASE,BANDPASS')

    """
