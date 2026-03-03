# Stage 14 (hifa_bandpass) Optimization Investigation

## Summary

Stage 14 (hifa_bandpass) result pickle is **55 MB** with **zero reduction** from Strategy A. Investigation reveals this is a nested `ResultsList` containing a single `BandpassResults` object, which differs significantly from flagging task results that benefited from Strategy A.

**Key Finding**: The 55 MB is NOT stored in view arrays (which Strategy A targets), but in calibration solution data within the result object attributes.

---

## Current Structure

### Result Type
```
ResultsList
    └── BandpassResults (1 item)
        ├── metadata: dict
        ├── inputs: ResultInput objects
        ├── logrecords: list
        ├── qa: dict
        ├── phaseup_snr_expected: float
        ├── phaseup_caltable_for_phase_rms: ???
        ├── solint_adjustments: ???
        ├── low_channel_solutions: ???
        ├── timestamps: ???
        ├── preceding: ???
        ├── pool: ???
        └── [other attributes]
```

### Attributes Identified

**Public Attributes**:
```
accept, applies_adopted, error, final, inputs, logrecords, low_channel_solutions,
merge_with_context, metadata, phaseup_caltable_for_phase_rms, phaseup_snr_expected,
pool, preceding, qa, slim_for_pickle, solint_adjustments, stage_number, task,
timestamps, unregister_existing, uuid
```

**Potential Large Attributes** (need investigation):
- `low_channel_solutions`: Likely large array of calibration solutions
- `solint_adjustments`: Potentially large adjustment data
- `phaseup_caltable_for_phase_rms`: Calibration table data
- `pool`: Unknown, could be large
- `preceding`: Unknown, could be large or reference to other results
- `timestamps`: Could be large time array

---

## Investigation Plan

### Step 1: Detailed Attribute Profiling

```bash
python tools/profile_result_objects.py result-stage14.pickle --deep-dive
```

**Expected Output**:
- Size breakdown by attribute
- Type information for each attribute
- Identification of largest 5-10 attributes
- Nested structure of large attributes

### Step 2: Analyze Calibration Solution Storage

**Questions**:
1. Is `low_channel_solutions` a copy of bandpass calibration table?
2. Is it already stored in callibrary somewhere?
3. Should it be marked transient (can be regenerated)?

**Investigation Approach**:
```python
import pickle

with open('result-stage14.pickle', 'rb') as f:
    result = pickle.load(f)
    bandpass = result[0]
    
    # Check what low_channel_solutions contains
    low_ch = getattr(bandpass, 'low_channel_solutions', None)
    if low_ch:
        print(f"low_channel_solutions type: {type(low_ch)}")
        print(f"Structure: {type(low_ch).__dict__ if hasattr(low_ch, '__dict__') else 'N/A'}")
        
        # If it's an array or large object
        import sys
        print(f"Approximate size: {sys.getsizeof(low_ch) / 1_000_000:.1f} MB")
        
        # If it's a list/dict, show structure
        if isinstance(low_ch, (list, dict)):
            print(f"Contents: {len(low_ch)} items")
```

### Step 3: Check for Duplication with Calibration Library

**Hypothesis**: The bandpass calibration table is already stored in the callibrary attribute of the context. The result object may contain a duplicate copy.

**Investigation**:
```python
# Compare calibration solutions in result vs. context callibrary
# (requires access to full context pickle)
# Check if solutions are identical or if one is a view of the other
```

### Step 4: Analyze `pool`, `preceding`, and Other Unknowns

**For each large attribute**:
- Print type and size
- If complex object, print attribute structure
- Check if it's a reference (would be small) vs. copy (would be large)
- Determine if transient candidate

---

## Optimization Strategies (Priority Order)

### Strategy 1: Mark Large Calibration Data as Transient (High Priority)

**Hypothesis**: If `low_channel_solutions` is a copy of bandpass calibration data that's already stored in callibrary, mark it transient.

**Implementation**:
```python
# In pipeline/hifa/tasks/bandpass/resultobjects.py (or similar)

class BandpassResults(Results):
    def __init__(self):
        super().__init__()
        # Mark calibration solutions as transient if they're duplicates
        # of callibrary entries
        self._transient_fields = {
            'low_channel_solutions',  # If this is a duplicate
            # Add others here after investigation
        }
```

**Expected Savings**: 10-30 MB (if these represent duplicate calibration data)

**Validation**:
- Verify solutions can be regenerated from callibrary
- Confirm weblog rendering still works (may need defensive guards in renderer)
- Check that final products are identical (imaging, etc.)

### Strategy 2: External Calibration Table Storage (Medium Priority)

**Hypothesis**: Store bandpass calibration solutions externally (like CASA tables), include only reference in pickle.

**Approach**:
- Store as CASA table in output directory
- Include filename reference in result object
- On load, re-open table if needed
- Reduce result pickle size by 20-40 MB

**Effort**: Medium (requires refactoring result storage)  
**Risk**: Medium (must ensure table accessibility throughout pipeline)  
**Benefit**: Significant space savings, improved pipeline flexibility

### Strategy 3: Compress or Summary-Only Storage (Low Priority)

**Hypothesis**: If solutions data must be in pickle, can it be compressed or reduced to summary statistics?

**Approach**:
- Store only summary statistics (mean, std, min, max per channel)
- Compress large arrays using numpy compression
- Lazy-load full solutions on first access

**Effort**: Medium  
**Risk**: Low (optional enhancement)  
**Benefit**: 30-50% reduction if solutions are large arrays

### Strategy 4: Investigate Non-Essential Attributes (Low Priority)

**Hypothesis**: Some attributes are populated but not essential for downstream tasks.

**Approach**:
- For each large attribute, trace its usage in downstream tasks
- If not used after bandpass stage, mark as transient
- Include in defensive guards if used in weblog rendering

**Effort**: Low (investigation only)  
**Benefit**: 5-15 MB potential savings

---

## Implementation Plan (Recommended)

### Phase 1: Detailed Profiling (1-2 hours)

1. Run `profile_result_objects.py` with deep-dive on Stage 14
2. Identify top 5 largest attributes by size
3. Document findings in investigation report

### Phase 2: Validation & Testing (2-4 hours)

1. Create test case that marks identified attributes as transient
2. Run full hifa_calimage pipeline on small dataset
3. Verify:
   - Weblogs render correctly
   - Final products identical to baseline
   - Storage reduction achieved

### Phase 3: Production Validation (1 day)

1. Run on large multi-EB dataset
2. Measure actual storage reduction
3. Document any issues or surprises

### Phase 4: Implementation & Merge (1-2 hours)

1. Update `BandpassResults` class with transient fields
2. Add defensive guards to bandpass renderer if needed
3. Create commit and update PR
4. Merge to main branch

---

## Known Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Transient data needed for weblog rendering | Medium | Profile renderer usage, add defensive guards as with flagging tasks |
| Calibration solutions needed downstream | Medium | Trace usage in downstream tasks, validate product creation |
| Data duplication in callibrary | Low | Document if solutions are duplicates, explain why stored in both places |
| Complex nested structures | Medium | Use deep profiling tool to understand structure before marking transient |

---

## Timeline & Resource Allocation

**Total Effort**: 4-8 hours  
**Expected Savings**: 20-40 MB (36-73% of Stage 14 if successful)  
**ROI**: High (if successful, combines with Strategy A for 95%+ total reduction)

---

## Next Steps

1. **User confirms**: Is the investigation output (`BandpassResults` attributes) sufficient, or need deeper profiling?
2. **Profiling**: Run detailed attribute size analysis on Stage 14 result
3. **Decision**: Based on findings, decide which optimization strategy to pursue
4. **Implementation**: Execute chosen strategy and validate

---

## Questions for Developer

1. **Bandpass Data**: Are `low_channel_solutions` and other solution data duplicates of calibration tables already stored in callibrary?

2. **Renderer Dependencies**: Does the bandpass weblog renderer need access to `low_channel_solutions` or other potentially large attributes?

3. **Downstream Usage**: Are bandpass solutions used in stages 15-48, or only for rendering in stage 14?

4. **Callibrary Pattern**: Is the pattern of storing solutions both in result AND in callibrary intentional or an implementation artifact?

5. **Storage Strategy**: Would you prefer:
   - Option A: Mark as transient (small pickle, requires MS/callibrary access)
   - Option B: External CASA table (space-efficient, adds file I/O)
   - Option C: Compression/summary (moderate space, keeps in pickle)

---

## Appendix: Stage 14 Comparison with Stage 4

### Stage 4 (hif_rawflagchans) - Strategy A Success
- **Size**: 1,022 MB
- **Reduction**: 99.999% → 9.5 KB
- **Key Data**: Numpy view arrays (100+ MB each)
- **Result Object**: Uses `FlaggableViewResults` base class
- **Optimization**: Mark `view` transient

### Stage 14 (hifa_bandpass) - Different Pattern
- **Size**: 55 MB
- **Reduction**: 0% with Strategy A
- **Key Data**: Calibration solutions (not view arrays)
- **Result Object**: `BandpassResults` (does not inherit FlaggableViewResults)
- **Optimization**: Unknown (requires investigation)

**Conclusion**: Different task types have different storage patterns. Strategy A (view arrays) doesn't apply to calibration-heavy tasks like bandpass. Need custom optimization for each task type.
