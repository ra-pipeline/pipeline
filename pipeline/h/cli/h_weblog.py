from pipeline import show_weblog


def h_weblog(relpath=None):
    """Open the pipeline weblog in a browser

    h_weblog opens the weblog in a new browser tab or window.

    Args:
        relpath: Relative path to the weblog index file. This file must be located
            in a child directory of the CASA working directory. If relpath
            is left unspecified, the most recent weblog will be located and
            displayed.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Open pipeline weblog in a browser:

        >>> h_weblog()

    """
    show_weblog(index_path=relpath)
