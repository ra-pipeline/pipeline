import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.fluxcalflag.fluxcalflag.FluxcalFlagInputs.__init__
@utils.cli_wrapper
def hifa_fluxcalflag(vis=None, field=None, intent=None, spw=None, threshold=None, appendlines=None, linesfile=None,
                     applyflags=None):
    """Locate and flag line regions in solar system flux calibrators.

    Search the built-in solar system flux calibrator line catalog for overlaps with
    the science spectral windows. Generate a list of line overlap regions and
    flagging commands.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Locate known lines in any solar system object flux calibrators:

        >>> hifa_fluxcalflag()

    """
