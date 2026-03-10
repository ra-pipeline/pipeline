# Phase 1 exit codes and reason codes

## Purpose

This note documents the current Phase 1 terminal failure contract introduced in
the shared execution layer and runner entrypoints.

It is intentionally limited to process outcomes and the first set of reason
codes. It does not yet define the full Phase 2 event publication layer.

## Exit codes

Phase 1 uses a small, stable set of terminal process exit codes defined in
`pipeline.infrastructure.exceptions.PipelineExitCode`.

| Exit code | Meaning |
| --- | --- |
| `0` | Successful completion |
| `10` | Clean intentional stop |
| `20` | Invalid request or configuration |
| `30` | Stage or task failure |
| `40` | Internal pipeline error |

## Exception classes

Phase 1 currently uses the following shared exception classes.

| Exception | Exit code | Meaning |
| --- | --- | --- |
| `PipelineException` | `30` by default | Base class for pipeline failures |
| `PipelineRequestError` | `20` | Invalid request, missing input, or missing initialization |
| `PipelineTaskExecutionError` | `30` | Stage or task execution failure |
| `PipelineInternalError` | `40` | Unexpected internal pipeline failure |

## Initial reason codes

The following reason codes are now in use in the shared Phase 1 code.

| Reason code | Meaning |
| --- | --- |
| `missing_ppr_argument` | Runner launched without the required PPR argument |
| `request_analysis_failed` | Failure while decoding or preparing the request |
| `undefined_relative_data_path` | Request did not define a valid relative path |
| `empty_asdm_list` | Request contained no ASDM entries |
| `empty_commands_list` | Request contained no stage commands |
| `pipeline_not_initialized` | Task execution requested without `h_init()` or `h_resume()` |
| `task_execution_failed` | Stage or task produced a traceback or raised an execution failure |
| `mpi_task_execution_failed` | Tier0 or MPI-mediated task failed remotely |
| `sync_task_execution_failed` | Synchronous helper task failed locally |

## Compatibility behavior

Phase 1 preserves the legacy `errorexit-*` file behavior as a compatibility
side effect in the PPR execution paths. This file is no longer the primary
failure signaling mechanism for terminal process behavior.

In other words:

- the process exit code is now intentional and stable;
- the compatibility file is still created in the current PPR fatal paths;
- later phases should migrate consumers away from the compatibility file.

## Current coverage

Phase 1 coverage currently includes:

- `executeppr` request and task fatal paths;
- `executevlappr` request and task fatal paths;
- `runpipeline` process exit mapping;
- `runvlapipeline` process exit mapping;
- selected shared execution helpers in `h/cli/utils.py`, `recipereducer.py`,
  and `mpihelpers.py`.

## Follow-up guidance

Before Phase 2, new reason codes should only be added when both of the
following are true:

1. The new code represents a stable semantic class rather than a one-off error.
1. There is a clear consumer for that distinction, even if the consumer is only
   unit tests and documentation at first.