import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.fluxscale.fluxboot.FluxbootInputs.__init__
@utils.cli_wrapper
def hifv_fluxboot(vis=None, caltable=None, fitorder=None, refantignore=None, refant=None):
    """Determine flux density bootstrapping for gain calibrators relative to flux calibrator.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. VLA CASA pipeline flux density bootstrapping:

        >>> hifv_fluxboot()

    """
