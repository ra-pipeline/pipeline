import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.makeimages.makeimages.MakeImagesInputs.__init__
@utils.cli_wrapper
def hif_makeimages(vis=None, target_list=None, hm_masking=None,
                   hm_sidelobethreshold=None, hm_noisethreshold=None, hm_lownoisethreshold=None,
                   hm_negativethreshold=None, hm_minbeamfrac=None, hm_growiterations=None,
                   hm_dogrowprune=None, hm_minpercentchange=None, hm_fastnoise=None, hm_nsigma=None,
                   hm_perchanweightdensity=None, hm_npixels=None, hm_cyclefactor=None, hm_nmajor=None, hm_minpsffraction=None,
                   hm_maxpsffraction=None, hm_weighting=None, hm_cleaning=None, tlimit=None, drcorrect=None, masklimit=None,
                   cleancontranges=None, calcsb=None, hm_mosweight=None, overwrite_on_export=None, vlass_plane_reject_im=None,
                   parallel=None):
    """Compute clean results from a list of specified targets.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Compute clean results for all imaging targets defined in a previous hif_makeimlist or hif_editimlist call:

        >>> hif_makeimages()

        2. Compute clean results overriding automatic masking choice:

        >>> hif_makeimages(hm_masking='centralregion')

    """
