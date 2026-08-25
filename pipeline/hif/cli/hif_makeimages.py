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
    """Create cleaned images from the target list populated by :func:`~pipeline.hif.cli.hif_makeimlist`.

    In standard ALMA interferometric recipes, this task is invoked multiple times for different imaging
    purposes. The scenarios include:

    - **Calibrator Images**
      The first time it is run in standard recipes is to create per-spw MFS continuum images of the calibrators,
      using Briggs weighting with ``robust=0.5``.

    - **Polarization Calibrator Images (polarization recipes only)**
      Creates and displays per-session aggregate continuum Stokes I, Q, U and V images of all polarization calibrators.
      It performs Gaussian fits to each Stokes I, Q, and U image to calculate polarization fraction and angle.
      An additional yellow QA score and warning message are given if the Stokes I, Q, or U fits fail.

      .. figure:: /figures/polcal_imaging.png
         :alt: Polarization calibrator imaging

         Example of polarization calibrator imaging, displaying fit results, polarization intensity/angle plots, and Stokes images.

    - **Check Source Images**
      After creating per-EB, per-spw images of all check sources, the pipeline performs a Gaussian fit and evaluates
      positional offsets and flux ratios. Check source imaging uses the dynamic range modifiers for science targets.
      An additional QA score is computed as the geometric mean of three sub-scores based on positional offset, decorrelation
      (peak/total flux), and flux scale transfer.

      .. figure:: /figures/checksrc_table.png
         :alt: Check source QA table

         Example of the check source QA table in the WebLog.

    - **Target Per-spw Continuum Images**
      Cleaned continuum images are created for each spectral window using the continuum frequency ranges determined
      from ``hif_findcont``, the ``robust`` value from ``hifa_imageprecheck``, and any size mitigation from ``hif_checkproductsize``.

      .. figure:: /figures/guide-img030.png
         :alt: Target per-spw continuum images

         Example of WebLog for target per-spw continuum images.

      .. figure:: /figures/guide-img031.png
         :alt: View other QA images

         Details page displayed after clicking "View other QA images".

    - **Target Aggregate Continuum Images**
      A cleaned aggregate continuum image (all spws combined) is formed from the ``hif_findcont`` channels.
      It is made with ``nterms=2`` if the fractional bandwidth is >= 10%.

    - **Target Cubes**
      Cleaned continuum-subtracted cubes are created for each science target and spectral window at the native
      channel resolution (unless channel binning was selected). Only non-continuum channels are cleaned.
      For cube imaging, an additional QA score assesses line contamination in line-free channels
      by computing ``mom8_fc`` (max along freq axis) and ``mom10_fc`` (min) images. A penalty applies
      if the synthesized beam shape deviates significantly across the cube.

      .. figure:: /figures/hif_makeimages_cube_weblog.png
         :alt: Cube imaging WebLog

         Example of the cube imaging WebLog page.

      .. figure:: /figures/guide-img033_2022.png
         :alt: Image cube details

         Example of image cube details including line-free moment images and per-channel noise/spectra.

      .. figure:: /figures/guide-img010.png
         :alt: Cube spectrum

         Cube spectrum constructed from pixels inside the clean mask, overlaid with a noise spectrum from outside the mask.

    - **Representative Bandwidth Target Cube**
      If the PI-requested bandwidth for sensitivity is significantly coarser (> 4x) than the native correlator channel
      width, an additional cube is created at the PI-requested bandwidth.

    The following common task functionality applies to all imaging stages:

    - **Image Coordinates**
      In all imaging stages, the image is centered on the ICRS equinox 2000 position requested in the
      Observing Tool, or the ICRS ephemeris direction evaluated at the time of first integration for
      ephemeris objects. For objects with non-zero proper motion or parallax, the coordinates are ICRS
      equinox 2000 but for the epoch of observation. The difference between the Source direction and
      Field direction shown in the WebLog reflects this parallax/proper motion term.
      
      For irregular mosaics, the ``psfphasecenter`` is explicitly set to prevent poor PSFs or ``tclean`` failures.

      .. figure:: /figures/psfphasecenter.png
         :alt: PSF phase center for irregular mosaics

         Irregularly shaped mosaics are automatically handled by setting the ``tclean`` ``psfphasecenter`` parameter.

    - **Full Polarization IQUV Imaging**
      In polarization recipes, full polarization Stokes IQUV images are made. The mask and ``tclean`` threshold
      from the corresponding Stokes I imaging stage are carried forward and used (with a fallback to no mask
      and recomputed thresholds if not found). This mask is only displayed in the Stokes I WebLog.
    
    - **Automatic Clean Boxes (Automasking)**
      Images are deconvolved using ``tclean`` with the ``auto-multithresh`` auto-masking algorithm (Kepley et al. 2020),
      which mimics interactive cleaning. The masking threshold is the greater of the values calculated based on the
      residual rms noise and sidelobe levels. For continuum imaging, if the algorithm prunes all regions (which can
      happen for compact, high-SNR emission), ``tclean`` is run again using a fallback clean mask corresponding to
      the area above a fraction of the primary beam response (default 0.3). To save time, this fallback is not done
      for cube imaging.
      
      The auto-masking parameters vary based on the array and the 75th percentile baseline length (b75):

      .. code-block:: text

          Parameter          7m     12m b75<300m  12m b75=300-400m  12m b75>400m
          noisethreshold    5.0       4.25           5.0              5.0
          sidelobethreshold 1.25      2.0            2.0              2.5
          lownoisethreshold 2.0       1.5            1.5              1.5
          minbeamfrac       0.1       0.3            0.3              0.3
          negativethreshold 0.0/15.0  0.0/7.0        0.0/7.0          0.0/7.0
          fastnoise         False     False          False            True

      *(Note: negativethreshold is 0.0 for continuum and the higher value for line imaging. fastnoise=True uses a simple median absolute deviation; fastnoise=False uses the Chauvenet method).*

    - **Cleaning Threshold and Dynamic Range**:
      Images are cleaned to `2 x (predicted rms noise) x (dynamic range correction factor)`.
      To prevent divergence, if on-source time < 60s and dirty DR > 30 for a cube image, it uses a factor of 5 instead of 2.

      .. list-table:: 12-m array dynamic range correction factor (Science Targets)
         :header-rows: 1

         * - Source Dynamic Range
           - Correction Factor
         * - <= 20
           - 1
         * - 20 -- 50
           - 1.5
         * - 50 -- 100
           - 2
         * - 100 -- 150
           - 2.5
         * - >= 150
           - max(2.5, DR/150)

      .. list-table:: 7-m array dynamic range correction factor (Science Targets)
         :header-rows: 1

         * - Source Dynamic Range
           - 1 EB
           - >= 2 EBs
         * - <= 4
           - 1
           - 1
         * - 4 -- 10
           - 1.5
           - 1.5
         * - 10 -- 20
           - 2
           - 2
         * - 20 -- 30
           - 2.5
           - 2.5
         * - 30 -- 55
           - max(2.5, DR/30)
           - 2.5
         * - 55 -- 75
           - max(2.5, DR/30)
           - 3.0
         * - >= 75
           - max(2.5, DR/30)
           - max(3.5, DR/55)

      .. list-table:: 12-m array dynamic range correction factor (Calibrators)
         :header-rows: 1

         * - Calibrator Dynamic Range
           - Correction Factor
         * - <= 1000
           - 1
         * - 1000 -- 3000
           - DR / 1000
         * - >= 3000
           - DR / 3000

      .. list-table:: 7-m array dynamic range correction factor (Calibrators, 1 EB)
         :header-rows: 1

         * - Calibrator Dynamic Range
           - Correction Factor
         * - <= 200
           - 1
         * - >= 200
           - DR / 200

    Notes:
        Three base QA scores apply to all imaging stages:

        - QA = 0.0 if the clean algorithm diverges.
        - QA = 0.34 if an expected image is not created.
        - Third score = ratio of non-pbcor noise-annulus rms (0.3-0.2 PB level) to the product
          of the theoretical noise and the DR correction factor. QA = 1.0 if that ratio <= 1.0;
          QA = 0.0 if >= 5.0; linearly scaled between 1 and 5.
        
        Low QA scores for non-Check source calibrators may indicate the need for additional flagging and/or
        significant decoherence.

    Examples:
        1. Compute clean results for all imaging targets defined in a previous :func:`~pipeline.hif.cli.hif_makeimlist` call:

        >>> hif_makeimages()

        2. Compute clean results overriding automatic masking choice:

        >>> hif_makeimages(hm_masking='centralregion')

    """
