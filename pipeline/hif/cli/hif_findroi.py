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
    Fully flagged field/SPW combinations are skipped; spectral windows are also
    omitted if no selected field has usable data.

    The task produces a native stage-product pickle, ROI and continuum-range
    DAT files, summary plots, and a tarball containing these products. The
    result is registered in ``context.findroi_resources`` for inspection and
    can be included in the auxiliary products by ``hifa_exportdata``.

    The WebLog reports which field/SPW combinations were selected, completed
    successfully, or failed. A completed task does not necessarily mean that
    every requested combination produced a valid ROI. Inspect the per-SPW
    status and evidence plots when evaluating the result. Stage-level errors
    and cases with no selected science SPWs have an underlying QA score of 0.0.
    Plotting failures can reduce the underlying QA score to at most 0.5 when
    ROI results are otherwise available, and are likewise reported in the
    WebLog message. For ALMA Cycle 13 due to the experimental nature of the
    task, the reported QA score is hard-floored at 0.9, with the WebLog message
    recording the underlying score.

    .. figure:: /users_guide/whatsnew/weblogOverview.png
       :width: 900px
       :alt: Example hif_findroi WebLog summary and spectral ROI evidence view

       Example hif_findroi WebLog summary and spectral ROI evidence view. The
       displayed ROI products are still experimental and are not automatically
       consumed by standard downstream tasks in PL2026.

    Examples:
        1. Run with recommended settings after importdata:

        >>> hif_findroi()

        2. Restrict processing to one virtual science spectral window:

        >>> hif_findroi(spw='25')

    """
