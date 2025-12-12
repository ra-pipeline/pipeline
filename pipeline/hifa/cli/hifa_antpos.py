import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.antpos.almaantpos.ALMAAntposInputs.__init__
@utils.cli_wrapper
def hifa_antpos(vis=None, caltable=None, hm_antpos=None, antenna=None, offsets=None, antposfile=None,
                threshold=None, snr=None, search=None):
    """Derive antenna position calibration tables for a list of MeasurementSets.

    The `hifa_antpos` task corrects antenna positions recorded in the ASDMs using
    updated calibration information obtained after the observation. Corrections can
    be input by hand, read from a file on disk, or by querying an ALMA database service.

    The `antposfile` parameter serves a dual purpose, depending on which mode is set.

    For `hm_antpos='file'`, `antposfile` defines the antenna positions file in 'csv' format containing
    6 comma-delimited columns as shown below. This file should not include blank lines, including
    after the end of the last entry. This parameter is required for `hm_antpos='file'`.

    Example of contents for a .csv file::

        ms, antenna, xoffset, yoffset, zoffset, comment
        uid___A002_X30a93d_X43e.ms, DV11, 0.000, 0.010, 0.000, 'No comment'
        uid___A002_X30a93d_X43e.dup.ms, DV11, 0.000, -0.010, 0.000, 'No comment'

    The offset values in this file are in meters.

    For `hm_antpos='online'`, `antposfile` defines the base outfile name used by the CASA tasks
    `getantposalma` and `gencal` with the MS basename prepended to it. The file must be in JSON format.
    If no value is set, it will default to `antennapos.json`.

    The corrections are used to generate a calibration table which is recorded
    in the pipeline context and applied to the raw visibility data, on the fly to
    generate other calibration tables, or permanently to generate calibrated
    visibilities for imaging.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Correct the position of antenna 'DV05' for all the visibility files in a
        single pipeline run:

        >>> hifa_antpos(antenna='DV05', offsets=[0.01, 0.02, 0.03])

        2. Correct the position of antennas for all the visibility files in a single
        pipeline run using antenna positions files on disk. These files are assumed
        to conform to a default naming scheme if ``antposfile`` is unspecified by the
        user:

        >>> hifa_antpos(hm_antpos='file', antposfile='myantposfile.csv')

        3. Correct the position of antennas for all the visibility files in a single
        pipeline run using antenna positions retrieved from DB, limiting the selection
        to antennas with S/N of 5.0 or more and using the 'both_closest' search algorithm.
        A JSON file is returned and fed into the gencal task to apply corrections.

        >>> hifa_antpos(hm_antpos='online', snr=5.0, search='both_closest')

    """
