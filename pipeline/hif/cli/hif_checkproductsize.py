import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.checkproductsize.checkproductsize.CheckProductSizeInputs.__init__
@utils.cli_wrapper
def hif_checkproductsize(vis=None, maxcubesize=None, maxcubelimit=None, maxproductsize=None, maximsize=None,
                         calcsb=None, parallel=None):
    """Check imaging product size.

    Check interferometry imaging product size and try to mitigate to maximum
    allowed values. `hif_checkproductsize` implements a mitigation cascade computing the largest
    cube size and tries to reduce it below a given limit by adjusting the ``nbins``,
    ``hm_imsize`` and ``hm_cell`` parameters. If this step succeeds, it also checks the
    overall imaging product size and if necessary reduces the number of fields to
    be imaged.

    Alternatively, if ``maximsize`` is set, the image product pixel count is
    mitigated by trying to adjust ``hm_cell`` parameter. If the pixel count is still
    greater than ``maximsize`` at ``hm_cell`` of 4ppb, then this value is kept and
    the image field is truncated around the phase center by forcing ``hm_imsize``
    to ``maximsize``.

    Note that mitigation for image pixel count and for the product size currently
    are mutually exclusive, with maximsize taking precedence if set.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Basic call to check the product sizes using internal defaults

        >>> hif_checkproductsize()

        2. Typical ALMA call

        >>> hif_checkproductsize(maxcubesize=40.0, maxcubelimit=60.0, maxproductsize=350.0)

    """
