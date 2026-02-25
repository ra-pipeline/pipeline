from . import utils


def h_save(filename: str | None = None) -> None:
    """Save the current pipeline state to disk.

    If no filename is given, the name of the pipeline `context` object will be used.
    This name typically consists of the pipeline procedure name (or ``'pipeline-'``
    plus a timestamp) with the suffix ``'.context'``.

    Args:
        filename: Optional target filename for saving the pipeline state.

    Returns:
        None

    Examples:
        Save the current state to a default file:

        >>> h_save()

        Save the current state to a file named 'savestate_1':

        >>> h_save(filename='savestate_1')
    """
    context = utils.get_context()
    context.save(filename)
