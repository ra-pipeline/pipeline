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
    """Create cleaned images from the target list populated by :py:func:`hif_makeimlist <hif_makeimlist>`.

    Images are deconvolved using ``tclean`` with the ``auto-multithresh`` auto-masking algorithm
    (Kepley et al. 2020). Two thresholds, ``sidelobethreshold`` and ``noisethreshold``, control
    the masking at each minor cycle. For continuum imaging, if auto-masking prunes all regions, a
    fallback mask at the 0.3 primary beam response level is used. Cube imaging stages do not apply
    this fallback.

    Images are cleaned to `2 x (predicted rms noise) x (dynamic range correction factor)`, where
    the DR factor accounts for imaging artifacts at high dynamic range. For 12-m array calibrators
    the factor is 1 (DR <= 1000), DR/1000 (1000-3000), or DR/3000 (>= 3000). For 7-m array
    (1 EB) it is 1 (DR <= 200) or DR/200 (>= 200). For 12-m array science targets the factor
    ranges from 1 (DR <= 20) up to max(2.5, DR/150) (DR >= 150). The dynamic range correction
    factor is shown next to each image in the WebLog.

    The ``auto-multithresh`` parameters depend on array and configuration:

    .. code-block:: text

        Parameter          7m     12m b75<300m  12m b75=300-400m  12m b75>400m
        noisethreshold    5.0       4.25           5.0              5.0
        sidelobethreshold 1.25      2.0            2.0              2.5
        lownoisethreshold 2.0       1.5            1.5              1.5
        minbeamfrac       0.1       0.3            0.3              0.3
        fastnoise         False     False          False            True

    For cube imaging, an additional QA score assesses line contamination in line-free channels
    by computing ``mom8_fc`` (max along freq axis) and ``mom10_fc`` (min) images of the
    line-free channel ranges. Three metrics are evaluated: ``PeakSNR``, ``HistAsym``, and
    ``MaxSeg``. If PeakSNR > 5 and HistAsym > 0.2, or PeakSNR > 3.5 and HistAsym > 0.05 and
    MaxSeg > 1 beam area, the QA score is in the range 0.33-0.65 (yellow); otherwise 0.67-1.0.

    For check sources, additional Gaussian-fit-based QA is computed: positional offset from
    the catalog, peak/total flux ratio, and fitted/``gfluxscale`` flux ratio. The final check
    source QA score is the geometric mean of the three sub-scores.

    .. figure:: /figures/checksrc_table.png
       :scale: 60%
       :alt: Check source QA table

       Example of the check source QA table in the WebLog.

    .. figure:: /figures/hif_makeimages_cube_weblog.png
       :scale: 60%
       :alt: Cube imaging WebLog

       Example of the cube imaging WebLog page.

    Notes:
        Three base QA scores apply to all imaging stages:

        - QA = 0.0 if the clean algorithm diverges.
        - QA = 0.34 if an expected image is not created.
        - Third score = ratio of non-pbcor noise-annulus rms (0.3-0.2 PB level) to the product
          of the theoretical noise and the DR correction factor. QA = 1.0 if that ratio <= 1.0;
          QA = 0.0 if >= 5.0; linearly scaled between 1 and 5.

    Examples:
        1. Compute clean results for all imaging targets defined in a previous :py:func:`hif_makeimlist <hif_makeimlist>` call:

        >>> hif_makeimages()

        2. Compute clean results overriding automatic masking choice:

        >>> hif_makeimages(hm_masking='centralregion')

    """
