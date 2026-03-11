# Pipeline status and failure communication plan

## Purpose

This note describes a practical implementation plan for improving how the
pipeline communicates run status, failures, clean early exits, weblog
rendering outcomes, and non-fatal conditions to the production
`pipelinedriver` and to downstream pipeline stages.

The intent is to provide a design that is:

- explicit enough for operations and downstream tooling;
- small enough to implement within a normal development cycle;
- compatible with the current ALMA production entry path;
- understandable by developers, operators, QA, and release stakeholders.

## Scope

The original proposal focused on the ALMA production path. However, the Phase 1
implementation is now being broadened across shared execution paths so that the
common infrastructure does not diverge between ALMA and VLA.

The current target scope is:

- interferometric ALMA recipes (`hifa`);
- single-dish ALMA recipes (`hsd`);
- VLA PPR execution entrypoints where they share the same execution contract;
- shared execution helpers used by both ALMA and VLA task flows, including
  common interferometry support code under `h` and `hif`;
- the production execution path launched through `pipelinedriver`;
- weblog rendering and stage reporting associated with those runs.

The implementation still does not attempt a full cross-observatory workflow
redesign.

## Problem statement

The current production contract is too weak for the needs of both the pipeline
and `pipelinedriver`.

Today:

- some fatal paths raise Python exceptions;
- some fatal paths write `errorexit-*.txt` and return;
- the sentinel file does not carry structured metadata;
- `pipelinedriver` is forced to infer details from side effects or log text;
- there is no single durable source of truth for live status and final outcome;
- there is no standardized mechanism for a stage to request a clean session stop;
- non-fatal conditions are mostly communicated through logs or task-specific
  conventions;
- weblog rendering failures are tracked internally, but are not part of a clear
  production-facing status contract.

## Goals

The implementation should provide the following capabilities.

1. A stable machine-readable contract for run start, stage progression,
   warnings, exceptions, and final outcome.
1. A clean distinction between `failed`, `stopped intentionally`, and
   `completed with non-fatal conditions`.
1. A durable artifact that can be consumed both live and after process exit.
1. A standard mechanism for tasks or stages to request early clean shutdown.
1. A standard mechanism for downstream tasks to inspect non-fatal conditions.
1. Weblog indicators that show when a task or stage failed or stopped.
1. Minimal disruption to the existing task model and rendering stack.

## Non-goals

The first phase should not attempt to do the following.

- redesign the full pipeline task execution framework;
- replace the existing logging system;
- expose a network service or long-lived IPC daemon;
- define a fine-grained exit code for every possible failure cause;
- retrofit all historical task-specific warning patterns at once;
- generalize the solution immediately to VLA.

## Recommended architecture

The recommended solution has three layers.

### Layer 1: terminal process outcome

The subprocess exit status remains useful, but only for coarse process-level
classification.

Recommended terminal classes:

- `0`: success;
- `10`: clean intentional stop;
- `20`: invalid request or configuration;
- `30`: stage or task failure;
- `40`: internal pipeline error.

The exact numeric values are less important than keeping the set small,
documented, and stable.

### Layer 2: structured run status publication

The primary production-facing contract should be a structured status publisher
that emits both:

- an append-only event stream, for example `pipeline-events.jsonl`;
- a latest-state snapshot, for example `pipeline-status.json`.

The append-only stream supports live monitoring and postmortem reconstruction.
The snapshot supports simple polling and recovery after driver restarts.

### Layer 3: in-context workflow conditions

The pipeline context should gain an explicit condition registry for non-fatal
and control-flow-relevant state. This is separate from project metadata and
separate from ordinary log records.

This condition registry is the recommended mechanism for inter-task and
inter-stage communication.

## Why this design fits the current code

The code base already contains useful primitives that reduce implementation
effort.

- Task lifecycle events already exist.
- Weblog stage lifecycle events already exist.
- A timing tracker already persists lifecycle information.
- Top-level task execution already captures warning and attention log records.
- Failed task rendering already exists in the weblog stack.

Because of this, the new implementation should build on existing event and
result structures instead of creating a completely parallel control plane.

## Proposed data model

### Run status snapshot

The latest-state file should contain one JSON object with at least the
following fields.

```json
{
  "schema_version": 1,
  "run_id": "pipeline-20260310T120001",
  "context_name": "pipeline-20260310T120001",
  "observatory": "ALMA",
  "recipe_name": "procedure_hifa_calimage.xml",
  "state": "running",
  "final_disposition": null,
  "reason_code": null,
  "message": null,
  "start_time": "2026-03-10T12:00:01Z",
  "end_time": null,
  "current_stage": 7,
  "current_task": "hifa_bandpass",
  "latest_warning_count": 3,
  "latest_attention_count": 1,
  "conditions": [
    {
      "code": "REPRESENTATIVE_TARGET_FALLBACK",
      "severity": "warning",
      "scope": "run",
      "disposition": "continue"
    }
  ]
}
```

### Event stream records

Each JSON Lines record should carry the fields required to reconstruct the run.

Recommended fields:

- `schema_version`;
- `timestamp`;
- `run_id`;
- `context_name`;
- `event_type`;
- `state`;
- `stage_number`;
- `task_name`;
- `severity`;
- `reason_code`;
- `message`;
- `exception_type`;
- `traceback_excerpt`;
- `payload`.

Recommended event types:

- `run_started`;
- `run_resumed`;
- `run_finished`;
- `run_failed`;
- `run_stopped`;
- `stage_started`;
- `stage_completed`;
- `stage_failed`;
- `stage_stopped`;
- `result_accepting`;
- `result_accepted`;
- `result_error`;
- `weblog_stage_started`;
- `weblog_stage_completed`;
- `weblog_stage_failed`;
- `log_message`;
- `condition_raised`;
- `condition_cleared`.

### Condition registry

The context should gain a dedicated container, for example
`context.conditions`, storing structured condition objects.

Recommended condition fields:

- `code`;
- `severity`;
- `scope`;
- `disposition`;
- `message`;
- `details`;
- `producer_stage`;
- `producer_task`;
- `created_at`;
- `updated_at`;
- `active`.

Recommended dispositions:

- `continue`;
- `skip_stage`;
- `stop_run_clean`;
- `fail_run`.

## Exception and control model

The implementation should distinguish three classes of exceptional control
flow.

### Fatal execution errors

Fatal execution errors should continue to use exceptions, but they should be
normalized into a small, typed hierarchy. Example categories include:

- invalid request or malformed input;
- configuration or environment error;
- task execution failure;
- result acceptance failure;
- internal pipeline bug.

### Clean early-stop requests

Stages that need to stop the session cleanly should raise a dedicated control
exception, for example `PipelineStopRequested`.

This exception should include:

- a stable `reason_code`;
- a user-facing `message`;
- an optional `details` payload;
- an indication of whether the stop is immediate or after-stage.

This exception is not a failure. It is a controlled outcome that should become
both a status event and a distinct final disposition.

### Non-fatal conditions

Recoverable issues should not rely on free-form log parsing when later stages
must make decisions based on them. Instead, the producing stage should record a
condition in the context registry and optionally emit a structured status event.

## Weblog behavior

The weblog should show the difference between:

- a task that failed;
- a task that stopped intentionally;
- a task that completed with warnings or non-fatal conditions;
- a stage whose weblog rendering failed.

The existing failed-task renderer can be extended rather than replaced. The
implementation should add a small amount of execution-state metadata to task
results so the renderer can display `failed` versus `stopped` explicitly.

Recommended visible changes:

- a `failed` or `stopped` label on the task detail page;
- stage summary badges that distinguish abnormal exit from intentional stop;
- a visible indicator when weblog rendering itself failed for a stage;
- an optional section listing active non-fatal conditions relevant to the
  stage.

## Implementation workstreams

The work should be organized into six workstreams.

### Workstream A: normalize fatal handling in shared execution paths

Objective: remove ambiguity at the process boundary.

Tasks:

- identify fatal paths in shared and PPR execution code that currently write
  `errorexit-*` and return;
- replace those paths with typed exceptions;
- preserve product export and context save behavior where required;
- handle exception-to-exit-code mapping once at the ALMA entrypoint.

Deliverable:

- runner entrypoints and shared execution paths use intentional and documented
  process semantics.

### Workstream B: add a status publisher

Objective: publish structured run and stage status with minimal invasive
changes.

Tasks:

- implement a status publisher class that subscribes to lifecycle events;
- write JSON Lines events;
- write a latest-state JSON snapshot atomically;
- ensure artifacts are written in a stable and documented location;
- include schema versioning from day one.

Deliverable:

- one append-only event stream and one latest-state snapshot per ALMA run.

### Workstream C: add a structured elevated-log bridge

Objective: expose elevated log records without requiring log scraping.

Tasks:

- attach a dedicated handler or bridge for `WARNING`, `ATTENTION`, `ERROR`,
  and `CRITICAL`;
- emit structured `log_message` events with stage and task attribution where
  possible;
- document which severities are considered driver-visible.

Deliverable:

- `pipelinedriver` can react to elevated messages without parsing plain text.

### Workstream D: add clean early-stop control flow

Objective: allow stages or workflow logic to request a clean session stop.

Tasks:

- introduce `PipelineStopRequested` or equivalent control exception;
- define stop reason codes;
- handle the exception in the ALMA execution wrapper;
- publish `run_stopped` and `stage_stopped` events;
- render the stopped state in the weblog.

Deliverable:

- deterministic, user-visible early-stop behavior.

### Workstream E: add context conditions

Objective: support non-fatal inter-stage communication.

Tasks:

- add a condition registry to `Context`;
- provide helper methods to add, clear, and query conditions by code and
  severity;
- define an initial small vocabulary of condition codes;
- update selected high-value ALMA stages to use the condition registry.

Deliverable:

- downstream tasks have a supported way to inspect prior recoverable issues.

### Workstream F: weblog status improvements

Objective: expose task and stage execution state clearly in the weblog.

Tasks:

- add result metadata for execution state and status reason;
- update task detail rendering to show `failed` versus `stopped`;
- surface weblog rendering failures in stage summaries;
- consider showing active conditions and elevated messages per stage.

Deliverable:

- weblog reflects run and stage outcomes accurately, including partial failure.

## Recommended rollout phases

### Phase 0: design and agreement

Duration: short design phase before coding.

Outputs:

- approved status schema;
- approved exit-code mapping;
- approved condition-code vocabulary for initial rollout;
- agreement on artifact locations and retention;
- agreement on whether `pipelinedriver` consumes events live, snapshot-only,
  or both.

### Phase 1: fatal-path normalization in shared execution paths

Primary value: immediate production clarity.

Outputs:

- shared fatal paths raise typed exceptions consistently;
- ALMA and VLA runner entrypoints map exceptions to stable exit codes;
- legacy `errorexit-*` behavior either becomes optional compatibility output or
  is formally deprecated.

### Phase 2: status publisher and final snapshot

Primary value: machine-readable run visibility.

Outputs:

- lifecycle-driven event emission;
- final snapshot publication;
- driver can consume final state without log parsing.

### Phase 3: live updates and elevated message bridge

Primary value: operational monitoring.

Outputs:

- stage transitions are visible to `pipelinedriver`;
- elevated log messages are exposed as structured events;
- start and end times are available through status artifacts rather than
  inferred.

### Phase 4: clean early-stop support

Primary value: controlled workflow interruption.

Outputs:

- tasks can request a clean stop with stable semantics;
- driver and weblog can distinguish stop from failure.

### Phase 5: context conditions and selective stage adoption

Primary value: downstream decision support.

Outputs:

- condition registry implemented;
- first set of ALMA stages migrated to emit structured conditions;
- downstream stages consume those conditions where needed.

### Phase 6: broader adoption and cleanup

Primary value: consolidation.

Outputs:

- retire or formally demote the old sentinel file contract;
- document long-term support expectations;
- decide whether to generalize to VLA.

## Stakeholder education plan

This work changes both operational expectations and developer behavior, so it
requires a documentation and communication track alongside the code changes.

### Stakeholder groups

- ALMA pipeline developers;
- `pipelinedriver` developers and operators;
- QA and validation teams;
- release managers;
- users who read weblogs for failure diagnosis.

### Education topics

- what counts as `failed`, `stopped`, and `completed with conditions`;
- where the new status artifacts live;
- how to interpret exit codes;
- how to consume the event stream and snapshot;
- how tasks should request early stop;
- how tasks should publish non-fatal conditions;
- how weblog indicators map to execution states.

### Recommended communication artifacts

- a short architecture note for developers;
- a schema reference for event and snapshot JSON;
- an operator guide for `pipelinedriver` integration;
- a migration guide from `errorexit-*` behavior;
- a task-author guide for stop requests and condition publishing;
- release notes summarizing observable behavior changes.

## Documentation deliverables

The documentation work should be treated as part of the implementation, not as
follow-up work.

Recommended documentation set:

1. This implementation plan.
1. A status schema reference, including JSON examples.
1. An ALMA operations integration guide for `pipelinedriver`.
1. A developer guide for emitting conditions and stop requests.
1. A weblog behavior note describing new badges, labels, and failure states.
1. Release notes for the first production rollout.

## Testing strategy

Testing should be organized by contract rather than only by unit coverage.

### Contract tests

- a fatal ALMA run returns the documented exit code;
- a clean stop returns the documented stop code;
- `pipeline-status.json` contains the final state and reason code;
- `pipeline-events.jsonl` contains ordered lifecycle records;
- elevated log messages appear as structured events;
- weblog rendering failure produces a structured record and visible indicator.

### Integration tests

- ALMA interferometry recipe with successful completion;
- ALMA interferometry recipe with fatal task failure;
- ALMA single-dish recipe with successful completion;
- ALMA single-dish recipe with intentional stop;
- resume path if resume remains in scope for production.

### Backward-compatibility tests

- optional compatibility sentinel file behavior, if retained;
- existing context save and export behavior on failure;
- existing weblog generation paths for successful runs.

## Acceptance criteria

The first production-ready implementation should meet the following minimum
acceptance criteria.

1. Every ALMA fatal run ends with a typed failure classification and stable
   non-zero exit code.
1. Every ALMA production run writes a final structured status snapshot.
1. Stage transitions are available as structured events.
1. Clean early-stop requests are distinguishable from failures.
1. Weblog task detail pages visibly distinguish failed and stopped tasks.
1. At least one initial set of non-fatal conditions is recorded in the
   context and queryable downstream.
1. `pipelinedriver` no longer needs to infer terminal failure specifics from
   `errorexit-*` or ad hoc log parsing.

## Risks and mitigations

### Risk: scope expands into a full workflow redesign

Mitigation: keep the first implementation ALMA-only and focused on the status
contract.

### Risk: too many reason codes or condition codes appear too early

Mitigation: begin with a small controlled vocabulary and extend only when a
clear consumer exists.

### Risk: event artifacts become another unmaintained side channel

Mitigation: define the status publisher as the supported production contract
and document ownership clearly.

### Risk: stakeholders keep using log parsing out of habit

Mitigation: provide an operator guide and deprecate string-based integration in
release notes.

### Risk: implementation diverges between ALMA interferometry and single-dish

Mitigation: centralize the status publisher and control exceptions in shared
ALMA execution infrastructure.

## Open decisions

The following decisions should be made in Phase 0.

1. Whether compatibility `errorexit-*` files should be retained temporarily.
1. The canonical location and retention policy for status artifacts.
1. The initial exit-code mapping.
1. The initial condition-code vocabulary.
1. Whether the driver consumes live events, final snapshot, or both.
1. Whether result metadata or a new result class is preferred for `stopped`
   tasks in the weblog.

## Suggested implementation order

If the work must be split across multiple tickets, the recommended order is:

1. fatal-path normalization and typed exceptions;
1. exit-code mapping at the ALMA runner entrypoint;
1. status publisher for final snapshot;
1. event-stream publication from existing lifecycle events;
1. clean early-stop exception and handling;
1. context condition registry;
1. weblog status refinements;
1. documentation and driver adoption cleanup.

This order gives operations value early while keeping risk manageable.