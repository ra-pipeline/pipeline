import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.restorepims.restorepims.RestorepimsInputs.__init__
@utils.cli_wrapper
def hifv_restorepims(vis=None, reimaging_resources=None):
    """Restore VLASS SE per-image MeasurementSet data, resetting flagging, weights, and applying self-calibration.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Basic restorepims task:

        >>> hifv_restorepims()

    """
