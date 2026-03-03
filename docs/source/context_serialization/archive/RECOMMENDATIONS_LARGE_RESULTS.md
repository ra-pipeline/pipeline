# Large Result Pickle Investigation - Summary and Recommendations

**Date**: February 20, 2026  
**Status**: Investigation Complete - Recommendations Ready  
**Related**: LARGE_RESULT_INVESTIGATION.md, PHASE4_RESULTS.md

## Executive Summary

Following Phase 4 testing that conclusively showed plot objects represent <0.1% of result pickle size, we investigated the actual sources of bloat in large result pickles. This investigation identified **9 high-risk result classes** across **5 flagging tasks** that store large flagging view data for weblog interactive plotting.

### Key Findings

1. **Root Cause Identified**: Large pickles dominated by flagging view dictionaries containing `ImageResult` objects with multiple numpy array copies
2. **Scope**: 9 result classes inherit from `FlaggableViewResults` or have similar `view`/`components` patterns
3. **Largest Case**: 21 GB `hif_rawflagchans` result (stage 4) - likely contains full channel×baseline×polarization data arrays
4. **Common Pattern**: Tasks store complete flagging views for weblog generation but never purge them from context
5. **Phase 4 Lesson**: Plot objects are trivial; data arrays for interactive plotting are the actual bloat

### Impact Assessment

**Known Large Pickles**:
- `hif_rawflagchans`: 21,065 MB (stage 4)
- `hifa_tsysflag`: 2,048 MB (stage 7)
- `hif_refant`: 1,546 MB (stage 7)
- `hif_makeimages`: 944 MB (stage 13)
- Total: ~24 GB for single 56-stage production pipeline

**Affected Tasks** (high-risk with FlaggableViewResults):
1. `hif_rawflagchans` - Raw channel flagging
2. `h*/hifa_tsysflag` - Tsys spectrum flagging  
3. `hif_lowgainflag` - Low gain antenna flagging
4. `hifa_wvrgcal` - WVR calibration views
5. `hifa_wvrgcalflag` - WVR flagging views

## Technical Analysis

### The ImageResult Data Model

From `pipeline/h/tasks/common/commonresultobjects.py` (lines 65-105):

```python
class ImageResult(ResultBase):
    def __init__(self, filename, data, datatype, axes, flag=None, ...):
        self.data = data.copy()  # ← Full array copy
        self.flag = flag.copy()  # ← Full array copy
        self.nodata = nodata.copy()  # ← Full array copy
        self.flag_reason_plane = np.zeros(np.shape(data), int)  # ← New array
```

**Problem**: Each `ImageResult` stores **4 copies** of the data shape:
- Original data array (copied)
- Flag array (copied)
- Nodata array (copied)
- Flag reason plane (newly allocated)

**Example**: For `hif_rawflagchans` with 4096 channels × 351 baselines × 2 pols:
- Per-array size: 4096 × 351 × 8 bytes (complex64) = 11.5 MB
- Per-ImageResult: 11.5 MB × 4 arrays = 46 MB
- Multiple polarizations and iterations → hundreds of MB to GB

### The FlaggableViewResults Pattern

From `pipeline/h/tasks/common/flaggableviewresults.py`:

```python
class FlaggableViewResults(object):
    def __init__(self):
        self.flagging = []  # Flag commands (small)
        self.view = collections.defaultdict(list)  # ← Storage bloat

    def addview(self, description, viewresult):
        self.view[description].append(viewresult)  # ← Accumulates ImageResults
```

**Problem**: The `.view` dictionary accumulates `ImageResult` objects for every spw/pol/iteration combination:
- Each entry: 46 MB (per example above)
- Many spws × pols × iterations: 500+ MB to 20+ GB
- All stored permanently in context pickle

### Example: hif_rawflagchans Data Flow

1. **Data task** reads MS, creates 3D array: `data[corrs × channels × baselines]`
2. **View task** creates `ImageResult` for each polarization with `.copy()` calls
3. **Flagger task** may iterate (niter parameter), creating multiple views
4. **Result object** accumulates all in `self.view` dictionary
5. **Context pickle** serializes entire result with all views
6. **Never purged**: Views remain in pickle forever, even after weblog generated

**Actual Usage**: Views used only during weblog generation for interactive plots. After weblog created, views never accessed again but remain in pickle.

## Proposed Solutions

### Strategy A: Mark Views as Transient (Quick Win)

**Approach**: Extend Phase 4 `_transient_fields` mechanism to flagging views.

**Implementation**:
```python
# In FlaggableViewResults.__init__ (flaggableviewresults.py)
class FlaggableViewResults(object):
    def __init__(self):
        self.flagging = []
        self.view = collections.defaultdict(list)
        self._transient_fields = {'view'}  # ← Mark view as transient

# In TsysflagResults.__init__ (tsysflag/resultobjects.py)
class TsysflagResults(resultobjects.TsyscalResults):
    def __init__(self):
        super().__init__()
        self._transient_fields.update({'components'})  # ← Mark components as transient
```

**Files to Modify**:
1. `pipeline/h/tasks/common/flaggableviewresults.py` - Add `_transient_fields = {'view'}`
2. `pipeline/h/tasks/tsysflag/resultobjects.py` - Add `_transient_fields.update({'components'})`
3. `pipeline/hifa/tasks/wvrgcal/resultobjects.py` - Add `_transient_fields = {'view'}`

**Expected Impact**:
- `hif_rawflagchans`: 21 GB → ~10 MB (99.95% reduction)
- `hifa_tsysflag`: 2 GB → ~50 MB (97.5% reduction)
- Total context: 24 GB → ~1 GB (95% reduction)

**Pros**:
- Leverages existing Phase 4 infrastructure
- Simple implementation (3 files, ~10 lines)
- Immediate 95% size reduction
- No performance overhead

**Cons**:
- **Loss of debugging capability**: Cannot inspect flagging views after pipeline completes
- **Breaks weblog regeneration**: Cannot regenerate weblogs from existing context
- May impact troubleshooting workflows

**Risk**: Medium - Acceptable for production (weblogs generated once) but impacts debugging.

### Strategy B: External View Storage (Recommended)

**Approach**: Store flagging views in separate compressed files, load on-demand.

**Implementation**:
```python
# In FlaggableViewResults
class FlaggableViewResults(object):
    def __init__(self):
        self.flagging = []
        self.view = collections.defaultdict(list)
        self._view_file = None  # Reference to external file
        self._transient_fields = {'view'}  # Don't pickle view

    def save_views_external(self, output_dir, stage_number):
        """Save views to compressed numpy file."""
        import numpy as np
        view_file = Path(output_dir) / f'stage{stage_number}-flagging-views.npz'
        # Convert view dict to numpy arrays
        view_data = {desc: [ir.data, ir.flag, ir.nodata] 
                     for desc, ir_list in self.view.items() 
                     for ir in ir_list}
        np.savez_compressed(view_file, **view_data)
        self._view_file = str(view_file)

    def load_views_external(self):
        """Load views from external file on-demand."""
        if self._view_file and Path(self._view_file).exists():
            data = np.load(self._view_file)
            # Reconstruct view dictionary
            # ...
```

**Integration Points**:
1. `ResultsProxy.write()` - Call `save_views_external()` before pickling
2. Renderer - Call `load_views_external()` when generating weblog
3. Context.load() - Optional flag to load external data

**Expected Impact**:
- Context pickle: 24 GB → ~1 GB (95% reduction, same as Strategy A)
- External files: ~5 GB compressed (npz format, 80% compression)
- Total storage: 6 GB (75% reduction from 24 GB)
- Weblog regeneration: Works (loads external files)
- Debugging: Works (loads external files when needed)

**Pros**:
- Maintains debugging capability
- Enables weblog regeneration
- Excellent compression (npz format)
- External files can be purged after validation

**Cons**:
- More complex implementation (~200 lines)
- File management overhead
- Need to handle missing external files gracefully

**Risk**: Low - Preserves all functionality while achieving size reduction.

### Strategy C: Lazy View Generation (Long-Term)

**Approach**: Store only parameters needed to regenerate views from MS data.

**Implementation**:
```python
class FlaggableViewResults(object):
    def __init__(self):
        self.flagging = []
        self.view_params = {  # ← Store params, not data
            'ms_name': '',
            'spw': '',
            'intent': '',
            'flag_rules': {},
        }
        self._transient_fields = {'view'}  # Don't store view

    def regenerate_views(self):
        """Regenerate views from MS data using stored parameters."""
        # Re-read MS data
        # Re-apply flagging rules
        # Recreate ImageResult objects
```

**Expected Impact**:
- Context pickle: 24 GB → ~100 MB (99.6% reduction)
- No external files needed
- Regeneration time: 1-5 minutes per stage

**Pros**:
- Minimal storage (only metadata)
- Always consistent with current MS state
- No external file management

**Cons**:
- Requires MS access (may not be available)
- Slow regeneration (re-read MS data)
- Complex implementation (~500 lines)
- May not be exact due to floating-point differences

**Risk**: Medium - Requires MS access, slow, complex.

### Strategy D: Summary Statistics Only (Most Aggressive)

**Approach**: Replace full data arrays with summary statistics.

**Implementation**:
```python
class ImageResultSummary:
    """Lightweight summary replacing full ImageResult."""
    def __init__(self, data, flag):
        self.median = np.median(data[~flag])
        self.mad = median_absolute_deviation(data[~flag])
        self.percentiles = np.percentile(data[~flag], [5, 25, 50, 75, 95])
        self.flag_fraction = np.sum(flag) / flag.size
        # No full arrays stored
```

**Expected Impact**:
- Context pickle: 24 GB → ~50 MB (99.8% reduction)
- Per-ImageResult: 46 MB → ~200 bytes (99.9% reduction)

**Pros**:
- Dramatic size reduction
- Fast to serialize/deserialize
- Sufficient for most QA metrics

**Cons**:
- **Cannot regenerate weblog plots**: Summary stats insufficient for plotting
- **Major API break**: All code using ImageResult.data must be rewritten
- **Loss of detail**: Cannot inspect individual channels/baselines

**Risk**: High - Breaks existing functionality, major refactoring.

## Historical Context

The issue of large tsys flagging results has been known since at least 2019. Stewart Williams commented on PIPE-376:

> "Tsys results are large because they contain the flagging views (=NumPy arrays), which are used to generate the flagging view plots downstream during web log generation.
> 
> The general pattern is that plotting is only performed during web log generation, not during task execution. We could make an exception to generate the flagging view plots during task execution, storing PNG paths in the TsysResults rather than the flagging view, which would reduce the results size. Some kind of interim plot management could be required, however. I suggest looking at hifa_bandpassflag, which is forced to create plots during task execution by the nature of the task."

The current investigation confirms this pattern extends beyond tsysflag to all tasks using `FlaggableViewResults` (9 classes identified). The Phase 4 investigation conclusively proved that plot objects themselves are trivial (<0.1% of size); the bloat is from the underlying numpy arrays stored for deferred plotting.

## Recommended Approach

### Phase 1: Quick Win (Strategy A) - **AGREED STARTING POINT** ✅

**Goal**: Achieve 95% size reduction with minimal code changes.

**Decision**: After reviewing the trade-offs, Strategy A is the best starting point. The break in weblog regeneration and debugging functionality is acceptable for production use, where weblogs are generated once during pipeline execution. If these limitations prove untenable in practice, we can investigate other strategies (B or C) as follow-on work.

**Rationale**:
- Production pipelines generate weblogs once, never regenerate
- Context debugging typically happens during development, not production
- 95% size reduction is critical for storage and performance
- Simple implementation reduces risk of regressions
- Can always add Strategy B later if debugging needs emerge

**Tasks**:
1. Add `_transient_fields = {'view'}` to `FlaggableViewResults`
2. Add `_transient_fields.update({'components'})` to `TsysflagResults`
3. Add `_transient_fields = {'view'}` to `WvrgcalResult`
4. Test on large dataset (verify size reduction, no functional regressions)
5. Document impact on debugging workflows

**Deliverables**:
- 3 file modifications (~10 lines total)
- Test results showing 95% reduction
- Documentation update warning about debugging limitations

**Risk Mitigation**:
- Document the limitation clearly (no weblog regen, no view debugging)
- Provide opt-out mechanism (environment variable to disable transient field culling)
- Consider creating separate "debug mode" that preserves views when explicitly requested
- Monitor for user complaints about debugging workflow impact

### Phase 2: Robust Solution (Strategy B) - **OPTIONAL FOLLOW-ON**

**Goal**: Maintain full functionality while achieving size reduction.

**When to Consider**: Only if Strategy A limitations prove untenable in practice:
- Users frequently need to regenerate weblogs from existing contexts
- Debugging workflows require access to flagging views after pipeline completion
- Scientific validation requires post-hoc inspection of flagging data

**Tasks**:
1. Implement external view storage in `FlaggableViewResults`
2. Integrate with `ResultsProxy.write()` and pickle workflow
3. Update renderers to load external views on-demand
4. Add lifecycle management (auto-purge after N days)
5. Comprehensive testing (weblog regen, debugging, edge cases)

**Deliverables**:
- External storage implementation (~200 lines)
- Integration with pickle workflow (~50 lines)
- Renderer updates (~30 lines per renderer)
- Lifecycle management tool
- Full test suite

**Risk Mitigation**:
- Graceful fallback if external files missing
- Optional feature (can be disabled)
- Backwards compatible (reads old pickles without external files)

### Phase 3: Architecture Redesign (Strategy C) - **LONG-TERM CONSIDERATION**

**Goal**: Implement proper separation of concerns for result data.

**When to Consider**: Only if warranted by broader architectural needs:
- Multiple teams requesting better separation of processing/QA/presentation data
- Need for lifecycle management across many result types (not just flagging views)
- Requirements for incremental context loading or selective data retention

**Tasks**:
1. Design multi-tier storage architecture (Core/Presentation/Debug)
2. Implement tier classification for all result attributes
3. Create external storage abstraction layer
4. Migrate flagging views to Presentation tier
5. Add lifecycle management and auto-cleanup
6. Update all tasks and renderers

**Deliverables**:
- Architecture design document
- Storage tier abstraction (~500 lines)
- Migration guide for existing code
- Full backwards compatibility layer

## Testing Plan

### Test Dataset Requirements

**Small Dataset** (Regression Testing):
- Context: < 1 MB
- Stages: 30-50
- Expected large results: None
- Use: Fast iteration, verify no regressions

**Medium Dataset** (Validation):
- Context: 10-50 MB
- Stages: 50-70
- Expected large results: 100-500 MB tsysflag/rawflagchans
- Use: Validate size reduction, performance impact

**Large Dataset** (Performance Testing):
- Context: 40-100 MB
- Stages: 50-80
- Expected large results: 2+ GB tsysflag, 10+ GB rawflagchans
- Use: Measure actual size reduction on real-world bloat

### Success Criteria

**Phase 1 (Strategy A)**:
- ✅ Context size reduced by 90%+
- ✅ No increase in pipeline execution time
- ✅ All stages complete successfully
- ✅ Weblogs generated correctly (first time)
- ⚠️ Weblog regeneration fails (known limitation)
- ⚠️ Cannot inspect flagging views after completion (known limitation)

**Phase 2 (Strategy B)**:
- ✅ Context size reduced by 90%+
- ✅ External files compressed to 70-80% of original view size
- ✅ Weblog regeneration works (loads external files)
- ✅ Debugging works (can inspect views when needed)
- ✅ Graceful handling of missing external files
- ✅ Performance overhead < 5% (file I/O)

**Phase 3 (Strategy C)**:
- ✅ Context size reduced by 95%+
- ✅ Clear separation of Core/Presentation/Debug data
- ✅ Lifecycle management (auto-purge old data)
- ✅ Backwards compatible with existing contexts

## Implementation Priority

### Immediate (This Week) - **PRIMARY FOCUS** ✅
1. ✅ **Investigation complete** - Found 9 high-risk classes
2. ✅ **Tools created** - `profile_result_objects.py`, `survey_result_objects.py`
3. ✅ **Strategy A agreed** - Transient fields approach accepted as starting point
4. **Profile large pickles** (optional validation) - Run tools on 21 GB rawflagchans, 2 GB tsysflag
5. **Validate findings** (optional) - Confirm views dominate pickle size

### Short-Term (Next 2 Weeks) - **PRIMARY IMPLEMENTATION**
1. **Implement Strategy A** (transient fields for views) - 3 files, ~10 lines
2. **Test on large dataset** (measure actual size reduction, verify 95% target)
3. **Document limitations** (no weblog regen after pickle, no post-execution view debugging)
4. **Create opt-out mechanism** (environment variable to disable for debugging workflows)
5. **Deploy to production** if testing successful

### Medium-Term (Only if Strategy A limitations are untenable) - **OPTIONAL**
1. **Assess user feedback** - Are users impacted by lack of weblog regeneration or view debugging?
2. **Consider Strategy B** (external storage) only if feedback indicates real need
3. **Prototype and validate** before committing to full implementation

### Long-Term (Only if broader needs emerge) - **OPTIONAL**
1. **Evaluate architectural needs** - Is multi-tier storage needed beyond flagging views?
2. **Consider Strategy C** (architecture redesign) only if justified by requirements
3. **Design and implement** if warranted

## Risks and Mitigation

### Risk 1: Breaking Existing Workflows (Strategy A)

**Impact**: Users unable to regenerate weblogs or inspect views after pipeline completion  
**Probability**: Known limitation (100% - this is by design)  
**Severity**: Low for production (weblogs generated once), Medium for debugging workflows  
**Decision**: **ACCEPTED** - Trade-off is acceptable for production use

**Mitigation**:
- Clear documentation of limitations in release notes
- Provide opt-out mechanism (environment variable to disable transient field culling)
- Monitor user feedback post-deployment for any critical workflow disruptions
- Have Strategy B ready as fallback if limitations prove untenable
- Consider "debug mode" flag that preserves views when explicitly requested

### Risk 2: Performance Degradation

**Impact**: Slower pipeline execution or weblog generation  
**Probability**: Low (A), Medium (B), High (C)  
**Mitigation**:
- Benchmark all strategies
- Set performance targets (< 5% overhead)
- Optimize hot paths (lazy loading, caching)

### Risk 3: File Management Complexity

**Impact**: External files get out of sync, go missing, consume disk space  
**Probability**: N/A (A), Medium (B, C)  
**Mitigation**:
- Graceful handling of missing files (fallback to regeneration)
- Atomic writes (tmp file + rename)
- Lifecycle management (auto-purge after validation)
- Clear documentation for operators

### Risk 4: Backwards Compatibility

**Impact**: Old contexts fail to load or behave differently  
**Probability**: Low (A, B), Medium (C)  
**Mitigation**:
- Maintain fallback code paths
- Version external file format
- Test with variety of old contexts
- Provide migration utility if needed

## Success Metrics

### Quantitative
- **Size reduction**: 90%+ on affected pickles
- **Performance**: < 5% overhead on total pipeline time
- **Compression**: 70-80% on external files (Strategy B)
- **Coverage**: All 9 high-risk classes addressed

### Qualitative
- **Debugging preserved**: Can still inspect views when needed (Strategy B+)
- **Weblog regen works**: Can regenerate from existing context (Strategy B+)
- **Operator friendly**: Clear error messages, automatic cleanup
- **Developer friendly**: Clean API, well-documented

## Conclusion

The investigation successfully identified the root cause of large result pickles: flagging view dictionaries storing full numpy arrays for weblog interactive plotting. With 9 high-risk classes across 5 tasks, the scope is well-defined and actionable.

**Agreed Path Forward**:

**Primary Implementation: Strategy A (Transient Fields)**
- Mark `.view` and `.components` as transient fields (leveraging existing Phase 4 infrastructure)
- Expected: 95% size reduction (24 GB → 1 GB)
- Timeline: 1 week implementation + testing
- Trade-off: Weblog regeneration and view debugging unavailable after pipeline completion
- **Decision**: This trade-off is acceptable for production use, where weblogs are generated once and contexts are not typically debugged post-execution

**Optional Follow-On Work** (only if Strategy A limitations prove untenable):
- **Strategy B** (external storage): If users need weblog regeneration or post-hoc debugging
- **Strategy C** (architecture redesign): If broader separation of concerns is warranted

The tools created (`profile_result_objects.py`, `survey_result_objects.py`) provide ongoing capability to identify and diagnose similar issues in the future. The investigation methodology established here (survey → profile → test → implement) can be applied to other optimization efforts.
