# Pipeline Status Artifact Operator Guide

## Purpose

This note describes how operators and downstream tooling should consume the structured pipeline status artifacts that are now emitted for ALMA and VLA execution paths sharing the common runner contract.

It is a practical usage guide for `pipelinedriver`-style integrations. For the full schema, see `pipeline_status_schema.md`. For exit-code semantics, see `pipeline_exit_semantics.md`.

## Supported artifacts

The supported production-facing contract is now:

- process exit code for coarse terminal classification;
- `pipeline-status.json` for latest known state;
- `pipeline-events.jsonl` for ordered lifecycle history.

Legacy `errorexit-*` files may still appear in some fatal PPR compatibility paths, but they should be treated as transitional output only.

## Artifact locations

The status artifacts are written into the pipeline run output directory, next to the saved context and weblog products.

Operators should treat the run output directory as the canonical location for all three of the following:

- the status snapshot;
- the event stream;
- the generated weblog.

## File roles

### `pipeline-status.json`

Use the snapshot when a consumer needs the current answer to questions such as:

- is the run still active;
- what is the latest stage or task;
- what terminal outcome was reached;
- are any active structured conditions still present.

The snapshot is intended for:

- polling;
- restart recovery after a consumer restart;
- final terminal classification without replaying the event stream.

### `pipeline-events.jsonl`

Use the event stream when a consumer needs ordered history such as:

- run start and stop boundaries;
- stage transitions;
- elevated log records during active execution;
- condition lifecycle changes;
- weblog stage lifecycle.

The event stream is intended for:

- live monitoring;
- postmortem reconstruction;
- audit-style consumption.

## Recommended consumption order

For robust integrations, consume the artifacts in this order:

1. Use the process exit code for coarse success, stop, or failure handling.
2. Read `pipeline-status.json` for the authoritative final disposition, reason code, and operator-facing message.
3. Use `pipeline-events.jsonl` when detailed timing, stage history, or live elevated messages are needed.

If the snapshot and exit code disagree, prefer the snapshot unless the process terminated before the snapshot could be updated. In that case, the event stream and runner logs should be used to diagnose an incomplete terminal write.

## Terminal interpretation

### Success

Treat the run as successful when all of the following are true:

- exit code is `0`;
- snapshot `state` is `completed`;
- snapshot `final_disposition` is `success`.

Warnings and active conditions do not automatically change success into failure. They indicate that the run completed with additional operator-visible state.

### Intentional stop

Treat the run as intentionally stopped when the terminal contract shows:

- exit code `10`;
- snapshot `state` is `stopped`;
- snapshot `final_disposition` is `clean_stop`.

This is not a crash. Downstream automation should avoid folding this outcome into the same bucket as execution failures.

### Failure

Treat the run as failed when the terminal contract shows:

- exit code `20`, `30`, or `40`;
- snapshot `state` is `failed`;
- snapshot `final_disposition` is `invalid_request`, `task_failure`, or
  `internal_error`.

## Active conditions

The snapshot `conditions` array contains the active structured condition set at the time of the latest write.

Consumers should treat these as non-fatal state unless the individual condition's `disposition` explicitly indicates otherwise.

Current examples include:

- imaging target-selection notices;
- continuum-selection warnings;
- imaging parameter overrides;
- size-mitigation state.

For operator-facing displays, the recommended presentation is:

- show condition `code`, `severity`, and `message`;
- keep `details` available for drill-down rather than forcing them into a one-line summary;
- do not infer failure only from the presence of conditions.

## Live monitoring guidance

For live monitoring:

- watch the snapshot for current state and latest stage;
- tail the event stream for new lifecycle records;
- treat `log_message` records as the supported elevated-log bridge;
- treat `condition_raised` and `condition_cleared` as the supported condition lifecycle feed.

Consumers should assume that event delivery is append-only and ordered by emission time, not by later file timestamp normalization.

## Recovery and restart behavior

If a consumer restarts during a run:

1. read `pipeline-status.json` first;
2. resume event consumption from the last processed line in `pipeline-events.jsonl`;
3. reconcile the final snapshot again when the run terminates.

This avoids reconstructing terminal state entirely from historical event replay.

## Compatibility guidance

The old `errorexit-*` files should no longer be used as the primary contract for any new consumer work.

Use them only as a temporary fallback while older integrations are being retired.

The long-term supported interface is the combination of:

- stable exit code;
- structured status snapshot;
- structured event stream.