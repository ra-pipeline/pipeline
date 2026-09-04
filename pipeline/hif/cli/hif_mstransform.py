import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.mstransform.mstransform.MstransformInputs.__init__
@utils.cli_wrapper
def hif_mstransform(vis=None, outputvis=None, field=None, intent=None, spw=None, chanbin=None, timebin=None,
                    per_spw=None, parallel=None):
    """Split calibrated science target data into a new ``*targets.ms`` MeasurementSet.

    For each execution block, calibrated visibilities for the science targets are split from the
    CORRECTED column of the regular-calibrated MS, or from the data column of the
    self-calibrated MS, using the :func:`~casatasks.manipulation.mstransform` CASA task. The output MS is named
    with ``*targets.ms`` and is listed on the front WebLog page. At this stage the ``targets.ms``
    contains only the calibrated continuum and line emission data (no continuum subtraction yet).
    By default, all science target data is copied to the new MS.

    The new MS is not re-indexed: source, field, and spw names and IDs match the parent MS.
    Optionally, the imaging-ready MSes can be regridded to the source native frequency frame
    (currently only for LSRK).

    Notes:
        QA = 1.0 if the new MS is successfully created; 0.0 otherwise.

    Examples:
        1. Split all science target data:

        >>> hif_mstransform()

        2. Split only selected intents, for example phase and bandpass:

        >>> hif_mstransform(intent='PHASE,BANDPASS')

    """
