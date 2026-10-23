import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.mstransform.mstransform.MstransformInputs.__init__
@utils.cli_wrapper
def hif_mstransform(vis=None, outputvis=None, field=None, intent=None, spw=None, chanbin=None, timebin=None,
                    per_spw=None, parallel=None):
    """Transform selected calibrated data into new MeasurementSets.

    For each execution block, calibrated visibilities are transformed from the
    data column associated with the selected pipeline data type using the
    :func:`~casatasks.manipulation.mstransform` CASA task.

    When the input contains regular-calibrated data for all scans, the output
    MS is named ``*_targets.ms`` and is listed on the front WebLog page. At
    this stage the target MS contains only the calibrated continuum and line
    emission data (no continuum subtraction yet). By default, all science
    target data are copied to the new MS.

    When the input contains regular- or self-calibrated science-only data, the
    task creates ``*_imaging.ms`` for continuum-plus-line data or
    ``*_imaging_line.ms`` for continuum-subtracted data. These imaging-ready
    MSes are regridded to LSRK for supported non-ephemeris data and are listed
    on the front WebLog page.

    The new MSes are not re-indexed: source, field, and spw names and IDs match
    the parent MS.

    Notes:
        QA = 1.0 if the new MS is successfully created; 0.0 otherwise.

    Examples:
        1. Split all science target data:

        >>> hif_mstransform()

        2. Transform a selected science target and spectral windows:

        >>> hif_mstransform(field='my_target', spw='0,1')

    """
