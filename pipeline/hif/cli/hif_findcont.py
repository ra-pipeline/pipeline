import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.findcont.findcont.FindContInputs.__init__
@utils.cli_wrapper
def hif_findcont(vis=None, target_list=None, hm_mosweight=None, hm_perchanweightdensity=None, hm_weighting=None,
                 datacolumn=None, parallel=None):
    """Find continuum frequency ranges for a list of specified targets.

    If a `cont.dat` file is not already present in the working directory, then dirty image
    cubes are created for each spectral window of each science target at the native channel
    resolution unless the ``nbins`` parameter was used in the preceding hif_makeimlist stage.
    Robust=1 Briggs weighting is used for optimal line sensitivity, even if a different
    robust had been chosen in hifa_imageprecheck to match the PI requested angular resolution.
    Using moment0 and moment8 images of each cube, SNR-based masks are created, and the mean
    spectrum of the joint mask is computed and evaluated with extensive heuristics to find the
    channel ranges that are likely to be free of line emission.  Warnings are generated if
    the channel ranges contain a small fraction of the bandwidth, or sample only a limited
    extent of the spectrum.

    If a `cont.dat` file already exists in the working directory before this task is executed,
    then it will first examine the contents. For any spw that already has frequency ranges
    defined in this file, it will not perform the analysis described above in favor of the
    a priori ranges. For spws not listed in a pre-existing file, it will analyze them as
    normal and update the file. In either case, the `cont.dat` file is used by the subsequent
    `hif_uvcontsub` and `hif_makeimages` stages.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Perform continuum frequency range detection for all science targets and spws:

        >>> hif_findcont()

    """
