import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hsd.tasks.skycal.skycal.SDSkyCalInputs.__init__
@utils.cli_wrapper
def hsd_skycal(calmode=None, fraction=None, noff=None,
               width=None, elongated=None, parallel=None,
               infiles=None, field=None,
               spw=None, scan=None):
    """Generate sky (OFF-source) calibration tables for single-dish data.

    Produces a caltable storing the reference (OFF-source) spectra that are subtracted from
    on-source spectra to remove non-source contributions (atmosphere + receiver noise).

    The WebLog shows integrated OFF spectra per spw and per source for each MS. The y-axis
    represents the direct correlator output dominated by atmospheric and receiver signals.
    Different colors indicate different antennas; magenta lines show the atmospheric
    transmission curves. Time-averaged OFF spectra plots are also shown to assess time
    variability. Additional diagnostic plots include amplitude vs. time for OFF_SOURCE data
    and elevation difference between ON_SOURCE and OFF_SOURCE vs. time.

    .. figure:: /figures/guide-img035.png
       :scale: 60%
       :alt: OFF spectrum example

       Example of an OFF spectrum. Different antennas are shown in different colours;
       atmospheric transmission is shown in magenta.

    Notes:
        QA scoring:

        - QA = 1.0 if the elevation difference between ON and OFF is <= 3 degrees.
        - QA = 0.8 if the elevation difference between ON and OFF is > 3 degrees.

    Examples:
        1. Generate caltables for all data in the context:

        >>> hsd_skycal()

    """
