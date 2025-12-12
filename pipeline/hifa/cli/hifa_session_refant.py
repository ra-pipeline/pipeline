import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.sessionrefant.sessionrefant.SessionRefAntInputs.__init__
@utils.cli_wrapper
def hifa_session_refant(vis=None, phase_threshold=None):
    """Select best reference antenna for session(s).

    This task re-evaluates the reference antenna lists from all MeasurementSets
    within a session and combines these to select a single common reference
    antenna (per session) that is to be used by any subsequent pipeline stages.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Compute a single common reference antenna per session:

        >>> hifa_session_refant()

    """
