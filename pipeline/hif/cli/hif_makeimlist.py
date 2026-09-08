import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.makeimlist.makeimlist.MakeImListInputs.__init__
@utils.cli_wrapper
def hif_makeimlist(vis=None, imagename=None, intent=None, field=None,
                   spw=None, stokes=None, contfile=None, linesfile=None,
                   uvrange=None, specmode=None, outframe=None, hm_imsize=None,
                   hm_cell=None, calmaxpix=None, minpix=None, phasecenter=None,
                   nchan=None, start=None, width=None, nbins=None,
                   robust=None, uvtaper=None, clearlist=None, per_eb=None,
                   per_session=None, calcsb=None, datatype=None, datacolumn=None,
                   allow_wproject=None, parallel=None):
    """Compute the list of images to be produced in the next :func:`~pipeline.hif.cli.hif_makeimages` call.

    This stage determines image parameters (image size, cell size, etc.) to be used in the subsequent
    :func:`~pipeline.hif.cli.hif_makeimages` stage, and reports them on the WebLog page. 
    The ``specmode`` can be ``'mfs'`` for per-spw continuum multi-frequency synthesis images,
    ``'cont'`` for aggregate mfs continuum images of several spectral windows, or ``'cube'`` for spectral cubes.
    If ``specmode`` is not specified, it defaults to ``'cube'`` for
    ``intent='TARGET'`` and to ``'mfs'`` for other intents. Standard ALMA
    recipes override this default when aggregate continuum, polarization,
    check-source, or representative-bandwidth products are required.
    When ``datatype`` is not specified, the task selects the first available
    matching data type from the preference order associated with the requested
    intent and ``specmode``.
    The first time the task is run in standard recipes is in preparation for making per-spw mfs images
    of the calibrators. The cell and imsize is chosen separately per band, so that more appropriate choices are
    made for multi-band data including BandToBandInterferometry.

    .. figure:: /figures/guide-img026.png
       :alt: Example of the WebLog for the hif_makeimlist stage

       Example of the WebLog for the hif_makeimlist stage. This example is for setting up the parameters
       for calibrator per-spw multi-frequency synthesis (mfs) continuum images.

    In standard ALMA interferometric recipes, the task is invoked multiple times for different imaging
    purposes by setting the ``intent``, ``specmode``, and other parameters accordingly. The scenarios include:

    - **Calibrator Images** (``intent='PHASE,BANDPASS,AMPLITUDE,POLARIZATION,DIFFGAINREF,DIFFGAINSRC'``)
      This prepares for making per-spw multi-frequency synthesis (MFS) continuum images of the calibrators.
      The cell and imsize are chosen separately per band to make appropriate choices for multi-band data,
      including BandToBandInterferometry. Image dimensions are limited to ``calmaxpix`` pixels.

    - **Polarization Calibrator Imaging** (``intent='POLARIZATION'``, ``specmode='cont'``, ``per_session=True``)
      Used only in polarization recipes. Prepares to create aggregate continuum Stokes I, Q, U, and V images
      of the polarization calibrators per session. The default image size is set to 256 in this stage.

    - **Check Source Images** (``intent='CHECK'``, ``per_eb=True``)
      Prepares to create check source images, one per EB per spw.

    - **Target Per-spw Continuum Imaging** (``specmode='mfs'``)
      Imaging parameters are determined and listed for the creation of per-spw MFS continuum images of each
      science target. This task also controls the parameters used to create the dirty cubes used by the
      ``hif_findcont`` stage, including any channel binning (listed in the "nbins" column of the WebLog table).

    - **Target Aggregate Continuum Images** (``specmode='cont'``)
      Imaging parameters are calculated and listed for the creation of an aggregate (all spectral windows
      combined) continuum image of each science target. The imaging parameters use the ``robust`` value selected
      from the ``hifa_imageprecheck`` stage and incorporate any mitigation triggered by the ``hif_checkproductsize``
      stage.

    - **Target Cube Imaging** (``specmode='cube'``)
      Parameters are calculated and listed for the creation of spectral cube images of each continuum-subtracted
      spectral window of each science target. As with aggregate continuum images, the cube parameters use the
      ``robust`` value from ``hifa_imageprecheck`` and any mitigation from ``hif_checkproductsize``.

    - **Representative Bandwidth Target Cube**
      The representative-bandwidth heuristic first determines whether the
      PI-requested bandwidth is represented by aggregate continuum imaging,
      per-spw continuum imaging, or a separate representative-bandwidth cube.
      No separate RepBW cube is created when the requested bandwidth is
      classified as covered by aggregate (``specmode='cont'``) or per-spw
      (``specmode='mfs'``) continuum imaging. Otherwise, a separate RepBW cube
      is created when the requested bandwidth is strictly greater than four
      times the default cube channel width after any ``hif_checkproductsize``
      channel binning.

    The cell size is set to the minimum consistent with the UV coverage. The image size is set from the
    cell size and primary beam size. If ``clearlist=True`` (default), the current pending imaging list
    and associated information are replaced before the new entries are written. Replacement is not
    limited to entries with the same intent.

    Notes:
        QA includes a primary score based on the fraction of expected imaging
        targets successfully added to the list. Task errors and size-mitigation
        errors receive a score of 0.0; when no clean targets are expected, the
        primary score becomes ``None``. Aggregate continuum targets also
        receive an additional score indicating whether continuum ranges were
        found for their spectral windows.

    Examples:
        1. Make a list of science target images to be cleaned, one image per science spw:

        >>> hif_makeimlist()

        2. Make a list of PHASE and BANDPASS calibrator targets to be imaged, one image per science spw:

        >>> hif_makeimlist(intent='PHASE,BANDPASS')

        3. Make a list of PHASE calibrator images observed in spw 1, images limited to 50 pixels on a side:

        >>> hif_makeimlist(intent='PHASE', spw='1', calmaxpix=50)

    """
