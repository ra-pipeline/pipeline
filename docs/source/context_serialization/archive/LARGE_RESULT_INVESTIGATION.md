# Large Result Object Investigation

## Overview

This document tracks the investigation into abnormally large result pickle files in the pipeline context. Following the Phase 4 testing which showed that plot objects represent <0.1% of result pickle size, we're now investigating the actual sources of bloat.

**Status**: Active Investigation  
**Date Started**: February 20, 2026  
**Related Work**: Phase 4 results slimming (PHASE4_RESULTS.md)

## Known Issues

### 1. hif_rawflagchans: 21 GB Result Pickle

**Dataset**: Large production context (44 MB, 56 stages)  
**Pickle Size**: 21,065 MB (stage 4 result)  
**Task**: `hif_rawflagchans`

**Suspected Root Cause** (based on code analysis):
- `RawflagchansViewResults` inherits from `FlaggableViewResults`
- Stores `ImageResult` objects in `self.view` (defaultdict of lists)
- Each `ImageResult` contains multiple full numpy array copies:
  - `self.data = data.copy()` - Complete data array
  - `self.flag = flag.copy()` - Complete flag array
  - `self.nodata = nodata.copy()` - Complete nodata array
  - `self.flag_reason_plane = np.zeros(np.shape(data), int)` - Additional array

**Code Locations**:
- Result object: `pipeline/hif/tasks/rawflagchans/resultobjects.py`
- Data task: `pipeline/hif/tasks/rawflagchans/rawflagchans.py` (lines 300-400)
- View generator: `pipeline/hif/tasks/rawflagchans/rawflagchans.py` (lines 400-504)
- ImageResult class: `pipeline/h/tasks/common/commonresultobjects.py` (lines 65-105)

**Data Flow**:
1. `RawflagchansData.prepare()` reads MS data and creates 3D arrays: `data[corrs x channels x baselines]`
2. For each polarization, creates `ImageResult(data=data[icorr], flag=flag[icorr], ...)`
3. `ImageResult.__init__` calls `.copy()` on all input arrays
4. Multiple `ImageResult` objects stored in `self.view[description]` list
5. Entire result object pickled with all array copies

### 2. h*_tsysflag: 2 GB Result Pickle

**Dataset**: Production ALMA-IF dataset  
**Pickle Size**: 2,048 MB (stage 7 result)  
**Task**: `hifa_tsysflag` / `h_tsysflag` / `hsd_tsysflag`

**Related Ticket**: PIPE-2224 (Context size inflation for h*_tsysflag)

**Root Cause** (from user-provided analysis):
- `TsysflagResults.components` contains multiple `TsysflagspectraResults` objects
- Each component result inherits from `FlaggableViewResults`
- The `.view` dictionary stores `ImageResult` objects per spw/pol combination
- Example breakdown:
  - `components['fieldshape'].view`: 59.96 MB (14 entries, each with ImageResult arrays)
  - `components['toomany'].view`: 56.11 MB
  - Total across all components: ~233 MB in memory, 2 GB pickled

**Code Locations**:
- Result object: `pipeline/h/tasks/tsysflag/resultobjects.py`
- TsysflagspectraResults: inherits from `FlaggableViewResults`
- FlaggableViewResults: `pipeline/h/tasks/common/flaggableviewresults.py`

**Sample View Structure**:
```python
r0.components['fieldshape'].view = defaultdict(list, {
    'File:uid___A002_X10dc577_X19b1.ms.h_tsyscal.s6_1.tsyscal.tbl Intent:ATMOSPHERE Field:None SpW:16 Pol:X': 
        [<ImageResult object>],
    # ... 14 total entries (7 spws × 2 pols)
})
```

**Historical Context** (Stewart Williams comment on PIPE-376):
> "Tsys results are large because they contain the flagging views (=NumPy arrays), which are used to generate the flagging view plots downstream during web log generation.
> 
> The general pattern is that plotting is only performed during web log generation, not during task execution. We could make an exception to generate the flagging view plots during task execution, storing PNG paths in the TsysResults rather than the flagging view, which would reduce the results size. Some kind of interim plot management could be required, however. I suggest looking at hifa_bandpassflag, which is forced to create plots during task execution by the nature of the task."

This pattern of storing flagging views for deferred plotting is the root cause of bloat across multiple flagging tasks.

### 3. Pattern: view Dictionaries with ImageResult Lists

**Common Pattern Across Multiple Tasks**:
Tasks that inherit from `FlaggableViewResults` all have this pattern:
- `self.view = collections.defaultdict(list)` stores flagging views
- Each view entry contains one or more `ImageResult` objects
- `ImageResult` stores multiple full numpy array copies
- All used for weblog interactive plotting

**Affected Tasks** (preliminary list):
- `hif_rawflagchans`
- `hifa_tsysflag`
- `h_tsysflag` 
- `hsd_tsysflag`
- `hifa_bandpassflag`
- `hifa_gfluxscaleflag`
-  `hifa_polcalflag`
- `hifa_targetflag`
- Potentially others inheriting from `FlaggableViewResults`

## Investigation Plan

### Phase 1: Profiling ✅ COMPLETE

**Tool Created**: `tools/profile_result_objects.py`

**Features**:
- Load result pickles and profile attribute sizes
- Identify top 10 largest attributes
- Analyze numpy arrays, dictionaries, defaultdicts
- Special handling for `.view` and `.components` attributes
- Export JSON reports for further analysis

**Usage**:
```bash
# Profile single result
python tools/profile_result_objects.py /path/to/results-stage7.pickle -v

# Profile all large results
python tools/profile_result_objects.py /path/to/pipeline/output --all --min-size-mb 100

# Export JSON report
python tools/profile_result_objects.py /path/to/output --all --json large_results.json
```

### Phase 2: Codebase Survey ✅ COMPLETE

**Tool Created**: `tools/survey_result_objects.py`

**Features**:
- AST-based scanning of all resultobjects.py files
- Identifies classes inheriting from FlaggableViewResults
- Detects `.view` and `.components` attributes
- Categorizes by risk level (high/medium/low)
- Exports detailed JSON report

**Survey Results**:
Found 33 result classes total across 22 files:
- **9 high-risk classes**: Inherit FlaggableViewResults or have view/components
- **8 medium-risk classes**: Have transient fields or large collections
- **16 low-risk classes**: Simple result objects

**High-Risk Tasks Identified**:
1. **hif_rawflagchans** (2 classes):
   - `RawflagchansResults` - inherits FlaggableViewResults
   - `RawflagchansViewResults` - inherits FlaggableViewResults

2. **h*_tsysflag** (3 classes):
   - `TsysflagResults` - has `.components` OrderedDict
   - `TsysflagspectraResults` - inherits FlaggableViewResults
   - `TsysflagViewResults` - inherits FlaggableViewResults

3. **hif_lowgainflag** (2 classes):
   - `LowgainflagResults` - inherits FlaggableViewResults
   - `LowgainflagViewResults` - inherits FlaggableViewResults

4. **hifa_wvrgcal** (1 class):
   - `WvrgcalResult` - has `.view` defaultdict (line 45 in wvrgcal/resultobjects.py)

5. **hifa_wvrgcalflag** (1 class):
   - `WvrgcalflagViewResults` - inherits FlaggableViewResults

**Key Finding**: All 9 high-risk classes are related to flagging tasks that store flagging views for weblog interactive plotting.

### Phase 3: Root Cause Validation (In Progress)

**Tasks**:
1. ✅ Survey codebase for all FlaggableViewResults classes (9 found)
2. **TODO**: Run profiling tool on known large pickles (21 GB hif_rawflagchans, 2 GB tsysflag)
3. **TODO**: Confirm that `.view` dictionaries and their `ImageResult` contents dominate
4. **TODO**: Measure overhead from multiple array copies in `ImageResult.__init__`
5. **TODO**: Determine if flagging views are actually needed after weblog generation

### Phase 4: Usage Pattern Analysis (Next)

**Questions to Answer**:
1. Are flagging views used after weblog generation?
2. Could views be stored externally (separate files) and loaded on-demand?
3. Are full data arrays needed, or just summary statistics?
4. Could ImageResult use views of arrays instead of copies?
5. Is `flag_reason_plane` actually used? (initialized but rarely populated)

### Phase 5: Slimming Strategies (TODO)

**Potential Approaches**:

#### A. Mark Flagging Views as Transient (Like Phase 4 Plots)
```python
# In FlaggableViewResults or task result objects
self._transient_fields.update({'view'})
```
- **Pros**: Simple, leverages existing Phase 4 infrastructure
- **Cons**: Loss of debugging capability, may break weblog regeneration

#### B. External Storage for Views
```python
# Store views separately, load on-demand
self.view_file = 'stage7-flagging-views.npy'  # NumPy compressed
# Load only when needed for weblog or debugging
```
- **Pros**: Keeps data available, reduces pickle size
- **Cons**: More complex, file management overhead

#### C. Lazy View Generation
```python
# Store only parameters needed to regenerate views
self.view_params = {'raw_data_path': ..., 'flag_params': ...}
# Regenerate views on-demand from MS data
```
- **Pros**: Minimal storage, always up-to-date with MS
- **Cons**: Requires MS access, slow regeneration

#### D. Replace ImageResult Array Copies with Views
```python
# In ImageResult.__init__, use array views instead of copies
self.data = data  # View, not copy
self.flag = flag  # View, not copy
```
- **Pros**: Reduces memory footprint immediately
- **Cons**: Risk of unintended mutations, may break existing code

#### E. Store Summary Statistics Instead of Full Arrays
```python
# Instead of full data array, store:
self.data_summary = {
    'median': np.median(data),
    'mad': mad(data),
    'percentiles': np.percentile(data, [5, 25, 50, 75, 95]),
}
```
- **Pros**: Dramatic size reduction (KB vs GB)
- **Cons**: Loss of full data for post-hoc analysis, major API change

#### F. Compress Arrays Before Pickling
```python
# In Results.slim_for_pickle()
import gzip
for result in self.view.values():
    result.data_compressed = gzip.compress(result.data.tobytes())
    del result.data  # Remove uncompressed
```
- **Pros**: Significant compression (60-80%), maintains data availability
- **Cons**: Overhead on load/save, more complex implementation

## Architecture Issues

### Core Problem: Information Flow Between Processing/QA/Presentation

This issue highlights fundamental architecture problems:

**Current Architecture**:
```
Task Processing → Result Object → Context Pickle → Weblog Generation
                     ↓                  ↓
              (Stores everything for posterity)
```

**Issues**:
1. **No separation of concerns**: Result objects serve multiple purposes:
   - Processing results (flags to apply)
   - QA metrics (scores, statistics)
   - Presentation data (full arrays for plots)
   - Debugging data (intermediate computations)

2. **No lifecycle management**: All data kept indefinitely:
   - Presentation data needed only during weblog generation
   - Debugging data needed only when troubleshooting
   - But both stored forever in context pickle

3. **No lazy loading**: Everything loaded at once:
   - Context.load() unpickles entire result tree
   - Even when only metadata or specific stages needed

**Ideal Architecture**:
```
Task Processing → Results (slim) → Context Pickle (metadata + refs)
                     ↓                         ↓
              Presentation Data → External Store (loaded on-demand)
                     ↓
              Debugging Data → Separate Files (optional retention)
```

**Benefits**:
- Context pickle contains only essential metadata and references
- Presentation data loaded only during weblog generation
- Debugging data stored separately, can be purged after validation
- Result objects remain small and fast to serialize

### Proposed Long-Term Solution

**Multi-Tier Storage System**:

1. **Tier 1 - Core Context** (always in pickle):
   - Task completion status
   - QA scores and flags to apply
   - Calibration tables and metadata
   - Small summary statistics

2. **Tier 2 - Presentation Data** (external, auto-loaded for weblogs):
   - Flagging view arrays
   - Plot data and statistics
   - Stored in compressed NumPy files or HDF5
   - File references in context: `view_data_file='stage7-views.npz'`

3. **Tier 3 - Debugging Data** (external, manual load):
   - Full intermediate computations
   - Detailed array diagnostics
   - Optional retention, purgeable after validation
   - Loaded only when explicitly requested

**Implementation Phases**:
1. Phase A: Identify and classify all result object attributes by tier
2. Phase B: Implement external storage mechanism with automatic loading
3. Phase C: Migrate flagging views to Tier 2 storage
4. Phase D: Add lifecycle management (auto-purge Tier 3 after N days)

## Testing Datasets

### Small Dataset: ALMA-IF
- Context: 914 KB
- Stages: 48
- Known large results: None (all < 50 MB)
- Use case: Fast iteration, regression testing

### Large Dataset: Production
- Context: 44 MB
- Stages: 56
- Known large results:
  - Stage 4 (hif_rawflagchans): 21,065 MB
  - Stage 7 (hif_refant): 1,546 MB
  - Stage 13 (hif_makeimages): 944 MB
- Use case: Real-world validation, performance testing

### Additional Datasets Needed
- **High spectral resolution**: Many channels → large channel axis in arrays
- **Many baselines**: Large antenna array → large baseline axis
- **Multi-EB**: Multiple execution blocks → repeated view storage

## Metrics to Track

### Before Optimization
- **Total result pickle size**: Sum across all stages
- **Largest N result pickles**: Top 5-10 by size
- **Memory footprint**: get_obj_size() for loaded results
- **Load time**: Time to Context.load()

### After Optimization
- **Size reduction**: % decrease in pickle sizes
- **Performance impact**: Load time, weblog generation time
- **Functional validation**: All stages complete, weblogs identical
- **Debugging impact**: Can still inspect flagging views when needed

### Target Metrics
- **hif_rawflagchans**: 21 GB → < 100 MB (99.5% reduction)
- **h*_tsysflag**: 2 GB → < 50 MB (97.5% reduction)
- **Total context**: 24 GB → < 1 GB (95% reduction)

## Next Steps

1. ✅ **Create profiling tool** (`profile_result_objects.py`)
2. ✅ **Create survey tool** (`survey_result_objects.py`)
3. ✅ **Survey all tasks** inheriting from `FlaggableViewResults`:
   - Found 9 high-risk classes across 5 tasks
   - All related to flagging with weblog plotting
4. **Run profiling on known large datasets**:
   - Profile 21 GB hif_rawflagchans result
   - Profile 2 GB tsysflag result
   - Identify exact attributes consuming space
5. **Analyze usage patterns**:
   - Grep for `.view` access patterns in renderer code
   - Determine if views needed after weblog generation
   - Check if views accessed during QA scoring
6. **Prototype slimming strategy**:
   - Start with Strategy A (transient fields) for quick win
   - Compare with Strategy F (compression) for data retention
   - Measure impact on both approaches
7. **Document recommendations**:
   - Short-term: Immediate wins (transient fields, compression)
   - Long-term: Architecture redesign (multi-tier storage)

## Related Documentation

- `PHASE4_RESULTS.md`: Phase 4 testing showing plots are not the issue
- `COMPLETE_IMPLEMENTATION_SUMMARY.md`: Full context optimization work
- `EXECUTIVE_SUMMARY.md`: High-level status of all phases
- `estimate_results_slimming.py`: Post-hoc analysis tool (revealed 0% from plots)
- `profile_result_objects.py`: Tool for detailed result profiling
- `survey_result_objects.py`: AST-based survey of all result classes
- `result_object_survey.json`: Complete survey results (9 high-risk classes identified)

## Investigation Tools Created

### 1. profile_result_objects.py (474 lines)
Detailed profiling of individual result pickle files:
- Attribute-level size breakdown
- Special handling for numpy arrays, view dictionaries
- Top 10 largest attributes identification
- JSON export for analysis

### 2. survey_result_objects.py (353 lines)  
AST-based scanning of entire codebase:
- Finds all result classes (33 total)
- Identifies FlaggableViewResults inheritance (9 classes)
- Detects view/components attributes
- Risk categorization (high/medium/low)
- JSON export for cross-referencing

**Combined Usage**:
```bash
# Step 1: Survey codebase to find high-risk classes
python tools/survey_result_objects.py --verbose --json survey.json

# Step 2: Profile actual pickles from high-risk tasks
python tools/profile_result_objects.py /path/to/hif_rawflagchans/results-stage4.pickle -v

# Step 3: Cross-reference findings
# - Which high-risk classes actually produce large pickles?
# - What attributes dominate in practice?
# - How much can be saved by marking as transient?
```

## References

- **PIPE-2224**: `hi*_tsysflag` task result object size
- **Phase 4 Investigation**: Rigorous testing methodology proving plots not the cause
