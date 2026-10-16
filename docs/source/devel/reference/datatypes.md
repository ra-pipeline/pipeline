# DataType Design

This document describes how pipeline data types (`DataType`) are represented, updated, persisted, and queried across the pipeline workflow lifecycle.

Originally, the pipeline assumed visibility data lived either in `'DATA'` (for raw data) or `'CORRECTED_DATA'` (for calibrated data). With the addition of science target splitting (`_targets.ms`), continuum subtraction (`_targets_line.ms`), and self-calibration ({func}`~pipeline.hif.cli.hif_selfcal`), visibilities in `'DATA'` or `'CORRECTED_DATA'` can represent different data states in various reduction stages. The `DataType` design tracks these calibration states so that downstream tasks (such as imaging) can automatically select the appropriate columns and datasets per field and spectral window without hardcoding column information or explicit task input instructions.

---

## Visibility Data Types

Visibility types are defined by the {class}`~pipeline.domain.DataType` enum in {mod}`pipeline.domain.datatype`:

* `RAW`: Uncalibrated visibility data.
* `REGCAL_CONTLINE_ALL`: Standard-calibrated data containing both continuum and lines for all targets and calibrators.
* `ATMCORR`: Offline atmospheric-corrected data (Single Dish).
* `BASELINED`: Baseline-subtracted data (Single Dish).
* `REGCAL_CONTLINE_SCIENCE`: Standard-calibrated data for science targets (continuum + line).
* `SELFCAL_CONTLINE_SCIENCE`: Self-calibrated data for science targets (continuum + line).
* `IM_CONTLINE_SCIENCE`: Transformed/re-gridded science data for continuum+line imaging.
* `REGCAL_CONT_SCIENCE`: Standard-calibrated continuum-only science data.
* `SELFCAL_CONT_SCIENCE`: Self-calibrated continuum-only science data.
* `IM_CONT_SCIENCE`: Transformed/re-gridded science data for continuum imaging.
* `REGCAL_LINE_SCIENCE`: Standard-calibrated, continuum-subtracted line data.
* `SELFCAL_LINE_SCIENCE`: Self-calibrated, continuum-subtracted line data.
* `IM_LINE_SCIENCE`: Transformed/re-gridded science data for spectral line imaging.

### In-Memory Representation (`MeasurementSet`)

Each {class}`~pipeline.domain.MeasurementSet` domain object tracks datatype state via two attributes:

1. **`ms.data_column: dict[DataType, str]`**  
   Global mapping from `DataType` to column name (`'DATA'` or `'CORRECTED_DATA'`).
2. **`ms.data_types_per_source_and_spw: dict[tuple[str, int], list[DataType]]`**  
   Per-(source, spw) mapping from `(source_name, real_spw_id)` to the data types present in that MS (at most two: one for `'DATA'` and one for `'CORRECTED_DATA'`). Keys use real spw IDs; for multi-EB runs with virtual spws, the translation between virtual and real spw IDs is handled by `ObservingRun` query methods.

These dictionaries are managed through:

* {meth}`~pipeline.domain.MeasurementSet.set_data_column` `(dtype, column, source=None, spw=None, overwrite=False, save_to_ms=True)`
* {meth}`~pipeline.domain.MeasurementSet.get_data_column` `(dtype, source=None, spw=None)`
* {meth}`~pipeline.domain.MeasurementSet.get_data_type` `(column, source=None, spw=None)`

### On-Disk Persistence (MS `HISTORY` Table)

Starting in **v2025.1.0** (PL2025) (via {jira}`PIPE-2432`), whenever {meth}`~pipeline.domain.MeasurementSet.set_data_column` is called with `save_to_ms=True` (the default), the pipeline persists both dictionaries into the MS `HISTORY` subtable under `origin="Datatype Handler"`:

```text
data_type_per_column = {'RAW': 'DATA', ...}
data_types_per_source_and_spw = {('FIELD_A', 0): ['RAW'], ...}
```

### Inspecting DataType from an Existing MS

You can inspect the persisted datatypes directly from Python using pipeline heuristics without loading a full pipeline context:

```python
from pprint import pprint
from pipeline.infrastructure import tablereader
from pipeline.h.heuristics.importdata import get_ms_data_types_from_history

ms_path = "uid___A002_Xc3412f_X2a7d_targets_line.ms"
history_entries = tablereader.MeasurementSetReader.get_history(ms_path)
data_type_per_column, data_types_per_source_spw = get_ms_data_types_from_history(history_entries)

pprint(data_type_per_column)
pprint(data_types_per_source_spw)
```

Example output from a split line MS where self-calibration succeeded on spw 23 of target `G5.89-0.39`:

```python
# data_type_per_column
{<DataType.REGCAL_LINE_SCIENCE: 11>: 'DATA',
 <DataType.SELFCAL_LINE_SCIENCE: 12>: 'CORRECTED_DATA'}

# data_types_per_source_spw
{('G5.89-0.39', 22): [<DataType.REGCAL_LINE_SCIENCE: 11>],
 ('G5.89-0.39', 23): [<DataType.REGCAL_LINE_SCIENCE: 11>,
                      <DataType.SELFCAL_LINE_SCIENCE: 12>],
 ('G5.89-0.39', 24): [<DataType.REGCAL_LINE_SCIENCE: 11>]}
 ...
```

---

## Lifecycle Across Standard Reduction Workflows

The diagram below outlines when datatype information is assigned and propagated through a typical ALMA / VLA interferometry run:

```mermaid
flowchart TD
    A["Raw Ingestion<br><code>h*_importdata</code>"] -->|"DATA: RAW<br>CORRECTED: REGCAL_CONTLINE_ALL (if present)"| B["Calibration Application<br><code>h*_applycal</code>"]
    B -->|"CORRECTED_DATA: REGCAL_CONTLINE_ALL"| C["Split Science Targets<br><code>mssplit / transformimagedata</code>"]
    C -->|"DATA: REGCAL_CONTLINE_SCIENCE"| D["Transform / Line Splitting<br><code>hif_mstransform / hifv_mstransform</code>"]
    D -->|"_targets.ms DATA:<br>REGCAL_CONT_SCIENCE / IM_CONTLINE_SCIENCE"| E["Self-Calibration<br><code>hif_selfcal</code>"]
    D -->|"_targets_line.ms DATA:<br>REGCAL_LINE_SCIENCE"| F["Continuum Subtraction<br><code>hif_uvcontsub</code>"]
    E -->|"CORRECTED_DATA:<br>SELFCAL_*_SCIENCE (per field/spw)"| G["Clean Target List & Imaging<br><code>makeimlist / tclean</code>"]
    F -->|"DATA: REGCAL_LINE_SCIENCE"| G
```

### Stage Details

1. **`h*_importdata` ({func}`~pipeline.hifa.cli.hifa_importdata`, {func}`~pipeline.hifv.cli.hifv_importdata`, {func}`~pipeline.hsd.cli.hsd_importdata`)**:
   * Reads MS `HISTORY` via `pipeline.h.heuristics.importdata.get_ms_data_types_from_history()`.
   * If entries are found (e.g. importing a pre-existing target MS), they are restored into `ms.data_column` and `ms.data_types_per_source_and_spw`.
   * If the user provided the `datacolumns` parameter, user-specified types override history.
   * If no history exists (standard ASDM import), defaults to:
     * `'DATA' -> DataType.RAW`
     * `'CORRECTED' -> DataType.REGCAL_CONTLINE_ALL` (if `CORRECTED_DATA` column exists).
2. **`h*_applycal` ({func}`~pipeline.hif.cli.hif_applycal`, {func}`~pipeline.hifv.cli.hifv_applycals`)**:
   * After caltables are applied, `ApplycalResults.merge_with_context()` sets `DataType.REGCAL_CONTLINE_ALL` on `'CORRECTED_DATA'`.
3. **`mssplit` / `transformimagedata`**:
   * When splitting target fields (`intent='TARGET'`), sets `'DATA'` of the new MS to `DataType.REGCAL_CONTLINE_SCIENCE`.
4. **`hif_mstransform` ({func}`~pipeline.hif.cli.hif_mstransform`) / `hifv_mstransform` ({func}`~pipeline.hifv.cli.hifv_mstransform`)**:
   * Maps parent datatypes to transformed target types (`REGCAL_CONTLINE_SCIENCE -> IM_CONTLINE_SCIENCE`, `SELFCAL_CONTLINE_SCIENCE -> IM_CONTLINE_SCIENCE`).
   * For VLA, registers `DataType.REGCAL_CONT_SCIENCE` on `_targets.ms` and `DataType.REGCAL_CONTLINE_SCIENCE` on `_targets_line.ms`.
5. **`hif_selfcal` ({func}`~pipeline.hif.cli.hif_selfcal`, {func}`~pipeline.hifv.cli.hifv_selfcal`)**:
   * When self-cal solutions are applied, maps the base `'DATA'` type to its selfcal equivalent (`REGCAL_* -> SELFCAL_*`).
   * Calls {meth}`~pipeline.domain.MeasurementSet.set_data_column` with `(dtype_applied, 'CORRECTED_DATA', source=field, spw=spw_sel)` for each successfully calibrated target and SPW.
6. **`hif_uvcontsub` ({func}`~pipeline.hif.cli.hif_uvcontsub`)**:
   * Sets `'DATA'` of `_targets_line.ms` to `DataType.REGCAL_LINE_SCIENCE`.
7. **Single Dish (`hsd_atmcor`, `hsd_baseline`)**:
   * Sets `'DATA'` to `DataType.ATMCORR` after atmospheric correction, and `DataType.BASELINED` after baseline subtraction.

---

## Restore Workflows & Self-Calibration

### Standard Restore ({func}`~pipeline.hifa.cli.hifa_restoredata` / {func}`~pipeline.hifv.cli.hifv_restoredata`)

When running standard restore tasks:

1. `importdata` runs first, setting `'DATA'` to `DataType.RAW` and writing the initial history record.
2. Caltables and flags are unpacked and restored.
3. `applycal` applies calibrations, generating `CORRECTED_DATA`, and registers `DataType.REGCAL_CONTLINE_ALL`, writing a second record to MS `HISTORY`.

> **Note on `restoredata` Scope**:  
> {func}`~pipeline.hifa.cli.hifa_restoredata` / {func}`~pipeline.hifv.cli.hifv_restoredata` only restores the parent EB (`<uid>.ms`). It does not split `_targets.ms` or apply self-calibration, so restored parent EBs will never contain `SELFCAL_*` datatypes.

### Follow-up Self-Calibration Restore (`hif_selfcal` Apply-Only Mode)

To restore self-calibrated data, a workflow should execute {func}`~pipeline.hif.cli.hif_selfcal` in restore mode (`recal=False`, `apply=True`) following the standard restore and target split:

```mermaid
sequenceDiagram
    autonumber
    participant RestoreScript as Restore Script
    participant hif_selfcal as hif_selfcal
    participant selfcal_json as selfcal.json / auxproducts
    participant TargetMS as _targets.ms (TableWriter)
    participant History as _targets.ms HISTORY

    RestoreScript->>hif_selfcal: hif_selfcal(recal=False, apply=True)
    hif_selfcal->>selfcal_json: _check_restore_from_resources()
    selfcal_json-->>hif_selfcal: scal_targets (SC_success flags)
    hif_selfcal->>TargetMS: _apply_scal(): apply caltables to CORRECTED_DATA
    hif_selfcal->>hif_selfcal: merge_with_context() -> _register_datatype()
    hif_selfcal->>History: set_data_column(SELFCAL_*_SCIENCE, 'CORRECTED_DATA', source, spw)
```

1. **Solution Discovery**: `hif_selfcal` checks for `selfcal.json` in the current working directory, in `../products/`, or inside `auxproducts.tgz`. If found, it sideloads the solutions and skips the self-cal solver.
2. **Selective Application**: For each target where self-calibration succeeded (`SC_success == True`), caltables are applied to `CORRECTED_DATA`. Unsuccessful targets are left uncalibrated in `CORRECTED_DATA` (or untouched).
3. **Datatype Registration**: In `merge_with_context()`, `_register_datatype()` registers `DataType.SELFCAL_*` on `CORRECTED_DATA` scoped strictly to the successful field and SPW combinations.
4. **Target MS Persistence**: In ≥ PL2025, {meth}`~pipeline.domain.MeasurementSet.set_data_column` writes the updated dictionaries to the `HISTORY` table of the **split target MS** (`_targets.ms`).

---

## Where DataType Info Gets Used Downstream

### 1. Automatic Dataset Scope Resolution ({class}`~pipeline.infrastructure.vdp.StandardInputs`)

When a pipeline task executes without an explicit `vis` argument, {class}`~pipeline.infrastructure.vdp.StandardInputs` inspects the task's `Inputs.processing_data_types`:

```python
ms_pool = context.observing_run.get_measurement_sets_of_type(processing_data_types)
```

This ensures imaging tasks automatically process `_targets.ms` or `_targets_line.ms` rather than raw parent EBs without needing hardcoded paths.

### 2. Imaging Column & Fallback Selection (`MakeImList` / `EditImList`)

In {func}`~pipeline.hif.cli.hif_makeimlist` and {func}`~pipeline.hif.cli.hif_editimlist`:

1. `DataType.get_specmode_datatypes(intent, specmode)` defines candidate types in fallback order:
   * **Science targets** (e.g. continuum):  
     `[IM_CONTLINE_SCIENCE, SELFCAL_CONTLINE_SCIENCE, REGCAL_CONTLINE_SCIENCE, REGCAL_CONTLINE_ALL, RAW]`  
     Selfcal data is preferred over regcal. If science targets have not been split to `_targets.ms` yet, it falls back to `REGCAL_CONTLINE_ALL` in the parent MS, and down to `RAW` if uncalibrated.
   * **Calibrators**:  
     `[REGCAL_CONTLINE_ALL, RAW]`
2. For each target and virtual spw, the pipeline queries:

   ```python
   observing_run.get_measurement_sets_of_type(dtypes=specmode_datatypes, source=field, spw=spw, vis=vislist)
   ```

   This translates virtual spw to real spw per MS and checks {meth}`~pipeline.domain.MeasurementSet.get_data_column`. If selfcal data exists for that (field, real spw), imaging reads `CORRECTED_DATA` (`SELFCAL_*`); otherwise it falls back to `DATA` (`REGCAL_*`).
3. The selected data type is recorded in `CleanTarget['datatype']` (with any fallback notes in `CleanTarget['datatype_info']`) and displayed in the WebLog.

### 3. Image Product Filenames and Headers

* **Filenames**: `EditImList` derives `datatype_suffix` (`'selfcal'` or `'regcal'`) based on the clean target's datatype, which `pipeline.infrastructure.filenamer` inserts into the FITS and CASA image names.
* **Headers**: `pipeline.infrastructure.imageheader` records the datatype string in image metadata.

### 4. WebLog & QA Handling

* **WebLog**: Imaging templates render badges (`RAW`, `REGCAL`, `SELFCAL`, `IMAGING`) via `DataType.get_short_datatype_desc()` and group diagnostic plots accordingly.
* **QA Scoring**: In `pipeline.h.tasks.importdata.qa`, `HISTORY` table checks explicitly ignore entries where `origin="Datatype Handler"` so that persisted datatype records do not generate spurious QA warnings.

---

## Version Compatibility & Caveats

```{list-table}
:header-rows: 1
:widths: 22 24 24 30

* - Pipeline Version
  - {func}`~pipeline.hif.cli.hif_selfcal` Available
  - Datatypes in MS `HISTORY`
  - Method to Check Self-Cal Success
* - **≥ PL2025 (v2025.1.0+)**
  - Yes
  - **Yes**
  - MS `HISTORY` or `selfcal.json`
* - **PL2023 / PL2024**
  - Yes (introduced v2023.1.0)
  - **No** (in-memory context only)
  - `selfcal.json` (or `auxproducts.tgz` caltables)
* - **≤ PL2022**
  - No
  - **No**
  - N/A
```

### Important Practical Caveats

1. **Older Pipeline Runs Have No Datatypes in MS HISTORY**:  
   Because MS `HISTORY` persistence was added in PL2025 ({jira}`PIPE-2432`), datasets processed with or restored under PL2023 or PL2024 will return empty results from `get_ms_data_types_from_history()`.
2. **Reliable Determination of Self-Calibration Status**:  
   If checking whether self-calibration succeeded across arbitrary versions (e.g. in archiving or verification scripts), inspect `selfcal.json` (checking `sc_lib['SC_success']`) rather than assuming MS `HISTORY` is populated. This matches the method used internally by {func}`~pipeline.hif.cli.hif_selfcal` during apply-only restore.

### Related JIRA Tickets

* {jira}`PIPE-2432`: Initial persistence of datatype dictionaries to MS `HISTORY` table (`save_to_ms=True`).
* {jira}`PIPE-2492`: Saved target-phase calibrator scan metadata in `_targets.ms` history table for mosaic self-calibration.
* {jira}`PIPE-2500`: Added `recal=True` support to recalculate selfcal on data already marked with `DataType`.
* {jira}`PIPE-2555`: Handled off-tree MS writes, added `nocopy=True` support, switched history parsing to `ast.literal_eval()`, and added unit tests.

---

## Testing / Mocking DataType Setups

To test downstream tasks like `hif_makeimlist` or `hif_editimlist` without running full self-calibration, one can mock `set_data_column` calls directly on imported target MSes.

> **Prerequisite**: If the imported target MS does not yet contain a `CORRECTED_DATA` column, ensure one exists (e.g. by copying `DATA` to `CORRECTED_DATA` via CASA `tb` tool) before registering data types on `'CORRECTED_DATA'`. Otherwise `set_data_column` will raise a `ValueError`.

For example, taking two target MSes from a multi-EB run:

```python
from pipeline.domain import DataType

ctx = h_init()
hifa_importdata(
    ['uid___A002_Xed4607_Xfbf7_targets.ms', 'uid___A002_Xed4607_Xfd64_targets.ms'],
    datacolumns={'data': 'regcal_contline_science'}
)

# MS 1 (real spws 13, 15, 17, 19): set selfcal on spws 17 and 19 in CORRECTED_DATA
ctx.observing_run.measurement_sets[0].set_data_column(
    DataType.SELFCAL_CONTLINE_SCIENCE, 'CORRECTED_DATA', source='HL_Tau', spw='17'
)
ctx.observing_run.measurement_sets[0].set_data_column(
    DataType.SELFCAL_CONTLINE_SCIENCE, 'CORRECTED_DATA', source='HL_Tau', spw='19'
)

# MS 2 (real spws 5, 7, 9, 11): set selfcal on spws 7, 9, 11
ctx.observing_run.measurement_sets[1].set_data_column(
    DataType.SELFCAL_CONTLINE_SCIENCE, 'CORRECTED_DATA', source='HL_Tau', spw='7'
)
ctx.observing_run.measurement_sets[1].set_data_column(
    DataType.SELFCAL_CONTLINE_SCIENCE, 'CORRECTED_DATA', source='HL_Tau', spw='9'
)
ctx.observing_run.measurement_sets[1].set_data_column(
    DataType.SELFCAL_CONTLINE_SCIENCE, 'CORRECTED_DATA', source='HL_Tau', spw='11'
)

h_save('c1')
```

This sets up mixed calibration states across virtual spws:
* Virtual spw 13: regcal only.
* Virtual spw 15: selfcal in MS 2 (real spw 7), regcal in MS 1 (real spw 15).
* Virtual spws 17 and 19: selfcal in both MSes.

From here, you can resume `c1` and run imaging stages to verify that the expected column and data types are picked up per field and spw.
