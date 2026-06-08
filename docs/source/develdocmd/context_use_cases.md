# Pipeline Context Use Cases

## Overview

The pipeline `Context` is the central state object used for a pipeline execution. It carries observation data, calibration state, imaging state, execution history and state, project metadata, and serves as the primary communication channel between pipeline stages.

This document catalogues the use cases of the current pipeline context as determined by examination of the codebase. The goal is to describe the current pipeline context implementation and document observed limitations.

These use cases were produced retrospectively, after the pipeline and its context model had already been developed and iterated on over multiple years. They describe behavior that exists in the current implementation and in established pipeline workflows; they are not original requirements that guided the design before implementation.

---

## 1. Context Lifecycle

The canonical flow through the context is:

1. **Create session** — `h_init()` constructs a `launcher.Pipeline(...)` and returns a new `Context`. In PPR-driven execution, `executeppr()` or `executevlappr()` also populates project metadata at this point.
2. **Populate data** — Import tasks (`h*_importdata`) attach datasets to the context's domain model (`context.observing_run`, measurement sets, scans, SPWs, etc.).
3. **Execute tasks** — Tasks execute against the in-memory context and return a `Results` object. After each task, `Results.accept(context)` records the outcome and mutates shared state.
4. **Accept results** — Inside `accept()`, results are merged via `Results.merge_with_context(context)`. A `ResultsProxy` is pickled to disk per-stage to keep the in-memory context bounded. The weblog is typically rendered after each top-level stage.
5. **Save / resume** — `h_save()` pickles the context; `h_resume(filename='last')` restores it. Driver-managed breakpoints and developer debugging workflows rely on this cycle.

### Key implementation references

- `Context` / `Pipeline`: `pipeline/infrastructure/launcher.py`
- CLI lifecycle tasks: `pipeline/h/cli/h_init.py`, `pipeline/h/cli/h_save.py`, `pipeline/h/cli/h_resume.py`
- Task dispatch & result acceptance: `pipeline/h/cli/utils.py`, `pipeline/infrastructure/basetask.py`
- PPR-driven execution loops:
  - ALMA: `pipeline/infrastructure/executeppr.py` (used by `pipeline/runpipeline.py`)
  - VLA: `pipeline/infrastructure/executevlappr.py` (used by `pipeline/runvlapipeline.py`)
- Direct XML procedure execution: `pipeline/recipereducer.py`
- MPI distribution: `pipeline/infrastructure/mpihelpers.py`
- QA framework: `pipeline/infrastructure/pipelineqa.py`, `pipeline/qa/`
- Weblog renderer: `pipeline/infrastructure/renderer/htmlrenderer.py`

---

## 2. Use Cases

Each use case below is mapped directly to current code paths and concrete runtime behavior found in this repository. The goal is to describe what the context must do and where that capability is implemented today (modules, classes, or functions). Implementation notes follow each use case and reference the exact symbols and files that implement or exercise the behavior.

The following fields are used in each use case:

- **Actor(s):** The human or system role that directly creates, updates, consumes, or inspects the context state described by the use case. Actors are role categories, not specific task names or current implementations.
- **Summary:** What the context must do to satisfy the use case.
- **Invariant:** A condition that must always be true while the system is operating. Present only where a meaningful invariant exists.
- **Postcondition:** A condition that must be true after a specific operation completes. Present only where a meaningful postcondition exists.

---

### UC-01 — Populate, Access, and Provide Observation Metadata

| | |
|-------|---------|
| **Actor(s)** | Data import task, any downstream task, heuristics, renderers, QA handlers |
| **Summary** | Import tasks under `pipeline/h/*_importdata` populate observation metadata into `context.observing_run` (MS objects, SPWs, fields, scans). Downstream code queries this metadata via `context.observing_run.get_ms(...)`, `context.observing_run.measurement_sets`, and related helpers. Derived datasets (calibrated/averaged subsets) are registered on the domain objects rather than mutating original MS objects. |
| **Invariant** | All populated datasets and derived dataset records remain queryable for the lifetime of the session without repeating the import process. |

**Implementation notes** — `context.observing_run` holds the observation metadata and is the most frequently queried attribute of the context:

- `context.observing_run.get_ms(name=vis)` — resolve an MS by filename
- `context.observing_run.measurement_sets` — all registered MS objects
- `context.observing_run.ms_reduction_group` — per-group reduction metadata (single-dish)
- Provenance attributes: `start_datetime`, `end_datetime`, `project_ids`, `schedblock_ids`, `execblock_ids`, `observers`

The MS objects stored by `context.observing_run` carry information about scans, fields, SPWs, antennas, reference antenna ordering, etc. Tasks read per-MS state like `ms.reference_antenna`, `ms.session`, `ms.start_time`, `ms.origin_ms`.

For the single-dish pipeline, this use case also includes per-MS `DataTable` products referenced through `context.observing_run.ms_datatable_name`. These are not just raw imported metadata tables: they persist row-level metadata and derived quantities used by downstream SD tasks. During SD import, the reader populates `DataTable` columns such as `RA`, `DEC`, `AZ`, `EL`, `SHIFT_RA`, `SHIFT_DEC`, `OFS_RA`, and `OFS_DEC`, including coordinate conversions into the pipeline's chosen celestial frame (for example ICRS) so later imaging, gridding, plotting, and QA code can reuse those values efficiently.

---

### UC-02 — Cross-MS Metadata Matching and Lookup
| | |
|-------|---------|
| **Actor(s)** | Calibration tasks, imaging tasks, heuristics
| **Summary** | The code implements cross-MS lookup via `context.observing_run` utilities: virtual SPW mapping (`virtual2real_spw_id` / `real2virtual_spw_id`) and type-aware filters (`get_measurement_sets_of_type(...)`). Downstream calibration and imaging tasks call these helpers directly to resolve SPWs, fields, and MS-level selections across heterogeneous datasets. |
| **Postcondition** | Downstream tasks can resolve applicable metadata across registered MSes using a unified identifier scheme, and can look up MSes and data columns by data type.

**Implementation notes** - `context.observing_run` handles the virtual spw mapping, as well as filtering MSes by type:

- `context.observing_run.get_measurement_sets_of_type(dtypes)` — filter by data type (RAW, REGCAL_CONTLINE_ALL, BASELINED, etc.)
- `context.observing_run.virtual2real_spw_id(vspw, ms)` / `real2virtual_spw_id(...)` — translate between abstract pipeline SPW IDs and CASA-native IDs
- `context.observing_run.virtual_science_spw_ids` — virtual SPW catalog

---

### UC-03 — Store and Provide Project-Level Metadata

| | |
|-------|---------|
| **Actor(s)** | Initialization, any task, report generators |
| **Summary** | Project-level metadata is populated by initialization and PPR executors (`executeppr()` / `executevlappr()`), is stored in `context.project_summary`, `context.project_structure`, and `context.project_performance_parameters`, and is read by heuristics and reporters (see `pipeline/infrastructure/executeppr.py`, `pipeline/infrastructure/executevlappr.py`, and `pipeline/infrastructure/launcher.py`). |
| **Invariant** | Project metadata is available for the lifetime of the processing session. |

**Implementation notes** — project metadata (properties of the observation program such as PI, targeted sensitivities, beam requirements) is set during initialization or import, is not modified after import, and is read many times:

 - The current implementation bundles project metadata (scientific intent and constraints: PI, targeted sensitivities, beam requirements) and workflow/recipe metadata (describe how the data should be processed: recipes, execution instructions, heuristic parameters) in the ProjectStructure class. These have different origins and lifecycles.
- `context.project_summary = project.ProjectSummary(...)` — set by `executeppr()` / `executevlappr()`
- `context.project_structure = project.ProjectStructure(...)` — set by PPR executors
- `context.project_performance_parameters` — performance parameters from the PPR
- `context.set_state('ProjectStructure', 'recipe_name', value)` — used by `recipereducer.reduce()` and SD heuristics
- `context.processing_intents` — set by `Pipeline` during initialization

---

### UC-04 — Register, Query, and Update Calibration State

| | |
|-------|---------|
| **Actor(s)** | Calibration tasks, export tasks, restore tasks, report generators |
| **Summary** | Calibration workflows register and query cal tables through `context.callibrary` (see `context.callibrary.add()`, `context.callibrary.active.get_caltable()`, `context.callibrary.unregister_calibrations()`), which records application scope and provenance; tasks query the callibrary to find applicable calibrations for selections. Atomic registration/de-registration is handled by callibrary primitives and `CalApplication` objects. |
| **Invariant** | Calibration state is queryable and correctly scoped to data selections, and can be updated as processing progresses. |

**Implementation notes** — `context.callibrary` is the primary cross-stage communication channel for calibration workflows:

- **Write:** `context.callibrary.add(calto, calfrom)` — register a calibration application (cal table + target selection); `context.callibrary.unregister_calibrations(matcher)` — remove by predicate
- **Read:** `context.callibrary.active.get_caltable(caltypes=...)` — list active cal tables; `context.callibrary.get_calstate(calto)` — get full application state for a target selection
- Backed by `CalApplication` → `CalTo` / `CalFrom` objects with interval trees for efficient matching.
 - The callibrary also supports de-registration of trial or reverted calibrations via predicate-based removal.

---

### UC-05 — Manage Imaging State

| | |
|-------|---------|
| **Actor(s)** | Imaging tasks, downstream heuristics, and export tasks |
| **Summary** | Imaging/planning tasks (`makeimlist`, `editimlist`) and execution tasks (`makeimages`, `tclean`) populate and consume imaging state via context attributes (for example `clean_list_pending`, `imaging_parameters`, `synthesized_beams`, `size_mitigation_parameters`). These attributes are written/read by imaging helpers and heuristics across `pipeline/h*` tasks and imaging utilities. |
| **Invariant** | Imaging state reflects contributions from all completed imaging-related stages, and is available for reading or refinement by subsequent stages. |

Imaging workflows consist of two separate phases: a lightweight planning phase (for example, `makeimlist`, `editimlist`) that assembles imaging instructions, target lists, and imaging-mode heuristics and a computationally intensive execution phase (for example, `makeimages`) that performs the heavy imaging work.

**Implementation notes** — imaging state is stored as ad-hoc attributes on the context object with no formal schema. Defensive `hasattr()` checks appear throughout the code to guard against attributes that may not yet exist:

| Attribute | Written by | Read by |
|---|---|---|
| `clean_list_pending` | `editimlist`, `makeimlist`, `findcont`, `makeimages` | `findcont`, `transformimagedata`, `makeimages`, `vlassmasking` |
| `clean_list_info` | `makeimlist`, `makeimages` | `makeimages` |
| `imaging_mode` | `editimlist` | `makermsimages`, `makecutoutimages`, `makeimages`, VLASS export/display code |
| `imaging_parameters` | `imageprecheck` | `tclean`, `checkproductsize`, `makeimlist`, heuristics |
| `synthesized_beams` | `imageprecheck`, `tclean`, `checkproductsize`, `makeimlist`, `makeimages` | `imageprecheck`, `editimlist`, `tclean`, `uvcontsub`, `checkproductsize`, heuristics |
| `size_mitigation_parameters` | `checkproductsize` | downstream stages |
| `selfcal_targets` | `selfcal` | `makeimlist` |
| `selfcal_resources` | `selfcal` | `exportdata` |

---

### UC-06 — Register and Query Produced Image Products

| | |
|-------|---------|
| **Actor(s)** | Imaging tasks, export tasks, report generators |
| **Summary** | Image registries are explicit lists on the context (`context.sciimlist`, `context.calimlist`, `context.rmsimlist`, `context.subimlist`) populated by imaging and export tasks (e.g., `makeimages`, `exportdata`) so downstream tasks and reporters can discover produced image products by type. |
| **Invariant** | Produced image products are registered by type and remain queryable for downstream processing, reporting, and export. |

**Implementation notes** — image libraries provide typed registries:

- `context.sciimlist` — science images
- `context.calimlist` — calibrator images
- `context.rmsimlist` — RMS images
- `context.subimlist` — sub-product images (cutouts, cubes)

---

### UC-07 — Track Current Execution Progress

| | |
|-------|---------|
| **Actor(s)** | Workflow orchestration layer, tasks, pipeline operators |
| **Summary** | Execution progress is tracked by fields set during task execution (`context.stage`, `context.task_counter`, `context.subtask_counter`) by the `Executor` and `StandardTaskTemplate` in `pipeline/infrastructure/basetask.py` and by driver entrypoints in `pipeline/h/cli/`. These fields, together with `context.results`, provide an ordered record that is preserved on save/resume. |
| **Invariant** | The currently executing stage is identifiable and completed stages are recorded in stable order. |

**Implementation notes:**

- `context.stage`, `context.task_counter`, `context.subtask_counter` track progress

---

### UC-08 — Preserve Per-Stage Execution Record

| | |
|-------|---------|
| **Actor(s)** | Report generators, pipeline operators, workflow orchestration layer |
| **Summary** | Per-stage execution records are captured as `ResultsProxy` objects (see `pipeline/infrastructure/basetask.py`) and appended to `context.results` via `Results.accept()` / `Results.merge_with_context()`. Results proxies are pickled to disk to bound memory and carry timing, traceback, invocation arguments, and outcome metadata for reporting and resume. |
| **Invariant** | Each completed stage retains its full execution record — identity, outcome, timing, traceback, and invocation arguments — for the lifetime of the session. |

**Implementation notes:**

- `context.results` holds an ordered list of `ResultsProxy` objects which are proxied to disk to bound memory
- Timetracker integration provides per-stage timing data
- Results proxies store basenames for portability

---

### UC-09 — Propagate Task Outputs to Downstream Tasks

| | |
|-------|---------|
| **Actor(s)** | Any task producing output, downstream tasks |
| **Summary** | Tasks publish outputs by returning `Results` objects which are merged into the shared `Context` via `Results.accept()` / `Results.merge_with_context()`; this path updates `context.callibrary`, image registries, and context attributes so downstream stages can consume published outputs without inspecting raw result objects. |
| **Postcondition** | Downstream tasks can access the propagated processing state they need. |

**Implementation notes** — the intended primary mechanism in the current pipeline is immediate propagation through context state updated during result acceptance. Over time, some workflows also came to inspect recorded results (`context.results`) directly. Both patterns exist in the codebase, but the second should be understood as an accreted pattern rather than the original design intent.

1. **Immediate state propagation** — `Results.merge_with_context(context)` updates calibration library, image libraries, and dedicated context attributes such as `clean_list_pending`, `clean_list_info`, `synthesized_beams`, `size_mitigation_parameters`, `selfcal_targets`, and `selfcal_resources` so later tasks can access the current processing state directly without parsing another task's results object.
2. **Recorded-result inspection** — some tasks read `context.results` to find outputs from earlier stages when those outputs are needed from the recorded results rather than from merged shared state. This pattern introduces coupling to recipe order or to another task's result class structure. For example:
   - VLA tasks compute `stage_number` from `context.results[-1].read().stage_number + 1`
   - `vlassmasking` iterates `context.results[::-1]` to find the latest `MakeImagesResult`
   - Export/AQUA code reads `context.results[0]` and `context.results[-1]` for timestamps

---

### UC-10 — Provide a Transient Intra-Stage Workspace

| | |
|-------|---------|
| **Actor(s)** | Aggregate tasks, child tasks, task execution framework |
| **Summary** | The `StandardTaskTemplate` / `Executor` pattern provides a transient workspace: `StandardTaskTemplate.execute()` executes child tasks against a pickled copy of the inputs/context and `Executor.execute(job, merge=True)` commits a child's `Results` via `result.accept(context)`. Temporary mutations are discarded unless explicitly merged. |
| **Invariant** | State changes made while executing against a temporary child-task context do not escape that workspace unless they are explicitly accepted and merged. |
| **Postcondition** | When a child task finishes, the enclosing task retains only the accepted state changes; unaccepted mutations to the temporary workspace are discarded. |

**Implementation notes** — the current framework implements this behavior in `pipeline/infrastructure/basetask.py`:

- `StandardTaskTemplate.execute()` replaces `self.inputs` with a pickled copy of the original inputs, including the context, before task logic runs, and restores the original inputs in `finally`
- Child tasks therefore execute against a duplicated context that may be mutated freely during `prepare()` / `analyse()`
- `Executor.execute(job, merge=True)` commits a child result by calling `result.accept(self._context)`; with `merge=False`, the child task may still be run and inspected without committing its state
- This makes it possible for aggregate tasks to try tentative calibration paths or other destructive edits inside a stage and keep only the results they explicitly accept
- The rollback mechanism is in-memory copy/restore of task inputs and context; it is distinct from explicit session save/resume workflows

---

### UC-11 — Support Multiple Orchestration Drivers

| | |
|-------|---------|
| **Actor(s)** | Operations / automated processing (PPR-driven batch), pipeline developer / power user (interactive), recipe executor |
| **Summary** | Multiple drivers converge on the same `Pipeline`/`Context` objects: interactive CLI wrappers under `pipeline/h/cli/`, PPR executors (`pipeline/infrastructure/executeppr.py`, `executevlappr.py`), and `recipereducer.py`. The context is populated and resumed by these drivers and must retain driver-injected metadata (e.g., `context.project_structure`) so downstream tasks behave consistently. |
| **Invariant** | Processing state is consistent and usable regardless of which orchestration driver created or resumed it, and success/failure signals are produced when appropriate. |

**Implementation notes** — multiple entry points converge on the same task execution path:

- **Task-driven**: direct task calls via CLI wrappers in `pipeline/h/cli/`
- **Command-list-driven**: PPR and XML procedure commands via `executeppr.py` / `executevlappr.py` and `recipereducer.py`

They differ in how inputs are specified, how session paths are selected, and how resume is initiated, but the persisted context is the same.

---

### UC-12 — Save and Restore a Processing Session

| | |
|-------|---------|
| **Actor(s)** | Pipeline operator, workflow orchestration layer, pipeline developer |
| **Summary** | Serialization is performed by `h_save()` / `h_resume()` (CLI wrappers) which pickle the `Context` object to `<context.name>.context` and later restore it. Per-stage results are proxied to disk (result-stageX.pickle) to reduce in-memory size. The restore path is implemented in `pipeline/h/cli/h_resume.py` and `launcher.Pipeline` initialization logic. |
| **Postcondition** | After restore, the processing state is operationally equivalent to the saved state for supported resume workflows, and processing can continue from the specified point, assuming the data files are in a state consistent with the snapshot used to create the saved context. |

**Implementation notes:**

- `h_save()` pickles the whole context to `<context.name>.context`
- `h_resume(filename)` loads a `.context` file, defaulting to the most recent context file available if `filename` is `None` or `last` is used.
- Per-stage results are proxied to disk (`saved_state/result-stageX.pickle`) to keep the in-memory context smaller
- Used by driver-managed breakpoint/resume (`executeppr(..., bpaction='resume')`) and developer debugging workflows

Note: The current implementation does not handle restoring data state to a past processing state and as such does not have a built-in, robust "true resume". If the data directory needs to be restored to match a saved context snapshot, this must be done manually (e.g. via having created a snapshot of the data at an earlier stage, and then restoring this state) before resuming.

---

### UC-13 — Provide State to Parallel Workers

| | |
|-------|---------|
| **Actor(s)** | Workflow orchestration layer, parallel worker processes |
| **Summary** | Parallel workers obtain context snapshots via `pipeline/infrastructure/mpihelpers.py` which pickles the context and task args to share with workers. Worker-side startup loads the pickled context and adjusts local paths (e.g., `context.logs['casa_commands']`) before executing tasks. This read-only snapshot model is the current distribution mechanism. |
| **Postcondition** | After distribution, each worker has a consistent view of the processing state for the duration of its work. |

**Implementation notes** — `pipeline/infrastructure/mpihelpers.py`, class `Tier0PipelineTask`:

1. The MPI client saves the context to disk as a pickle: `context.save(path)`.
2. Task arguments are also pickled to disk alongside the context.
3. On the server, `get_executable()` loads the context, modifies `context.logs['casa_commands']` to a server-local temp path, creates the task's `Inputs(context, **task_args)`, then executes the task.
4. For `Tier0JobRequest` (lower-level distribution), the executor is shallow-copied *excluding* the context reference to stay within the pipeline-enforced MPI buffer limit (100 MiB). Comments in the code note CASA's higher native limit (~150 MiB; see PIPE-1337 / CAS-13656).

- The current implementation uses a read-only worker model: workers do not modify shared processing state directly, and results are committed through a result-accept/merge flow.

---

### UC-14 — Aggregate Results from Parallel Workers

| | |
|-------|---------|
| **Actor(s)** | Workflow orchestration layer |
| **Summary** | Aggregation is implemented by the orchestration layer calling `result.accept(context)` for worker results; `Results.merge_with_context()` applies aggregated outputs (cal tables, image registries) into the shared `Context` in a single commit step to avoid interleaved conflicting writes. |
| **Postcondition** | The processing state reflects the combined outcomes of all parallel workers. |

---

### UC-15 — Provide Read-Only State for Reporting

| | |
|-------|---------|
| **Actor(s)** | Report generators (weblog, quality reports, reproducibility scripts, pipeline statistics) |
| **Summary** | Reporting uses `WebLogGenerator.render(context)` in `pipeline/infrastructure/renderer/htmlrenderer.py`, which unpickles `context.results` proxies and reads `context.observing_run`, `context.project_summary`, `context.report_dir`, and `context.output_dir` to assemble pages and report artifacts. |
| **Postcondition** | Reports accurately reflect the processing state at the time of generation. |

**Implementation notes** — `WebLogGenerator.render(context)` in `pipeline/infrastructure/renderer/htmlrenderer.py`:

- `WebLogGenerator.render(context)` explicitly does `context.results = [proxy.read() for proxy in context.results]` once before the renderer loop, so individual renderers iterate fully unpickled result objects rather than calling `read()` themselves
- Reads `context.report_dir`, `context.output_dir` — filesystem layout
- Reads `context.observing_run.*` — MS metadata, scheduling blocks, execution blocks, observers, project IDs, start/end times
- Reads `context.project_summary.telescope` — to determine telescope-specific page layouts (ALMA vs VLA vs NRO)
- Reads `context.project_structure.*` — OUS IDs, PPR file, recipe name
- The larger renderer stack, including the Mako templates under `pipeline/infrastructure/renderer/templates/`, reads `context.logs['casa_commands']` and related log references when generating weblog links

---

### UC-16 — Support QA Evaluation and Store Quality Assessments

| | |
|-------|---------|
| **Actor(s)** | QA scoring framework, report generators |
| **Summary** | After `Results.accept()` the QA framework (`pipeline/infrastructure/pipelineqa.py`) invokes `pipelineqa.qa_registry.do_qa(context, result)`. Handlers call `context.observing_run.get_ms(vis)` and inspect `context.imaging_mode` / `context.project_structure` to compute `QAScore` objects appended to `result.qa.pool`. |
| **Postcondition** | Quality scores are associated with the relevant processing step and accessible to reports. |

**Implementation notes** — after `merge_with_context()`, `accept()` triggers `pipelineqa.qa_registry.do_qa(context, result)`:

- QA handlers implement `QAPlugin.handle(context, result)`
- The context provides inputs to QA evaluation:
  - Most handlers call `context.observing_run.get_ms(vis)` to look up metadata for scoring (antenna count, channel count, SPW properties, field intents)
  - Some handlers check `context.imaging_mode` to branch on VLASS-specific scoring
  - Others check things in `context.observing_run`, `context.project_structure`, or the callibrary (`context.callibrary`)
- Scores are appended to `result.qa.pool`, so the scores are stored on the results rather than directly on the context. This also keeps detailed QA collections scoped to the stage result that produced them; in current code, a `QAScorePool` can hold many `QAScore` objects, and each score may carry fine-grained `applies_to` selections (e.g. vis, field, SPW, antenna, polarization), so the per-result pool can become fairly large for detailed assessments.

QA handlers write scores to `result.qa.pool` and do not modify the shared context directly.

---

### UC-17 — Support Inspection and Debugging

| | |
|-------|---------|
| **Actor(s)** | Pipeline developer, pipeline operator, CI harnesses |
| **Summary** | Inspection and debugging are supported by `h_save()`/`h_resume()` (pickled `Context` files), `context.results` (ordered `ResultsProxy` snapshots), and developer utilities used in tests and CI (`tests/testing_utils.py`). Weblog rendering (`pipeline/infrastructure/renderer/htmlrenderer.py`) and diagnostic helpers in `pipeline/infrastructure/basetask.py` expose per-stage timing, tracebacks, and log references so operators can inspect registered datasets (`context.observing_run`), calibrations (`context.callibrary`), and produced images (`context.sciimlist`). |
| **Invariant** | The current processing state is inspectable at any point during execution, and sufficient information is retained to diagnose failures after the fact. |

---

### UC-18 — Manage Telescope- and Array-Specific State

| | |
|-------|---------|
| **Actor(s)** | Telescope-specific tasks and heuristics, array-specific tasks and heuristics |
| **Summary** | Telescope- and array-specific state is implemented in a mixture of dynamic sidecars and domain-model extensions: `context.evla` (VLA-specific sidecar created by `hifv_importdata` and consumed by VLA calibration tasks), ALMA single-dish extensions under `context.observing_run` (e.g., `ms_datatable_name`, `ms_reduction_group`, per-MS `DataTable` objects), and task-specific heuristics in the `pipeline/h*` task implementations. Generic components read these extensions via their documented helpers rather than assuming their presence. |
| **Invariant** | Telescope- and array-specific extensions are present only for runs that require them, available to the tasks that need them, and are never assumed by shared pipeline code. |

**Implementation notes** — the current codebase shows at least two different forms of telescope-/array-specific state.

One is a VLA-specific sub-context (`context.evla`) which is created during `hifv_importdata` and is updated by several subsequent tasks. Functionally, it provides a way to store observation metadata and pass state between tasks under `context.evla` rather than using the top-level context directly or other context objects (e.g. the domain objects). `context.evla` is an untyped, dictionary-of-dictionaries sidecar dynamically attached to the top-level context with no schema, no type annotations, and no declaration in `Context.__init__`.

`context.evla` is a `collections.defaultdict(dict)`, keyed as `context.evla['msinfo'][ms_name].<property>`:

- **Written by:** `hifv_importdata` (creates + initializes), `testBPdcals` (gain intervals, ignorerefant), `fluxscale/solint`, `fluxboot`
- **Read by:** Most VLA calibration tasks and heuristics
- Accessed fields include: `gain_solint1`, `gain_solint2`, `setjy_results`, `ignorerefant`, various `*_field_select_string` / `*_scan_select_string` values, `fluxscale_sources`, `spindex_results`, and many more

Another is ALMA TP / single-dish state, which is array-specific rather than telescope-wide and is carried mainly through SD-specific structures under `context.observing_run`, such as `ms_datatable_name`, `ms_reduction_group`, and `org_directions`, plus the per-MS `DataTable` products referenced from that state. This is a useful reminder that array-specific extensions do not always appear as a single sidecar object like `context.evla`; they may instead live in domain-model extensions and array-specific cached metadata products.

---

### UC-19 — Provide State for Product Export

| | |
|-------|---------|
| **Actor(s)** | Export tasks |
| **Summary** | Export tasks (for example `hifa_exportdata`, `hifv_exportdata`, and the `hsdn/tasks/exportdata` implementations) consume `context.sciimlist`, `context.callibrary`, `context.project_summary`, `context.report_dir`, and `context.output_dir` to assemble deliverable bundles. The `pipeline/infrastructure/imagelibrary.py` utilities and export task code are the canonical places where exportable product lists are assembled and serialized. |
| **Invariant** | The information needed to assemble a deliverable product package is accessible through the processing state. |
