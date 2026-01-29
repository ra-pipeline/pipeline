import pipeline.infrastructure.launcher as launcher

from . import cli


def h_resume(filename: str | None = None):
    """Restore a saved pipeline state.

    Restores a named pipeline state from disk, allowing a suspended pipeline reduction session to be resumed.

    Args:
        filename: Saved pipeline state name. If set to ``'last'`` or left as ``None``, the most recently saved state
            ending with ``'.context'`` will be restored.

    Returns:
        The pipeline `context` object.

    Examples:
        Resume the last saved session:

            >>> h_resume()

        Resume from a saved session using the `context` snapshot after the processing stage-35:

            >>> h_resume(filename='pipeline-20230227T202157/saved_state/context-stage35.pickle')
    """
    _filename = filename or 'last'
    pipeline = launcher.Pipeline(context=_filename)

    cli.stack[cli.PIPELINE_NAME] = pipeline

    return pipeline.context
