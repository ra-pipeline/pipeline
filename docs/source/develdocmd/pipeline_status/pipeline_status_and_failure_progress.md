# Pipeline Status and Failure Implementation Progress

## Purpose

This note records the current implementation status of the pipeline status and
failure communication work.

It is intended to complement, not replace, the following existing documents:

- `pipeline_status_and_failure_plan.md` for the design and rollout plan;
- `pipeline_status_schema.md` for the structured artifact schema;
- `pipeline_exit_semantics.md` for the current exit behavior contract;
- `pipeline_phase1_reason_codes.md` for the shared exit code and reason code
  reference.

This document reflects the implementation state as of March 2026.

## Summary

The work is no longer only a design proposal.

The codebase now includes:

- stable process exit codes across the main ALMA and VLA runners;
- typed shared exceptions for request errors, task failures, internal errors,
  and intentional stop requests;
- structured run status artifacts:
  - `pipeline-status.json`;
  - `pipeline-events.jsonl`;
- live structured `log_message` export for elevated log records while tasks are
  still running;
- clean-stop flow with distinct `stage_stopped` and `run_stopped` events;
- initial weblog support for displaying intentionally stopped stages;
- run-level weblog status and active-condition summaries on the home and topic
  pages;
- a shared `Context` condition registry for structured non-fatal cross-stage
  state;
- initial Phase 5 adoption for imaging target-selection notices and
  checkproductsize mitigation state.

## Current Coverage

The current implementation covers more than the original ALMA production
entrypoint.

### Shared execution contract

The shared execution and exit contract now covers:

- `pipeline/infrastructure/exceptions.py`;
- `pipeline/infrastructure/basetask.py`;
- `pipeline/infrastructure/status.py`;
- `pipeline/infrastructure/eventbus/events.py`.

This means the stop/failure distinction is defined once in shared
infrastructure rather than only in a single runner.

### Entry points and execution paths

The current implementation reaches the following execution paths:

- ALMA PPR execution through `executeppr` and `runpipeline`;
- VLA PPR execution through `executevlappr` and `runvlapipeline`;
- recipe execution through `recipereducer`;
- explicit task-list execution through `recipereducer.run_named_tasks(...)`;
- shared helper task execution in `h/cli/utils.py` and `mpihelpers.py`.

### Weblog visibility

The weblog now distinguishes stopped stages from failed stages in the task
views by synthesizing stopped-stage entries from `pipeline-events.jsonl`.

This is intentionally renderer-driven. The implementation does not force a
synthetic stopped result into the saved pipeline context just to satisfy the
weblog.

## Implemented Workstreams

The implementation status against the plan is as follows.

### Workstream A: terminal outcome contract

Implemented.

Current stable exit codes are:

- `0`: success;
- `10`: intentional clean stop;
- `20`: invalid request or configuration;
- `30`: stage or task failure;
- `40`: internal error.

### Workstream B: structured run status publication

Implemented in the initial production-ready form.

Current artifacts:

- `pipeline-events.jsonl`:
  append-only event stream for live and postmortem consumption;
- `pipeline-status.json`:
  latest-state snapshot written atomically.

Current event types in use include:

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
- `log_message`.

### Workstream C: structured elevated log bridge

Implemented.

Elevated log records are now exported live through the shared logging layer
while a task is running. This avoids the earlier limitation where structured
messages only appeared after a `Result` was accepted.

### Workstream D: clean early-stop control flow

Implemented in the shared execution contract.

Current behavior:

- `PipelineStopRequested` represents intentional early termination;
- top-level tasks emit `TaskStoppedEvent`;
- status publication exports `stage_stopped` and `run_stopped`;
- runners return exit code `10` for intentional stops;
- `recipereducer` propagates the same stop semantics.

### Workstream E: context conditions

Implemented for the current selective rollout.

The current implementation now provides:

- a structured condition registry on `Context`;
- helper methods to raise, clear, and query conditions by code;
- `condition_raised` and `condition_cleared` status events;
- snapshot publication of the active condition set;
- compatibility helpers so migrated readers can prefer the registry while old
  context dictionaries remain available.

The first adopted condition codes are:

- `imaging_target_selection_notice`:
  used for non-fatal imaging target-selection messages such as no targets or no
  check source data;
- `continuum_selection_warning`:
  used for non-fatal `hif_findcont` warnings such as narrow continuum ranges,
  internal continuum-finder warnings, or target selections dropped from later
  continuum imaging;
- `imaging_parameter_override`:
  used for heuristic robust and uvtaper overrides published by
  `hifa_imageprecheck` for later imaging stages;
- `size_mitigation`:
  used for mitigation settings and blocking mitigation failures published by
  `hif_checkproductsize`.

Current selective adoption covers the shared interferometric imaging flow:

- `hif_checkproductsize` publishes the size-mitigation condition;
- `hif_findcont` publishes structured continuum-selection warnings;
- `hifa_imageprecheck` publishes imaging-parameter override state;
- `hif_makeimlist` publishes imaging target-selection notices;
- `hif_makeimages`, `hif_findcont`, `hif_uvcontsub`, `hif_makeimlist`,
  `hif_editimlist`, and `hif_checkproductsize` now read condition-backed
  compatibility helpers.

The current Phase 5 rollout is considered complete at this point.

An additional audit was performed for the remaining `selfcal` context state.
That review found that `context.selfcal_targets` is still best treated as
ordinary shared working data rather than a condition family. Downstream
consumers in `hif_makeimlist` depend on detailed per-target solver outputs such
as `sc_success`, `sc_lib`, and `sc_rms_scale`, not on a compact non-fatal
operator-facing summary.

If a future extension is needed, the likely next step would be a small summary
condition for selfcal availability or restore readiness, not migration of the
full `selfcal_targets` payload.

### Workstream F: weblog status improvements

Implemented for the current scope.

Implemented now:

- stopped stages are visible in the By Task weblog views;
- stopped stages get a dedicated detail page;
- stopped stages are labeled distinctly from failed stages;
- home-page and topic-page weblog views show a run-level status banner for
  clean stops, failures, and runs that ended with active conditions;
- home-page and topic-page weblog views surface the active condition set from
  `pipeline-status.json`.

Still pending:

- any rendering tied to future context conditions.

## Current Output Contract

### Snapshot file

The current `pipeline-status.json` snapshot includes fields such as:

- `schema_version`;
- `run_id`;
- `context_name`;
- `observatory`;
- `recipe_name`;
- `state`;
- `final_disposition`;
- `reason_code`;
- `message`;
- `start_time`;
- `end_time`;
- `current_stage`;
- `current_task`;
- `latest_warning_count`;
- `latest_attention_count`;
- `conditions`;
- `output_dir`;
- `exit_code` when terminal outcome is known;
- `source` when terminal outcome is known.

### Event stream file

The current `pipeline-events.jsonl` stream includes fields such as:

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

## Remaining Gaps

The following pieces remain unfinished relative to the broader plan.

- a broader rollout of structured conditions beyond the current imaging-state
  adoption;
- future rendering tied to newly added condition families beyond the current
  weblog scope.

## Documentation Follow-up

The original documentation cleanup items are now covered by dedicated notes:

- `pipeline_status_operator_guide.md` for artifact consumption by operators and
  downstream tooling;
- `pipeline_task_authoring_status.md` for stop-request and condition-publishing
  guidance for task authors;
- `pipeline_status_contract_transition.md` for retirement planning around
  legacy `errorexit-*` files and context-mirror compatibility.

## Practical Interpretation

The current implementation should be understood as a working shared execution
contract, not as a PPR-only special case.

The most important practical consequences are:

- downstream tooling can distinguish `success`, `failure`, and
  `intentional stop` without scraping logs;
- long-running tasks can emit machine-readable elevated log messages while they
  are still executing;
- downstream stages now have a supported shared registry for selected non-fatal
  imaging conditions instead of relying only on ad hoc context dictionaries;
- the weblog can now represent stopped stages separately from failed stages;
- recipe and task-list execution paths can participate in the same stop and
  failure model as PPR-based execution.