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
    """Compute the list of images to be produced in the next :py:func:`hif_makeimages <hif_makeimages>` call.

    Determines image parameters (cell size, image size, spectral mode, etc.) for each target/spw and
    populates the pipeline context imaging list. The WebLog reports the chosen parameters.

    In standard ALMA interferometric recipes the task is invoked multiple times for different imaging
    purposes by setting the ``intent`` and ``specmode`` parameters accordingly:

    - **Calibrators** (``intent='PHASE,BANDPASS,AMPLITUDE,POLARIZATION,DIFFGAINREF,DIFFGAINSRC'``): per-spw
      MFS continuum images, with image dimensions limited to ``calmaxpix`` pixels.
    - **Polarization calibrator** (polcal recipes): per-spw MFS images of the polarization calibrator.
    - **Check source**: per-spw MFS image of the check source.
    - **Per-spw continuum** (``specmode='cont'``): aggregate MFS continuum images combining multiple spws.
    - **Aggregate continuum** (``specmode='cont'``): using continuum channel selections from ``cont.dat``.
    - **Spectral cube** (``specmode='cube'``): per-spw cubes for science targets.
    - **Representative bandwidth cube**: cube over the representative bandwidth.

    The cell size is set to the minimum consistent with the UV coverage. The image size is set from the
    cell size and primary beam size. If ``clearlist=True`` (default) any existing imaging list entries
    for the same intent are replaced.

    Notes:
        QA = fraction of images successfully added to the list compared to the total expected.

    Examples:
        1. Make a list of science target images to be cleaned, one image per science spw:

        >>> hif_makeimlist()

        2. Make a list of PHASE and BANDPASS calibrator targets to be imaged, one image per science spw:

        >>> hif_makeimlist(intent='PHASE,BANDPASS')

        3. Make a list of PHASE calibrator images observed in spw 1, images limited to 50 pixels on a side:

        >>> hif_makeimlist(intent='PHASE', spw='1', calmaxpix=50)

    """
