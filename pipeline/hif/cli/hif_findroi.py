import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.findroi.findroi.FindROIInputs.__init__
@utils.cli_wrapper
def hif_findroi(vis=None, field=None, spw=None, parallel=None):
    """Detect spectral-line regions of interest for ALMA science targets.

    ``hif_findroi`` is experimental in PL2026. It searches science target data
    for candidate line-emission regions and records the results as auxiliary
    findROI resources in ``findroi_workdir``. The standard PL2026 imaging and
    continuum-processing stages do not currently use these ROI results
    automatically.

    By default, the task processes the science target fields and science
    spectral windows available in the pipeline context, normally after
    ``hifa_importdata``. Use ``field`` and ``spw`` to restrict the search.
    Fully flagged spectral windows are skipped.

    The task produces a native stage-product pickle, ROI and continuum-range
    DAT files, summary plots, and a tarball containing these products. The
    resources are retained in the pipeline context and can be included in the
    auxiliary products by ``hifa_exportdata``.

    Examples:
        1. Run with recommended settings after importdata:

        >>> hif_findroi()

        2. Restrict processing to one virtual science spectral window:

        >>> hif_findroi(spw='25')

    """
