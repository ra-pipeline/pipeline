import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.fixpointing.fixpointing.FixpointingInputs.__init__
@utils.cli_wrapper
def hifv_fixpointing(vis=None):
    """Base fixpointing task.

    Examples:
        1. Basic fixpointing task:

        >>> hifv_fixpointing()
    """
