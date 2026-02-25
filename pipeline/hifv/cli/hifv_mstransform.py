import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.mstransform.mstransform.VlaMstransformInputs.__init__
@utils.cli_wrapper
def hifv_mstransform(vis=None, outputvis=None, outputvis_for_line=None, field=None, intent=None, spw=None, spw_line=None, chanbin=None, timebin=None, omit_contline_ms=None):
    """Create new MeasurementSets for science target imaging.

    Create new MeasurementSets for imaging from the corrected column of the input
    MeasurementSet via calling mstransform with all data selection parameters.
    By default, all science target data is copied to the new MS(s). The
    new MeasurementSet is not re-indexed to the selected data and the new MS will
    have the same source, field, and spw names and ids as it does in the parent MS.

    The first MeasurementSet that is produced is intended for continuum imaging and
    will end in targets_cont.ms. If there are spws that have been detected or specified as
    spectral line spws in the input MeasurementSet, an MS for science target line imaging
    will also be produced, which will end in _targets.ms.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Create a science target MS from the corrected column in the input MS:

        >>> hifv_mstransform()

        2. Make a phase and bandpass calibrator targets MS from the corrected
        column in the input MS:

        >>> hifv_mstransform(intent='PHASE,BANDPASS')

    """
