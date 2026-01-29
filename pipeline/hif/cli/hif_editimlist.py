import pipeline.h.cli.utils as utils


@utils.cli_wrapper
def hif_editimlist(
    imagename=None,
    search_radius_arcsec=None,
    cell=None,
    cfcache=None,
    conjbeams=None,
    cyclefactor=None,
    cycleniter=None,
    nmajor=None,
    datatype=None,
    datacolumn=None,
    deconvolver=None,
    editmode=None,
    field=None,
    imaging_mode=None,
    imsize=None,
    intent=None,
    gridder=None,
    mask=None,
    pbmask=None,
    nbin=None,
    nchan=None,
    niter=None,
    nterms=None,
    parameter_file=None,
    pblimit=None,
    phasecenter=None,
    reffreq=None,
    restfreq=None,
    robust=None,
    scales=None,
    specmode=None,
    spw=None,
    start=None,
    stokes=None,
    sensitivity=None,
    threshold=None,
    nsigma=None,
    uvtaper=None,
    uvrange=None,
    width=None,
    vlass_plane_reject_ms=None,
):
    """Add to a list of images to be produced with ``hif_makeimages``.

    Returns:
        The results object for the pipeline task is returned.
    """
