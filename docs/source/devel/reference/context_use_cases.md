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
- Product export and manifests: `pipeline/h/tasks/exportdata/`, `pipeline/hif/tasks/exportdata/`, `pipeline/hifv/tasks/exportdata/`, `pipeline/hsd/tasks/exportdata/`, `pipeline/h/tasks/common/manifest.py`

---

## 2. Use Cases

Each use case summary describes the required capability and observable behavior without prescribing its implementation. Implementation notes follow each use case and document how the current pipeline realizes that behavior, including exact symbols and files where useful. Keeping those two parts distinct mirrors the requirements and supplementary-analysis documents maintained for the RADPS context work.

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
| **Summary** | The context must make observation metadata (datasets, spectral windows, fields, antennas, scans, and time ranges) available to subsequent processing steps. When processing produces derived or transformed datasets, downstream consumers must be able to distinguish them from their source datasets and determine their lineage. Metadata products produced during import must remain available for reuse by later stages. |
| **Invariant** | Observation metadata for datasets in the accepted processing state remains queryable for the lifetime of the session unless it is intentionally replaced by a subsequent accepted result. |

**Implementation notes** — Import tasks under `pipeline/h/*_importdata` populate the MS objects and related observation metadata held by `context.observing_run`, which is the most frequently queried attribute of the context:

- `context.observing_run.get_ms(name=vis)` — resolve an MS by filename
- `context.observing_run.measurement_sets` — all registered MS objects
- `context.observing_run.ms_reduction_group` — per-group reduction metadata (single-dish)
- Provenance attributes: `start_datetime`, `end_datetime`, `project_ids`, `schedblock_ids`, `execblock_ids`, `observers`

The MS objects stored by `context.observing_run` carry information about scans, fields, SPWs, antennas, reference antenna ordering, etc. Tasks read per-MS state like `ms.reference_antenna`, `ms.session`, `ms.start_time`, `ms.origin_ms`.

Transformed datasets are generally represented by new `MeasurementSet` domain objects. Tasks such as `h_mssplit`, `hif_mstransform`, `hifv_mstransform`, and `hif_transformimagedata` propagate the source object's `origin_ms` value to the new object before the accepted result adds it to `context.observing_run`. This preserves a source reference for derived datasets, but the current implementation does not retain every dataset object immutably: replace-mode transforms can remove the source entry, and rerunning tasks such as single-dish baseline/atmospheric correction or `hif_uvcontsub` can replace a previously registered output with the same name.

For the single-dish pipeline, this use case also includes per-MS `DataTable` products referenced through `context.observing_run.ms_datatable_name`. These are not just raw imported metadata tables: they persist row-level metadata and derived quantities used by downstream SD tasks. During SD import, the reader populates `DataTable` columns such as `RA`, `DEC`, `AZ`, `EL`, `SHIFT_RA`, `SHIFT_DEC`, `OFS_RA`, and `OFS_DEC`, including coordinate conversions into the pipeline's chosen celestial frame (for example ICRS) so later imaging, gridding, plotting, and QA code can reuse those values efficiently.

---

### UC-02 — Cross-MS Metadata Matching and Lookup
| | |
|-------|---------|
| **Actor(s)** | Calibration tasks, imaging tasks, heuristics
| **Summary** | When multiple MSes are available, downstream tasks must be able to identify corresponding metadata elements across them even when the MSes use different native numbering. Tasks must also be able to find MSes and associated data columns by data type.
| **Postcondition** | Downstream tasks can resolve corresponding metadata across the available MSes and can find MSes and data columns by data type.

**Implementation notes** - `context.observing_run` handles the virtual spw mapping, as well as filtering MSes by type:

- `context.observing_run.get_measurement_sets_of_type(dtypes)` — filter by data type (RAW, REGCAL_CONTLINE_ALL, BASELINED, etc.)
- `context.observing_run.virtual2real_spw_id(vspw, ms)` / `real2virtual_spw_id(...)` — translate between abstract pipeline SPW IDs and CASA-native IDs
- `context.observing_run.virtual_science_spw_ids` — virtual SPW catalog

Calibration and imaging tasks call these helpers directly when resolving SPWs and MS-level selections across datasets.

---

### UC-03 — Store and Provide Project-Level Metadata

| | |
|-------|---------|
| **Actor(s)** | Initialization, any task, report generators |
| **Summary** | The context must store project-level metadata (proposal code, PI, telescope, desired sensitivities, etc.) and make it available to all components, e.g., for decision-making in heuristics and to label outputs in reports. |
| **Invariant** | Project metadata is available for the lifetime of the processing session. |

**Implementation notes** — project metadata (properties of the observation program such as PI, targeted sensitivities, beam requirements) is set during initialization or import, is not modified after import, and is read many times:

 - The current implementation bundles project metadata (scientific intent and constraints: PI, targeted sensitivities, beam requirements) and workflow/recipe metadata (describe how the data should be processed: recipes, execution instructions, heuristic parameters) in the ProjectStructure class. These have different origins and lifecycles.
- `context.project_summary = project.ProjectSummary(...)` — set by `executeppr()` / `executevlappr()`
- `context.project_structure = project.ProjectStructure(...)` — set by PPR executors
- `context.project_performance_parameters` — performance parameters from the PPR
- `context.set_state('ProjectStructure', 'recipe_name', value)` — used by `recipereducer.reduce()` and SD heuristics
- `context.processing_intents` — set by `Pipeline` during initialization

The initialization and PPR paths are implemented in `pipeline/infrastructure/launcher.py`, `pipeline/infrastructure/executeppr.py`, and `pipeline/infrastructure/executevlappr.py`; downstream heuristics and report generators read the resulting project metadata.

---

### UC-04 — Register, Query, and Update Calibration State

| | |
|-------|---------|
| **Actor(s)** | Calibration tasks, export tasks, restore tasks, report generators |
| **Summary** | The context must allow calibration tasks to register and update solutions and to record both the coverage where a solution applies and the source(s) from which it was derived. Downstream tasks must be able to query for all calibrations applicable to a given data selection. The context must distinguish between calibrations pending application and those already applied. Registration must support registering multiple calibrations atomically as part of a single operation, and it must also support de-registration/removal of trial or reverted calibrations so alternative solutions can be tested or failed attempts rolled back. |
| **Invariant** | Calibration state is queryable and correctly scoped to data selections, and can be updated as processing progresses. |

**Implementation notes** — `context.callibrary` is the primary cross-stage communication channel for calibration workflows:

- **Write:** `context.callibrary.add(calto, calfrom)` — register a calibration application (cal table + target selection); `context.callibrary.unregister_calibrations(matcher)` — remove by predicate
- **Read:** `context.callibrary.active.get_caltable(caltypes=...)` — list active cal tables; `context.callibrary.get_calstate(calto)` — get full application state for a target selection
- Backed by `CalApplication` → `CalTo` / `CalFrom` objects with interval trees for efficient matching.
 - The callibrary also supports de-registration of trial or reverted calibrations via predicate-based removal.

These APIs mutate the in-process context; they do not provide a transactional store or an atomic commit boundary across multiple calls.

---

### UC-05 — Manage Imaging State

| | |
|-------|---------|
| **Actor(s)** | Imaging tasks, downstream heuristics, and export tasks |
| **Summary** | The context must allow imaging state — target lists, imaging parameters, masks, thresholds, and sensitivity estimates — to be computed by one step and read or refined by later steps. Multiple steps may contribute to a progressively refined imaging configuration. |
| **Invariant** | Imaging state reflects contributions from all completed imaging-related stages, and is available for reading or refinement by subsequent stages. |

Imaging workflows consist of two separate phases: a lightweight planning phase (for example, `makeimlist`, `editimlist`) that assembles imaging instructions, target lists, and imaging-mode heuristics and a computationally intensive execution phase (for example, `makeimages`) that performs the heavy imaging work.

**Implementation notes** — imaging state is stored as ad-hoc attributes on the context object with no formal schema. Planning, execution, and heuristic implementations under `pipeline/h*` read and update these attributes. Defensive `hasattr()` checks appear throughout the code to guard against attributes that may not yet exist:

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
| **Summary** | The context must allow produced science, calibrator, RMS, and sub-product images to be recorded and discovered by later tasks. |
| **Invariant** | Produced image products remain identifiable by type and available for downstream processing, reporting, and export. |

**Implementation notes** — image libraries in `pipeline/infrastructure/imagelibrary.py` provide typed registries. Imaging tasks such as `makeimages` populate them, and downstream processing, reporting, and export code reads them to discover products by category:

- `context.sciimlist` — science images
- `context.calimlist` — calibrator images
- `context.rmsimlist` — RMS images
- `context.subimlist` — sub-product images (cutouts, cubes)

---

### UC-07 — Track Current Execution Progress

| | |
|-------|---------|
| **Actor(s)** | Workflow orchestration layer, tasks, pipeline operators |
| **Summary** | The context must track which processing stage is currently executing and maintain a stable, ordered record of completed stages. Stage identity and ordering must remain coherent across session saves and resumes. |
| **Invariant** | The currently executing stage is identifiable and completed stages are recorded in stable order. |

**Implementation notes:**

- `Executor` and `StandardTaskTemplate` in `pipeline/infrastructure/basetask.py` update `context.stage`, `context.task_counter`, and `context.subtask_counter` during execution.
- The ordered `context.results` collection records completed stages and is preserved when the context is saved.

---

### UC-08 — Preserve Per-Stage Execution Record

| | |
|-------|---------|
| **Actor(s)** | Report generators, pipeline operators, workflow orchestration layer |
| **Summary** | The context must preserve a complete execution record for each completed stage, including timing, traceback information, outcomes, and the arguments used to invoke it. This record must support reporting, post-mortem diagnosis of failures, and resumption after interruption. |
| **Invariant** | Each completed stage retains its full execution record, including identity, outcome, timing, traceback, and invocation arguments, for the lifetime of the session. |

**Implementation notes** — `Results` and `ResultsProxy` are implemented in `pipeline/infrastructure/basetask.py`:

- `Results.accept()` appends each completed stage result to the ordered `context.results` collection as a `ResultsProxy`.
- Result objects carry invocation arguments, outcomes, traceback information, and timestamps used by reporting, debugging, and resume workflows.
- `ResultsProxy` writes each stage result to disk to bound memory and reloads it on demand.
- Timetracker integration provides per-stage timing data
- Results proxies store basenames for portability

---

### UC-09 — Propagate Task Outputs to Downstream Tasks

| | |
|-------|---------|
| **Actor(s)** | Any task producing output, downstream tasks |
| **Summary** | When a task produces outputs that change the processing state (e.g., new calibrations, updated flag summaries, image products, revised parameters), the context must provide a mechanism for those outputs to become available to subsequent processing steps before they execute. UC-04, UC-05, UC-06, and UC-16 are specific instances of this pattern. |
| **Postcondition** | Downstream tasks can access the propagated processing state they need. |

**Implementation notes** — tasks return `Results` objects whose `Results.accept()` path invokes `Results.merge_with_context()` to update shared context state. This immediate propagation is the intended primary mechanism in the current pipeline. Over time, some workflows also came to inspect recorded results (`context.results`) directly. Both patterns exist in the codebase, but the second should be understood as an accreted pattern rather than the original design intent.

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
| **Summary** | Within a stage, child tasks must be able to evaluate tentative changes to calibration and other processing state without changing the enclosing stage's accepted state. |
| **Invariant** | Tentative child-task changes do not affect the accepted processing state unless the enclosing task accepts them. |
| **Postcondition** | When a child task finishes, only its accepted state changes are available to subsequent processing. |

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
| **Actor(s)** | Automated processing operator, interactive pipeline user, recipe executor |
| **Summary** | The processing state must remain consistent and usable regardless of which orchestration driver created or resumed it. Non-interactive and interactive drivers must be able to supply run metadata, control partial execution, and stop or resume processing. |
| **Invariant** | Processing state is consistent and usable regardless of which orchestration driver created or resumed it, and success/failure signals are produced when appropriate. |

**Implementation notes** — multiple entry points converge on the same task execution path:

- **Task-driven**: direct task calls via CLI wrappers in `pipeline/h/cli/`
- **Command-list-driven**: PPR and XML procedure commands via `executeppr.py` / `executevlappr.py` and `recipereducer.py`

They differ in how inputs are specified, how session paths are selected, and how resume is initiated, but the persisted context is the same. Driver-supplied metadata, such as `context.project_structure`, remains available to downstream tasks through that common context.

---

### UC-12 — Save and Restore a Processing Session

| | |
|-------|---------|
| **Actor(s)** | Pipeline operator, workflow orchestration layer, pipeline developer |
| **Summary** | The complete processing state must be preservable and later recoverable so processing can resume from the preserved point. Some context-owned references can be relocated, but associated data files and paths must be made consistent with the preserved state before processing resumes. Backward compatibility across pipeline releases is not guaranteed. |
| **Postcondition** | After recovery, the processing state is operationally equivalent to the preserved state for supported resume workflows, and processing can continue from the specified point when the associated data files are consistent with that state. |

**Implementation notes:**

- `h_save()` pickles the whole context to `<context.name>.context`
- `h_resume(filename)` in `pipeline/h/cli/h_resume.py` loads a `.context` file, defaulting to the most recent context file available if `filename` is `None` or `last` is used.
- Per-stage results are proxied to disk (`saved_state/result-stageX.pickle`) to keep the in-memory context smaller
- Used by driver-managed breakpoint/resume (`executeppr(..., bpaction='resume')`) and developer debugging workflows

Relocation support is partial rather than automatic. `ResultsProxy` stores only each result pickle's basename and reconstructs its path from the loaded context's `output_dir` and `name`; `products_dir` is also stored relative to `output_dir`. The lower-level `launcher.Pipeline` loader accepts `path_overrides` that can replace selected context properties after loading, but `h_resume()` does not expose those overrides or recompute all dependent paths. Dataset paths and any external data state must therefore already be valid or be adjusted/restored separately before processing continues.

Note: The current implementation does not handle restoring data state to a past processing state and as such does not have a built-in, robust "true resume". If the data directory needs to be restored to match a saved context snapshot, this must be done manually (e.g. via having created a snapshot of the data at an earlier stage, and then restoring this state) before resuming.

---

### UC-13 — Provide State to Parallel Workers

| | |
|-------|---------|
| **Actor(s)** | Workflow orchestration layer, parallel worker processes |
| **Summary** | When work is distributed across parallel workers, each worker must efficiently receive a consistent view of the observation metadata, calibration state, and other processing state required for its work. |
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
| **Summary** | After parallel workers complete, the context must collect their individual results and incorporate them into the shared processing state. The aggregation must be safe (no conflicting concurrent writes) and complete before the next sequential step begins. |
| **Postcondition** | The processing state reflects the combined outcomes of all parallel workers. |

**Implementation notes** — worker execution is deliberately separated from context mutation:

- `TaskQueue` in `pipeline/infrastructure/mpihelpers.py` collects return values from synchronous, MPI, or Dask-backed tasks through `get_results()`. It does not itself merge those returned objects into the shared context.
- `Tier0PipelineTask` sends a pickled context snapshot to a worker and returns the worker task's result. The worker-side context is a private copy.
- `Tier0JobRequest` uses an executor copy with its context reference removed and executes with `merge=False`; `Executor.execute(..., merge=True)` is explicitly unavailable for that context-free executor.
- Aggregating tasks normally collect worker results into a parent result object and then publish combined state when that parent result is accepted. For example, `makeimages` collects `TcleanResult` worker outputs into `MakeImagesResult`; `MakeImagesResult.merge_with_context()` then registers produced images in `context.sciimlist` / `context.calimlist` and updates shared imaging state.
- For child jobs that run in-process with a context-bearing executor, `Executor.execute(job, merge=True)` commits the child result immediately by calling `result.accept(self._context)`.

This serial acceptance avoids concurrent worker writes, but it is not a transactional commit mechanism.

---

### UC-15 — Provide Read-Only State for Reporting

| | |
|-------|---------|
| **Actor(s)** | Report generators (weblog, quality reports, reproducibility scripts, pipeline statistics) |
| **Summary** | The context must provide read-only access to the observation metadata, project metadata, execution history (including per-stage domain-specific outputs such as flag summaries and plot references), QA outcomes, log references, and path information needed to generate reporting products such as weblogs, quality reports, reproducibility scripts, and pipeline statistics. |
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
| **Summary** | After each processing step completes, the context must make the relevant processing state available to QA handlers so they can evaluate the outcome against quality thresholds, which may depend on e.g. telescope, project parameters, or observation properties. The resulting quality scores must be recorded and remain retrievable for reporting. |
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
| **Summary** | The context must allow an operator to inspect the current processing state, including which datasets and calibrations are available, how many steps have completed, and what their outcomes were. Sufficient state must remain available after a failure for post-mortem analysis. |
| **Invariant** | The current processing state is inspectable at any point during execution, and sufficient information is retained to diagnose failures after the fact. |

**Implementation notes** — debugging state is preserved through the same acceptance and persistence mechanisms used for normal execution:

- `Results.accept(context)` records failure diagnostics by wrapping top-level acceptance failures in `FailedTaskResults`, preserving the exception, traceback, stage number, inputs, and timestamps before appending the stage result.
- Top-level accepted results are written as `ResultsProxy` pickles under `saved_state/result-stageX.pickle`; the proxy stores only the basename so saved contexts can be moved more easily.
- `ResultsProxy._write_stage_logs()` writes per-stage CASA log snippets into the weblog stage directory (`stageX/casapy.log`) and removes the in-memory log payload from the result pickle.
- When DEBUG logging is enabled, `Results.accept()` also writes `saved_state/context-stageX.pickle`, a full context snapshot at the end of that stage, for developer inspection.
- `WebLogGenerator.render(context)` temporarily replaces `context.results` with fully unpickled result objects while rendering, then restores the proxy list afterward.
- Test and CI utilities in `tests/testing_utils.py` load the most recent context for sanity checks and result extraction. They explicitly release the loaded context and run garbage collection because `Context -> ResultsProxy -> Context -> results` forms reference cycles that can otherwise retain large contexts between tests.

---

### UC-18 — Manage Telescope- and Array-Specific State

| | |
|-------|---------|
| **Actor(s)** | Telescope-specific tasks and heuristics, array-specific tasks and heuristics |
| **Summary** | The context must support conditional telescope-specific and array-specific extensions to the processing state. These extensions must be available to the tasks and heuristics that need them, including cases where one array mode within a telescope family has materially different state requirements from another. Generic pipeline components must not depend on or require knowledge of those telescope- or array-specific extensions. |
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
| **Summary** | The context must make the datasets, calibration state, image products, reports, scripts, path information, project identifiers, and any other information needed for export available through the processing state so export tasks can assemble them into a deliverable product package. |
| **Invariant** | The information needed to assemble a deliverable product package is accessible through the processing state. |

**Implementation notes** — the base export task and telescope-specific implementations under `pipeline/h/tasks/exportdata/`, `pipeline/hif/tasks/exportdata/`, `pipeline/hifv/tasks/exportdata/`, `pipeline/hsd/tasks/exportdata/`, and `pipeline/hsdn/tasks/exportdata/` assemble products from several parts of the context. Image-product registries are provided by `pipeline/infrastructure/imagelibrary.py`, and manifest serialization is implemented in `pipeline/h/tasks/common/manifest.py`:

- `ExportData.prepare()` creates `inputs.products_dir`, derives the OUS/status prefix from `context.get_oussid()` and `context.project_structure.recipe_name`, and exports standard OUS products from `context.logs`: PPR, weblog tarball, pipeline script, restore script, and CASA commands log.
- `_make_lists()` builds visibility and session lists from `context.observing_run.measurement_sets`, optionally filtering MSes by whether the MS has imaging data columns.
- Calibration and restore products are assembled from the active processing state: final flag versions, per-MS apply lists, per-session calibration table tarballs, and optionally final MS exports.
- `_export_images()` exports calibrator and science images from the context image libraries; the manifest records calibrator and target image products separately.
- `_make_pipe_manifest()` records CASA version, pipeline version, execution environment, recipe/procedure name, PPR, weblog, commands log, pipeline script, restore script, calibration products, MS products, and exported images using `pipeline/h/tasks/common/manifest.py`.
- ALMA, VLA, and SD export subclasses add auxiliary products and AQUA reports, then update the manifest. These auxiliary products can include continuum/flux/antenna files, target flag templates, timetracker reports, selfcal restore resources from `context.selfcal_resources`, pipeline statistics, auxiliary caltables, and auxiliary apply files.
- VLA export additionally handles flat-noise FITS products associated with exported target images. NRO export extends the SD path with a reduction template script and `nroscalefile.csv`, then records them in the NRO manifest.
