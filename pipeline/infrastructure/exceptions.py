"""Exceptions used by pipeline execution and workflow control."""

from __future__ import annotations


class PipelineException(Exception):
    """Pipeline exception class."""


class PipelineEarlyExit(Exception):
    """Request an intentional early exit from the pipeline workflow.

    This exception is a control-flow signal rather than a pipeline failure.
    Tasks and QA handlers should normally attach the request to a task result
    so its detail page can be rendered before workflow execution stops.

    Args:
        message: Reason workflow execution should stop.
        create_errorfile: Whether the workflow entry point should create an
            ``errorexit`` sentinel.
    """

    def __init__(self, message: str, *, create_errorfile: bool = False) -> None:
        """Initialize a workflow stop request."""
        super().__init__(message)
        self.create_errorfile = create_errorfile

    def __reduce__(self) -> tuple[object, tuple[str], dict[str, bool]]:
        """Preserve workflow options when the exception is pickled."""
        return (
            self.__class__,
            (str(self),),
            {'create_errorfile': self.create_errorfile},
        )
