# Pipeline status schema reference

## Purpose

This note defines the current structured data model for pipeline run status publication.

The schema described here is intentionally small. It documents the current supported contract rather than predicting every future field.

## Design principles

- prefer stable, explicit keys over ad hoc nested payloads;
- keep terminal process outcome separate from live execution status;
- make records understandable to developers and operators;
- version the schema from the first published artifact;
- allow new optional fields to be added without breaking older consumers.

## Artifact set

The status publication layer emits two artifacts.

### Event stream

Filename: `pipeline-events.jsonl`

Properties:

- append-only;
- one JSON object per line;
- ordered by emission time;
- suitable for live consumption and postmortem reconstruction.

### Latest-state snapshot

Filename: `pipeline-status.json`

Properties:

- one JSON object representing the latest known run state;
- written atomically by temporary file plus rename;
- suitable for polling and recovery after consumer restart.

## Common fields

The following fields should be common to both artifacts where applicable.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `schema_version` | integer | yes | Initial value should be `1`. |
| `run_id` | string | yes | Stable identifier for the pipeline run. |
| `context_name` | string | yes | Pipeline context name. |
| `observatory` | string | yes | Example: `ALMA`, `VLA`. |
| `recipe_name` | string | no | Procedure or recipe identifier if known. |
| `reason_code` | string or null | no | Stable machine-readable classification. |
| `message` | string or null | no | Short operator-readable message. |
| `timestamp` | string | event only | UTC ISO-8601 time for the event. |

## Snapshot schema

### Required fields

| Field | Type | Notes |
| --- | --- | --- |
| `schema_version` | integer | Current schema version. |
| `run_id` | string | Stable run identifier. |
| `context_name` | string | Current pipeline context name. |
| `state` | string | Current run state. |
| `start_time` | string or null | UTC ISO-8601 timestamp. |
| `end_time` | string or null | UTC ISO-8601 timestamp. |

### Optional fields

| Field | Type | Notes |
| --- | --- | --- |
| `observatory` | string | Observatory name. |
| `recipe_name` | string | Procedure or recipe name. |
| `final_disposition` | string or null | Final terminal classification when known. |
| `reason_code` | string or null | Stable reason code for the latest terminal or warning state. |
| `message` | string or null | Human-readable summary. |
| `current_stage` | integer or null | Current stage number when running. |
| `current_task` | string or null | Current task name when known. |
| `latest_warning_count` | integer | Warning count visible to status consumers. |
| `latest_attention_count` | integer | Attention count visible to status consumers. |
| `conditions` | array | Active structured conditions. |

### State vocabulary

Current `state` values:

- `initializing`
- `running`
- `stopping`
- `stopped`
- `failed`
- `completed`

### Final disposition vocabulary

Current `final_disposition` values:

- `success`
- `clean_stop`
- `invalid_request`
- `task_failure`
- `internal_error`

## Event schema

### Required fields

| Field | Type | Notes |
| --- | --- | --- |
| `schema_version` | integer | Current schema version. |
| `timestamp` | string | UTC ISO-8601 event timestamp. |
| `run_id` | string | Stable run identifier. |
| `context_name` | string | Pipeline context name. |
| `event_type` | string | Event classifier. |

### Optional fields

| Field | Type | Notes |
| --- | --- | --- |
| `state` | string or null | State associated with the event. |
| `stage_number` | integer or null | Stage number when applicable. |
| `task_name` | string or null | Task name when applicable. |
| `severity` | string or null | Log or condition severity. |
| `reason_code` | string or null | Stable machine-readable classification. |
| `message` | string or null | Human-readable summary. |
| `exception_type` | string or null | Exception class name if applicable. |
| `traceback_excerpt` | string or null | Short traceback excerpt, not necessarily the full traceback. |
| `payload` | object or null | Extensible detail payload. |

### Event vocabulary

Current `event_type` values:

- `run_started`
- `run_resumed`
- `run_finished`
- `run_failed`
- `run_stopped`
- `stage_started`
- `stage_completed`
- `stage_failed`
- `stage_stopped`
- `result_accepting`
- `result_accepted`
- `result_error`
- `weblog_stage_started`
- `weblog_stage_completed`
- `weblog_stage_failed`
- `log_message`
- `condition_raised`
- `condition_cleared`

## Condition schema

Conditions are designed for cross-stage and cross-task communication of non-fatal and control-relevant state.

The current implementation publishes active conditions in `pipeline-status.json` and emits `condition_raised` / `condition_cleared` records in `pipeline-events.jsonl`.

### Required condition fields

| Field | Type | Notes |
| --- | --- | --- |
| `code` | string | Stable condition identifier. |
| `severity` | string | `info`, `warning`, `attention`, `error`. |
| `scope` | string | `run`, `stage`, `task`, `dataset`. |
| `disposition` | string | `continue`, `skip_stage`, `stop_run_clean`, `fail_run`. |
| `active` | boolean | Whether the condition is active. |

### Optional condition fields

| Field | Type | Notes |
| --- | --- | --- |
| `message` | string or null | Human-readable summary. |
| `details` | object or null | Extra structured detail. |
| `producer_stage` | integer or null | Stage that produced the condition. |
| `producer_task` | string or null | Task that produced the condition. |
| `created_at` | string or null | UTC ISO-8601 time. |
| `updated_at` | string or null | UTC ISO-8601 time. |

### Current condition vocabulary

The currently implemented condition codes are intentionally small.

| Code | Meaning | Typical disposition |
| --- | --- | --- |
| `imaging_target_selection_notice` | Non-fatal message from imaging target selection, such as no targets or no check-source data. | `continue` |
| `continuum_selection_warning` | Non-fatal `hif_findcont` warning state, including narrow-range continuum findings, heuristic warnings, or selections removed from later imaging. | `continue` |
| `imaging_parameter_override` | Heuristic imaging parameter overrides, currently robust and uvtaper values from `hifa_imageprecheck`. | `continue` |
| `size_mitigation` | Published mitigation settings or blocking mitigation failure from `hif_checkproductsize`. | `continue` or `skip_stage` |

For condition lifecycle events, the condition code is currently carried in the `reason_code` field and the complete condition object is repeated in `payload.condition`.

## Compatibility guidance

The current implementation still preserves legacy `errorexit-*` compatibility files. Those files should not be treated as the long-term structured contract.

The current retirement staging for those compatibility surfaces is documented in `pipeline_status_contract_transition.md`.

The structured schema above is intended to become the supported contract for:

- live run monitoring;
- final run classification;
- stage lifecycle visibility;
- non-fatal condition communication.

## Versioning guidance

The initial schema should begin at `schema_version = 1`.

Recommended compatibility rule:

- adding optional fields is backward-compatible;
- removing fields or changing the meaning of existing fields requires a schema version increment.