"""Exceptions used by pipeline execution and workflow control."""

from __future__ import annotations


class PipelineException(Exception):
    """Pipeline exception class."""


class PipelineEarlyExit(Exception):
    """Request an intentional early exit from the pipeline workflow.

    This exception is a control-flow signal rather than a pipeline failure.
    Workflow entry points must catch it, save the current context, and return
    without creating an ``errorexit`` file.
    """
