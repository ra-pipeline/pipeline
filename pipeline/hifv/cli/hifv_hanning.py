import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.hanning.hanning.HanningInputs.__init__
@utils.cli_wrapper
def hifv_hanning(vis=None, maser_detection=None, spws_to_smooth=None):
    """Hanning smoothing on a dataset.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Run the task to execute hanning smoothing on a VLA CASA pipeline loaded MeasurementSet:

        >>> hifv_hanning()

        2. Run the task with maser detection off and to only smooth spws 2 through 5.

        >>> hifv_hanning(maser_detection=False, spws_to_smooth='2~5')

    """
