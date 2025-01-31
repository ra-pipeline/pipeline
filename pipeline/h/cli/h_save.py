import datetime

from . import utils


def h_save(filename=None):

    """Save the pipeline state to disk

    h_save saves the current pipeline state to disk using a unique filename.
    If no name is supplied one is generated automatically from a combination
    of the root name, 'context', the current stage number, and a time stamp.

    Args:
        filename: Name of the saved pipeline state. If filename is '' then a unique name will be generated computed several components: the
            root, 'context', the current stage number, and the time stamp.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Save the current state in the default file

        >>> h_save()

        2. Save the current state to a file called 'savestate_1'

        >>> h_save(filename='savestate_1')

    """

    context = utils.get_context()
    context.save(filename)
