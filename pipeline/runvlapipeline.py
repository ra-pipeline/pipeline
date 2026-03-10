"""VLA Pipeline Runner.

This script serves as an entry point for the VLA pipeline processing.
It parses command line arguments and executes the pipeline processing request (PPR).

Usage:
    casa --nogui --nologger -c runvlapipeline.py <pipeline_processing_request>

Note:
    The argument index calculation accounts for CASA's parameter handling,
    where the script name follows the '-c' flag.
"""
# Import casashell to access command line arguments passed to CASA
import casashell

# Import the module responsible for executing the pipeline processing request
import pipeline.infrastructure.executevlappr as eppr
from pipeline.infrastructure import exceptions, status


def main(argv: list[str] | None = None) -> int:
    """Run the VLA pipeline entrypoint and return a process exit code.

    Args:
        argv: Optional argv sequence. If omitted, use CASA's argv.

    Returns:
        Stable integer process exit code.
    """
    try:
        if argv is None:
            argv = casashell.argv

        ppr_file = argv[argv.index('-c') + 2]
    except (ValueError, IndexError):
        request_error = exceptions.PipelineRequestError(
            'No pipeline processing request was supplied to runvlapipeline.',
            reason_code='missing_ppr_argument',
        )
        status.publish_terminal_exception(request_error, request_path=None, source='runvlapipeline')
        return exceptions.exit_code_for_exception(request_error)

    try:
        eppr.executeppr(ppr_file, importonly=False)
    except (exceptions.PipelineStopRequested, KeyboardInterrupt) as exc:
        status.publish_terminal_exception(exc, request_path=ppr_file, source='runvlapipeline')
        return exceptions.exit_code_for_exception(exc)
    except Exception as exc:
        status.publish_terminal_exception(exc, request_path=ppr_file, source='runvlapipeline')
        return exceptions.exit_code_for_exception(exc)

    status.publish_active_context_completion(source='runvlapipeline')
    return int(exceptions.PipelineExitCode.SUCCESS)

# Only execute the PPR when the script is run directly (not when imported as a module)
if __name__ == '__main__':
    raise SystemExit(main())
