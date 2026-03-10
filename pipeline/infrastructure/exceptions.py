from enum import IntEnum


class PipelineExitCode(IntEnum):
    """Stable process exit codes for pipeline terminal outcomes."""

    SUCCESS = 0
    STOPPED = 10
    INVALID_REQUEST = 20
    TASK_FAILURE = 30
    INTERNAL_ERROR = 40


class PipelineException(Exception):
    """Base class for pipeline exceptions with stable exit-code mapping."""

    exit_code = PipelineExitCode.TASK_FAILURE

    def __init__(self, message: str = '', *, reason_code: str | None = None) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class PipelineRequestError(PipelineException):
    """Raised when the pipeline request is invalid or cannot be prepared."""

    exit_code = PipelineExitCode.INVALID_REQUEST


class PipelineTaskExecutionError(PipelineException):
    """Raised when a pipeline stage or task fails during execution."""

    exit_code = PipelineExitCode.TASK_FAILURE


class PipelineStopRequested(PipelineException):
    """Raised when pipeline execution should stop intentionally."""

    exit_code = PipelineExitCode.STOPPED


class PipelineInternalError(PipelineException):
    """Raised when the pipeline fails due to an unexpected internal error."""

    exit_code = PipelineExitCode.INTERNAL_ERROR


def exit_code_for_exception(exception: BaseException) -> int:
    """Return a stable process exit code for an exception.

    Args:
        exception: Exception raised during pipeline execution.

    Returns:
        Stable integer exit code for the exception class.
    """
    if isinstance(exception, PipelineException):
        return int(exception.exit_code)

    if isinstance(exception, KeyboardInterrupt):
        return int(PipelineExitCode.STOPPED)

    return int(PipelineExitCode.INTERNAL_ERROR)
