# Exit Codes and Reason Codes

## Purpose

This note documents the current terminal exit contract used by the shared execution layer and runner entrypoints.

It is intentionally focused on process outcomes and the currently supported set of reason codes. For the broader status artifact model, see `pipeline_status_schema.md` and `pipeline_exit_semantics.md`.

## Exit codes

The pipeline uses a small, stable set of terminal process exit codes defined in `pipeline.infrastructure.exceptions.PipelineExitCode`.

| Exit code | Meaning |
| --- | --- |
| `0` | Successful completion |
| `10` | Clean intentional stop |
| `20` | Invalid request or configuration |
| `30` | Stage or task failure |
| `40` | Internal pipeline error |

## Exception classes

The shared execution contract currently uses the following exception classes.

| Exception | Exit code | Meaning |
| --- | --- | --- |
| `PipelineException` | `30` by default | Base class for pipeline failures when no more specific terminal class applies |
| `PipelineRequestError` | `20` | Invalid request, missing input, or missing initialization |
| `PipelineTaskExecutionError` | `30` | Stage or task execution failure |
| `PipelineStopRequested` | `10` | Intentional clean stop requested by task or workflow control |
| `PipelineInternalError` | `40` | Unexpected internal pipeline failure |

`PipelineException` and `PipelineTaskExecutionError` intentionally share the same exit code because both belong to the coarse `task_failure` terminal outcome class. The exception type and any associated `reason_code` provide the finer-grained distinction.

## Additional terminal mappings

Not every terminal outcome comes from a typed pipeline exception.

The shared `exit_code_for_exception(...)` helper also maps:

- `KeyboardInterrupt` to exit code `10` (`STOPPED`);
- any other unclassified exception to exit code `40` (`INTERNAL_ERROR`).

## Current reason codes

The following reason codes are currently used in the shared execution and runner code.

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

Legacy `errorexit-*` files are still preserved as a compatibility side effect in the current PPR fatal paths. They are no longer the primary terminal failure-signaling mechanism.

In practice:

- the process exit code is now intentional and stable;
- the compatibility file may still be created in current fatal PPR paths;
- consumers should migrate toward the structured exit/status contract rather than depending on the compatibility file.

## Current coverage

The current exit and reason-code contract covers:

- `executeppr` request and task fatal paths;
- `executevlappr` request and task fatal paths;
- `runpipeline` process exit mapping;
- `runvlapipeline` process exit mapping;
- selected shared execution helpers in `h/cli/utils.py`, `recipereducer.py`, and `mpihelpers.py`.

## Guidance for adding new reason codes

New reason codes should be added only when both of the following are true:

1. The new code represents a stable semantic class rather than a one-off error.
2. There is a clear consumer for that distinction, even if that consumer is currently only tests and documentation.