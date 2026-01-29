import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hsd.tasks.skycal.skycal.SDSkyCalInputs.__init__
@utils.cli_wrapper
def hsd_skycal(calmode=None, fraction=None, noff=None,
               width=None, elongated=None, parallel=None,
               infiles=None, field=None,
               spw=None, scan=None):
    """Calibrate data.

    The hsd_skycal generates a caltable for sky calibration that stores
    reference spectra, which is to be subtracted from on-source spectra to filter
    out non-source contribution.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Generate caltables for all data managed by context.

        >>> default(hsd_skycal)
        >>> hsd_skycal()
    """
