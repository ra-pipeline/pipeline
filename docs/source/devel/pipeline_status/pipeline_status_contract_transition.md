# Pipeline Status Contract Transition Plan

## Purpose

This note records the current retirement plan for the older sentinel-file and legacy context-mirror behavior now that the structured status contract is in place.

It is intentionally practical. The goal is to clarify what remains supported, what is transitional, and what conditions should be met before compatibility output is removed.

## Supported contract going forward

The supported contract for run outcome and status visibility is now:

- stable process exit codes;
- `pipeline-status.json`;
- `pipeline-events.jsonl`;
- the `Context` condition registry for selected non-fatal cross-stage state.

New consumers and new task logic should target this contract directly.

## Transitional compatibility surfaces

Two older compatibility surfaces still exist.

### `errorexit-*` files

Legacy `errorexit-*` files remain in the fatal PPR compatibility path so that existing production integrations are not broken abruptly.

These files are now considered compatibility output only.

They should not be extended with new semantics, and no new consumer should be built against them.

### Legacy context mirrors

Some structured conditions currently continue to mirror state into older context dictionaries so that non-migrated readers continue to work.

Examples include:

- `context.size_mitigation_parameters`;
- `context.clean_list_info`;
- `context.imaging_parameters`.

These mirrors are transitional and should shrink as reader migration completes.

## Retirement stages

### Stage 1: compatibility retained

Current state.

Requirements:

- structured artifacts are treated as the primary contract;
- `errorexit-*` remains available only for compatibility;
- migrated readers prefer condition-backed helpers;
- documentation points new consumers to the structured contract.

### Stage 2: compatibility demoted

Exit criteria:

- `pipelinedriver` and related operators consume the structured artifacts in production workflows;
- release notes explicitly mark `errorexit-*` as deprecated;
- the remaining legacy context-mirror readers are identified and tracked.

Planned changes:

- `errorexit-*` becomes best-effort compatibility output rather than a relied upon contract;
- new feature work does not add to legacy mirrors;
- condition-backed readers become the default expectation in reviews.

### Stage 3: compatibility removed

Exit criteria:

- no supported production integration depends on `errorexit-*`;
- all readers of the relevant migrated state use condition-backed helpers;
- release stakeholders agree that the compatibility window has closed.

Planned changes:

- remove legacy `errorexit-*` writes from the production path;
- remove obsolete context-dictionary mirrors once the last reader is migrated;
- simplify documentation so the structured contract is the only documented interface.

## Implementation guidance for future work

Until compatibility is fully removed:

- keep the structured artifacts authoritative;
- avoid introducing new sentinel files;
- avoid adding new readers that depend directly on legacy context mirrors;
- update this note when a compatibility surface is retired.

## Minimum release-note content

When the project moves from one retirement stage to the next, release notes should state:

- which compatibility surface changed;
- whether the change is a deprecation or a removal;
- what supported replacement consumers should use instead.