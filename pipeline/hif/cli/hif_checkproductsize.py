import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.checkproductsize.checkproductsize.CheckProductSizeInputs.__init__
@utils.cli_wrapper
def hif_checkproductsize(vis=None, maxcubesize=None, maxcubelimit=None, maxproductsize=None, maximsize=None,
                         calcsb=None, parallel=None):
    """Mitigate imaging cube product sizes to fit within specified thresholds.

    This task modifies the characteristics of the imaging products in order to decrease their size, 
    thereby decreasing the time needed to make them so that data can be delivered to PIs more expediently, 
    and to prevent ``tclean`` failures on excessively large cubes. Datasets that have been mitigated will 
    have imaging products with different characteristics than those that have not been mitigated. 

    The pipeline recipe explicitly encodes the threshold values so they can be easily changed universally 
    for all pipeline runs. The ``casa_pipescript.py`` also encodes these values explicitly, so they can 
    be modified on a per-MOUS basis. Full imaging products can also be recreated by users without mitigation 
    by modifying the ``tclean`` commands in the ``casa_commands.log`` file.

    **Size Calculations**:
    
    The size calculations (in GB) for each spw are based on the following:

    - ``mfssize = 4.0 * nx * ny / 1e9``
    - ``cubesize = 4.0 * nx * ny * nchan / nbin / 1e9``
    - ``productsize = 2.0 * (mfssize + cubesize)``

    The 4 is the number of bytes per pixel, and the 2.0 accounts for the intensity image and the primary 
    beam image, which are both delivered to the user. When a full polarization IQUV imaging recipe is used, 
    ``mfssize`` and ``cubesize`` are inflated by a factor of 5 to account for the 4 axes in the IQUV image 
    in addition to the initial Stokes I image. The ``total_productsize`` is the sum of the individaul 
    ``productsize`` values, per spw.

    **Mitigation Cascade**:

    The mitigations are done in a priority order, halting once the predicted sizes fall below the thresholds
    The default limits are ``maxcubesize=40 GB``, ``maxcubelimit=60 GB``, and ``maxproductsize=500 GB``. For 
    ALMA long-baseline MOUSs ``maxcubelimit=100 GB``.

    - **Step 1** (If ``max(cubesize) > maxcubesize``, exceeding the limit, for all spws):

        a. Channel binning: set ``nbin=2`` if ``nchan`` == 7680 (single polarization)or 3840, or if ``nchan`` in 
           (1920, 960, 480) without prior online channel averaging.
        b. If still too large, primary beam (PB) level reduction: calculate the PB response level at which the largest cube size 
           equals the max allowed. The formula used is ``PB_mitigation = exp(-ln(2.0) * maxcubesize / current_cubesize / 1.01)``,
           with a cap at PB=0.7, and rounded up to 2 significant digits. 
           NOTE: this mitigation only applies to single fields (not mosaics) and uses the same mitigated FoV for all targets.
        c. If still too large, cell size reduction: change pixels-per-beam from 5 to 3.25 (if ``robust=+2``) or 3.0 (otherwise).
        d. If still too large, issue a warning that spectral window filtering will occur (later) if ``max(cubesize) > maxcubelimit``,
           cascade continues to step 2.

    - **Step 2** (If ``total_productsize > maxproductsize``):

        a. If the number of science targets (single fields or mosaics) is greater than 1, reduce the number of targets 
           to be imaged until ``total_productsize < maxproductsize``. The representative target is always retained.
        b. If still too large, repeat steps 1a, 1b, and 1c, recalculating ``total_productsize`` each time.
        c. If still too large, issue a warning that spectral window filtering will occur (later) to reduce ``total_productsize``,
           cascade continues to step 3.

    - **Step 3** (Conduct spectral window filtering to restrict the number of large cubes or obey step 1 and 2 limits):

        a. If the cube of the representative spectral window exceeds ``maxcubelimit`` stop with an error.
           The maximum cube size cannot be mitigated.
        b. If there are cubes with sizes > 0.5 * ``maxcubelimit``, but below ``maxcubelimit``, then restrict
           the number of these large cubes to be cleaned to 1. If the cube encompassing the representative frequency
           is not a large cube, a different spw large cube is retained. If not already, 
           the cube encompassing the representative frequency is retained.
           Cubes exceeding ``maxcubelimit`` are excluded and therefore not imaged.
        c. If ``total_productsze`` exceeds ``maxproductsize`` after the initial spw filtering, stop with an error.
           The total product size cannot be mitigated.
        d. Continuing with the cube(s) from (b), iteratively add spws to be imaged starting
           with the smallest ``cubesize``, summing the ``total_productsize`` until the ``maxproductsize`` is reached.

    - **Step 4** (Limit many science targets):

        a. For projects with more than 30 science targets to be imaged and over 960 channels summed over all spws,
           issue a warning that imaging will take a substantial time.

    .. figure:: /figures/PL2026_size_mitigation_flowchart_final.png
       :alt: Check product size mitigation cascade

       Workflow diagram indicating the image mitigation cascade. Colors are used to highlight certain workflow
       nodes, e.g. green represents an action to mitigate the image cube, yellow represents a decision using the
       various size limits, orange relates to warnings, red is a fail. 
       . 

    .. figure:: /figures/guide-img028.png
       :alt: Check product size mitigation example

       Screenshot of the hif_checkproductsize stage. In this example, the spws had to be binned by a factor of 2 
       and a single field selected in order to get the products below the thresholds. 

    Notes:
        QA = 1.0 if no mitigation was necessary; 0.85 (blue) if mitigation was applied; 0.0 if an error was encountered.

        When the cube or product size cannot be mitigated, the warning "QA Maximum cube size cannot be mitigated" 
        will appear at the top of the hif_checkproductsize stage, and the pipeline will stop in the first 
        :func:`~pipeline.hif.cli.hif_makeimlist` (cube) stage with the message: "Error! Size mitigation had failed. 
        Will not create any clean targets."

    Examples:
        1. Check product sizes with internal defaults:

        >>> hif_checkproductsize()

        2. Standard ALMA call with explicit thresholds:

        >>> hif_checkproductsize(maxcubesize=40.0, maxcubelimit=60.0, maxproductsize=500.0)

    """
