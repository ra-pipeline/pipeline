import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.checkproductsize.checkproductsize.CheckProductSizeInputs.__init__
@utils.cli_wrapper
def hif_checkproductsize(vis=None, maxcubesize=None, maxcubelimit=None, maxproductsize=None, maximsize=None,
                         calcsb=None, parallel=None):
    """Mitigate imaging product sizes to fit within specified thresholds.

    Checks the predicted sizes of all imaging products and applies a mitigation cascade to keep them
    within the allowed limits. Default thresholds are ``maxcubesize=40 GB``, ``maxcubelimit=60 GB``,
    and ``maxproductsize=500 GB``. Size estimates use 4 bytes/pixel; both the intensity image and
    primary beam image are counted.

    The mitigation cascade (applied in order until sizes fall below the thresholds) is:

    - **Step 1** (per spw exceeding maxcubesize):

        a. Channel binning: set ``nbin=2`` if nchan == 3840 or in (1920, 960, 480) without prior
           online averaging.
        b. Primary beam level reduction: compute ``PB_mitigation = exp(ln(0.2) * maxcubesize /
           cubesize)`` (with padding correction and clamped to PB=0.7). Only for single-field
           targets; same mitigated FoV applies to all products.
        c. Cell size reduction: change pixels-per-beam from 5 to 3.25 (``robust=+2``) or 3.0
           (otherwise).
        d. If still too large: stop with error.

    - **Step 2** (if productsize > maxproductsize):

        a. Reduce the number of science targets until productsize < maxproductsize (representative
           target is always retained).
        b. If still too large, repeat Step 1 mitigations.
        c. If still too large: stop with error.

    - **Step 3**: If any cube > 0.5 x maxcubelimit, limit the number of large cubes cleaned to 1
      (the spw containing the representative frequency is always retained).

    - **Step 4**: Limit the number of science targets to image to 30 (representative target always
      retained).

    The ``casa_commands.log`` file contains the ``tclean`` commands that can be re-run without
    mitigation. The ``casa_pipescript.py`` file explicitly encodes the threshold values so they can
    be modified on a per-MOUS basis.

    Notes:
        QA = 1.0 if no mitigation was necessary; 0.85 (blue) if mitigation was applied; 0.0 if
        mitigation was attempted but failed (error message appears at the top of the WebLog page).

    Examples:
        1. Check product sizes with internal defaults:

        >>> hif_checkproductsize()

        2. Standard ALMA call with explicit thresholds:

        >>> hif_checkproductsize(maxcubesize=40.0, maxcubelimit=60.0, maxproductsize=350.0)

    """
