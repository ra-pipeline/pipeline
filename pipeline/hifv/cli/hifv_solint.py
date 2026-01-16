import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.fluxscale.solint.SolintInputs.__init__
@utils.cli_wrapper
def hifv_solint(vis=None, limit_short_solint=None, refantignore=None, refant=None):
    """Determines different solution intervals.

    The hifv_solint task determines different solution intervals. Note that the short solint value is switched to 'int' when
    the minimum solution interval corresponds to one integration.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Determines different solution intervals:

        >>> hifv_solint()

    """
