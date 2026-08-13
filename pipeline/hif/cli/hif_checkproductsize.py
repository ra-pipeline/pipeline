import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.checkproductsize.checkproductsize.CheckProductSizeInputs.__init__
@utils.cli_wrapper
def hif_checkproductsize(vis=None, maxcubesize=None, maxcubelimit=None, maxproductsize=None, maximsize=None,
                         calcsb=None, parallel=None):
    """Mitigate imaging product sizes to fit within specified thresholds.

    This task modifies the characteristics of the imaging products in order to decrease their size, 
    thereby decreasing the time needed to make them so that data can be delivered to PIs more expediently, 
    and to prevent ``tclean`` failures on excessively large cubes. Datasets that have been mitigated will 
    have imaging products with different characteristics than those that have not been mitigated. 

    The pipeline recipe explicitly encodes the threshold values so they can be easily changed universally 
    for all pipeline runs. The ``casa_pipescript.py`` also encodes these values explicitly, so they can 
    be modified on a per-MOUS basis. Full imaging products can be recreated by users without mitigation 
    by modifying the ``tclean`` commands in the ``casa_commands.log`` file.

    **Size Calculations**:
    
    The size calculations (in GB) are based on the following:

    - ``mfssize = 4.0 * nx * ny / 1e9``
    - ``cubesize = 4.0 * nx * ny * nchan / nbin / 1e9``
    - ``productsize = 2.0 * (mfssize + cubesize)``

    The 4 is the number of bytes per pixel, and the 2.0 accounts for the intensity image and the primary 
    beam image, which are both delivered to the user. When a full polarization IQUV imaging recipe is used, 
    this is inflated by a factor of 5 to account for the 4 axes in the IQUV image in addition to the initial 
    Stokes I image.

    **Mitigation Cascade**:

    The mitigations are done in a priority order, halting once the predicted sizes fall below the thresholds. 
    The default limits are ``maxcubesize=40 GB``, ``maxcubelimit=60 GB``, and ``maxproductsize=500 GB``.

    - **Step 1** (If ``cubesize > maxcubesize``, for each spw exceeding the limit):

        a. Channel binning: set ``nbin=2`` if nchan == 3840 or in (1920, 960, 480) without prior
           online channel averaging.
        b. Primary beam (PB) level reduction: calculate the PB response level at which the largest cube size 
           equals the max allowed. The formula used is ``PB_mitigation = exp(ln(0.2) * maxcubesize / current_cubesize)``.
           This is adjusted for padding (``* 1.02``), capped at PB=0.7, and rounded to 2 significant digits. 
           NOTE: this mitigation only applies to single fields (not mosaics) and uses the same mitigated FoV for all targets.
        c. Cell size reduction: change pixels-per-beam from 5 to 3.25 (if ``robust=+2``) or 3.0 (otherwise).
        d. If still too large: stop with an error because the largest size cube(s) cannot be mitigated.

    - **Step 2** (If ``productsize > maxproductsize``):

        a. If the number of science targets (single fields or mosaics) is greater than 1, reduce the number of targets 
           to be imaged until productsize < maxproductsize. The representative target is always retained.
        b. If still too large, repeat steps 1a, 1b, and 1c, recalculating productsize each time.
        c. If still too large: stop with an error because the productsize cannot be mitigated.

    - **Step 3** (Limit large cubes):

        a. If there are cubes with sizes > 0.5 * maxcubelimit, limit the number of large cubes to be cleaned to 1. 
           The spw encompassing the representative frequency is always retained.

    - **Step 4** (Limit many science targets):

        a. For projects with many science targets, limit the number to be imaged to 30. The representative target 
           is always retained.

    .. figure:: /figures/guide-img028.png
       :alt: Check product size mitigation example

       Screenshot of the hif_checkproductsize stage. In this example, the spws had to be binned by a factor of 2 
       and a single field selected in order to get the products below the thresholds. 

    Notes:
        QA = 1.0 if no mitigation was necessary; 0.85 (blue) if mitigation was applied; 0.0 if an error was encountered.

        When the cube or product size cannot be mitigated, the warning "QA Maximum cube size cannot be mitigated" 
        will appear at the top of the hif_checkproductsize stage, and the pipeline will stop in the first 
        :py:func:`hif_makeimlist <hif_makeimlist>` (cube) stage with the message: "Error! Size mitigation had failed. 
        Will not create any clean targets."

    Examples:
        1. Check product sizes with internal defaults:

        >>> hif_checkproductsize()

        2. Standard ALMA call with explicit thresholds:

        >>> hif_checkproductsize(maxcubesize=40.0, maxcubelimit=60.0, maxproductsize=350.0)

    """
