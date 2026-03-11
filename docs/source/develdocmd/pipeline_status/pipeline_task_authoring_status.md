# Pipeline Task Author Guide for Stops and Conditions

## Purpose

This note describes when task authors should raise `PipelineStopRequested`, when they should raise ordinary failure exceptions, and when they should publish structured non-fatal conditions instead.

The goal is to keep task behavior consistent for runners, status artifacts, and weblog rendering.

## Choose the right mechanism

Task authors now have three distinct mechanisms available.

### Raise a failure exception

Use an ordinary pipeline failure exception when the task encountered a real execution error and the run should be classified as failed.

Typical examples:

- invalid task inputs that make execution impossible;
- missing required runtime dependencies;
- a CASA task failure that prevents continuing safely;
- an unexpected internal bug.

This path should lead to failure classification, not to a clean stop.

### Raise `PipelineStopRequested`

Use `PipelineStopRequested` only when the correct outcome is an intentional, controlled early stop.

Typical examples:

- an operator or workflow policy explicitly requested a stop;
- the run reached a deliberate checkpoint and should end cleanly;
- continuing would be misleading or wasteful, but the pipeline is otherwise in a controlled state.

Do not use `PipelineStopRequested` as a substitute for ordinary error handling.

### Publish a condition

Use a structured condition when later stages or operator tooling should know about a non-fatal state, but the run should continue.

Typical examples:

- imaging target-selection notices;
- heuristic parameter overrides;
- size mitigation that changes later behavior without failing the run;
- continuum-selection warnings that should remain visible downstream.

## Guidance for `PipelineStopRequested`

When raising `PipelineStopRequested`, provide:

- a stable `reason_code`;
- a short operator-facing `message`;
- optional structured `details` when the stop reason needs drill-down data.

The `reason_code` should be stable enough for downstream tooling to match on it without scraping the message text.

Recommended properties of a good stop reason code:

- concise;
- machine-readable;
- tied to a stable policy or workflow reason rather than a transient log sentence.

## What not to do

Task authors should avoid the following patterns:

- catching `PipelineStopRequested` and converting it into a failure result;
- logging a warning and continuing when the correct outcome is a deliberate stop;
- encoding downstream control decisions only in free-form log text;
- introducing new ad hoc context dictionaries when an existing condition code or helper already covers the use case.

## Condition authoring guidance

Use the `Context` condition helpers when a task produces non-fatal state that must be visible after the task returns.

Current helper methods are:

- `context.set_condition(...)`;
- `context.clear_condition(...)`;
- `context.get_condition(...)`;
- `context.get_conditions(...)`.

When publishing a condition, provide:

- a stable `code`;
- `severity` reflecting operator visibility;
- `scope` appropriate to the state;
- `disposition` describing the intended downstream behavior;
- a short `message`;
- structured `details` only when a consumer benefits from them.

## When to create a new condition code

Create a new condition code only when all of the following are true:

- the state is not fatal;
- the state must persist beyond the task's local execution;
- a later stage, weblog, or operator tool will consume it;
- a free-form log message is not a sufficient contract.

Do not create condition codes for ordinary working data that is better kept in task-specific context structures.

## Legacy mirror guidance

Some migrated workflows still maintain legacy context dictionaries in parallel with the new condition registry for compatibility.

Task authors should follow these rules:

- prefer the condition registry for any new reader logic;
- keep legacy mirrors only where an existing non-migrated consumer still requires them;
- remove the legacy mirror when the last reader has been moved to the condition-backed helper.

## Review checklist for task changes

Before merging a task that changes stop or condition behavior, verify:

1. real failures still raise failure exceptions;
2. intentional early exits raise `PipelineStopRequested`;
3. non-fatal cross-stage state is published as a condition when needed;
4. the task does not swallow a clean stop in shared wrappers or per-vis loops;
5. any new reason code or condition code is documented and tested.