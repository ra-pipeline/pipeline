# Pipeline Exit Semantics

## Purpose

This note describes how the pipeline can exit today and how those outcomes should be interpreted by developers, operators, and downstream tooling.

It documents the implementation as it exists now, not the larger future-state design.

For operator-facing artifact consumption, see `pipeline_status_operator_guide.md`.

For task-author guidance on clean stops and conditions, see `pipeline_task_authoring_status.md`.

## The Three Main Terminal Outcomes

At a high level, the current pipeline distinguishes three operationally
important outcomes:

1. successful completion;
2. intentional clean stop;
3. failure.

This distinction is visible in stable exit codes, structured status artifacts, and now the weblog.

## Successful Completion

### Meaning

A successful run completed the intended workflow path and reached normal run termination.

### Terminal behavior

- process exit code: `0`;
- structured run event: `run_finished`;
- final disposition: `success`;
- final run state: `completed`.

### Typical trigger

Normal completion of the entrypoint without a raised pipeline exception.

### Operational interpretation

The pipeline did what it intended to do for that execution path.

This does not mean there were no warnings or attentions. It only means the run completed normally.

## Intentional Clean Stop

### Meaning

A clean stop means the pipeline ended early on purpose.

This is not a failure. It indicates that continuing the workflow was not the desired action, but the pipeline remained in a controlled state.

### Terminal behavior

- process exit code: `10`;
- structured stage event: `stage_stopped`;
- structured run event: `run_stopped`;
- final disposition: `clean_stop`;
- final run state: `stopped`.

### Primary trigger

The shared control mechanism is `PipelineStopRequested`.

Tasks or workflow logic can raise this exception to request intentional early termination.

### Secondary trigger

`KeyboardInterrupt` is also mapped to the stopped terminal class at the runner level.

However, this is not identical to an in-task `PipelineStopRequested`:

- it produces a stopped terminal outcome;
- it does not necessarily produce a stage-level stopped event from inside a task.

### Typical use cases

Examples include:

- an operator-initiated stop request;
- a workflow guard condition that decides the run should end early;
- a controlled stop after a known checkpoint;
- future policy-driven stop logic based on structured conditions.

### Operational interpretation

The run ended intentionally and should not be treated as a crash or traceback failure.

Partial products and saved context may still be meaningful.

## Failure

### Meaning

A failure means the pipeline encountered an error condition that prevented the run from continuing normally.

### Terminal behavior

Failure is intentionally split into multiple stable terminal classes.

- `20`: invalid request or configuration;
- `30`: stage or task failure;
- `40`: internal pipeline error.

Structured terminal outcomes include:

- `run_failed`;
- final disposition `invalid_request`, `task_failure`, or `internal_error`.

Stage-level failure is currently represented as:

- `stage_failed`.

### Typical triggers

Examples include:

- invalid or incomplete request content;
- a task returning tracebacks;
- an unhandled exception during execution;
- an unexpected internal error in shared infrastructure.

### Operational interpretation

This is an error outcome and should be treated differently from a clean stop.

In a failure case, downstream tooling should assume the run did not terminate on a planned control path.

## Comparison Summary

| Outcome | Exit code | Run event | Stage event | Final disposition | Interpretation |
| --- | --- | --- | --- | --- | --- |
| Success | `0` | `run_finished` | `stage_completed` | `success` | Normal completion |
| Clean stop | `10` | `run_stopped` | `stage_stopped` | `clean_stop` | Intentional early termination |
| Invalid request | `20` | `run_failed` | none or partial | `invalid_request` | Request or setup problem |
| Task failure | `30` | `run_failed` | `stage_failed` | `task_failure` | Stage or task error |
| Internal error | `40` | `run_failed` | none or partial | `internal_error` | Unexpected infrastructure error |

## Entry Point Coverage

The current shared implementation covers:

- ALMA PPR execution;
- VLA PPR execution;
- `runpipeline` and `runvlapipeline` terminal runners;
- `recipereducer.reduce(...)`;
- explicit task-list execution through `recipereducer.run_named_tasks(...)`;
- shared top-level task execution through `StandardTaskTemplate.execute(...)`.

## Compatibility Behavior

Legacy `errorexit-*` files are still preserved in the existing fatal PPR compatibility paths.

That compatibility behavior should not be treated as the primary exit contract.

The primary contract is now:

- stable process exit code;
- structured status snapshot;
- structured event stream.

## Current Limitations

The current implementation has a few intentional boundaries.

- `PipelineStopRequested` is the primary in-pipeline clean-stop mechanism. There is not yet a broad set of production tasks that raise it automatically.
- `KeyboardInterrupt` is classified as stopped at the runner boundary, but does not currently provide the same rich stage-level semantics as an in-task stop request.
- structured context conditions exist today only for the current selective imaging-state rollout, not yet for all potential cross-stage state.

## Guidance for Developers

Use `PipelineStopRequested` when the correct behavior is to end the run intentionally and preserve that distinction for tooling and operators.

Do not use it for ordinary errors.

Use ordinary pipeline failure exceptions when the pipeline encountered a real execution problem rather than a deliberate control-flow decision.

For authoring guidance beyond this short summary, use `pipeline_task_authoring_status.md` as the primary task-level reference.