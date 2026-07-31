import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.findroi.findroi.FindROIInputs.__init__
@utils.cli_wrapper
def hif_findroi(vis=None, field=None, spw=None, parallel=None):
    """Detect spectral-line regions of interest for ALMA science targets.

    This task is intended to run after ``hifa_importdata``. By default it uses
    the pipeline context to process all science target sources and science
    spectral windows. It writes a native findROI stage-product pickle, ROI DAT
    files, summary plots, and exported findROI resources for later downstream
    discovery through pipeline context.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Run with recommended settings after importdata:

        >>> hif_findroi()

        2. Restrict processing to one virtual science spectral window:

        >>> hif_findroi(spw='25')

    """
