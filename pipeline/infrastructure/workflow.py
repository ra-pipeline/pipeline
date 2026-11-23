"""Workflow control state shared by pipeline execution entry points."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PipelineEarlyExitRequest:
    """Request that pipeline workflow execution stop after the current task.

    Attributes:
        message: Reason workflow execution should stop.
        create_errorfile: Whether to create an ``errorexit`` sentinel.
    """

    message: str
    create_errorfile: bool = False

    def __str__(self) -> str:
        """Return the human-readable stop reason."""
        return self.message
