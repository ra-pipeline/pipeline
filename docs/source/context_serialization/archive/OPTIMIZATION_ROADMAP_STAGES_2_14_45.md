# Stages 2, 14, 45 Optimization Investigation Plan

## Executive Summary

Strategy A achieved **92.3% reduction** on large datasets by targeting numpy view arrays in flagging tasks. However, **91 MB remains** in non-flagging tasks with entirely different storage patterns:

| Stage | Task | Current | Pattern | Challenge |
|-------|------|---------|---------|-----------|
| **2** | hifa_flagdata | 11 MB | Manual flagging (different from auto-flagging) | Unknown storage pattern |
| **14** | hifa_bandpass | 55 MB | Calibration solutions | Need identification & validation |
| **45** | hif_makeimlist | 15 MB | Imaging metadata | Need structure analysis |

**Opportunity**: 60-80 MB additional reduction (if successful)  
**Combined Impact**: 1,239 MB → 15-35 MB (**~98-99% total reduction**)

---

## Stage 2: hifa_flagdata (Manual Flagging)

### Current Status
- **Size**: 11 MB (unchanged by Strategy A)
- **Type**: Not a flagging task in traditional sense
- **Problem**: Does not use `FlaggableViewResults` base class

### Investigation Questions

1. **Storage Pattern**: 
   - What does hifa_flagdata result object contain?
   - Is it also storing view arrays (like hif_rawflagchans)?
   - Or does it store flag commands/rules differently?

2. **Comparison with Auto-Flagging Tasks**:
   - How does hifa_flagdata differ from hif_rawflagchans (Stage 4, 99.999% reduction)?
   - Why doesn't Strategy A work for Stage 2?

3. **Duplication**:
   - Are flag commands/rules duplicated between result and other storage?
   - Is reconstruction possible from cached data?

### Profiling Plan

```bash
# 1. Analyze Stage 2 result structure
python tools/deep_profile_result.py result-stage2.pickle --max-depth 3

# 2. Compare with Stage 4 (auto-flagging that benefited from Strategy A)
python tools/deep_profile_result.py result-stage4.pickle --max-depth 3

# 3. Identify largest attributes
# Expected output will show what's consuming 11 MB
```

### Potential Optimization Strategies

**A. Mark as Transient (if they're view/duplicate data)**
- Effort: Low (1-2 hours)
- Risk: Low
- Savings: 5-10 MB

**B. Refactor to FlaggableViewResults (if structural issue)**
- Effort: Medium (4-8 hours)
- Risk: Medium
- Savings: 8-11 MB

**C. External Storage (if commands/rules are large)**
- Effort: Medium-High
- Risk: Medium
- Savings: 10-11 MB

---

## Stage 14: hifa_bandpass (Calibration Solutions)

### Current Status
- **Size**: 55 MB (largest optimization target)
- **Type**: Calibration task
- **Pattern**: `BandpassResults` with calibration solutions
- **Attributes**: `low_channel_solutions`, `solint_adjustments`, `phaseup_caltable_for_phase_rms`, etc.

### Key Finding

User-provided investigation output shows:
```
ResultsList with 1 BandpassResults item
Attributes: low_channel_solutions, solint_adjustments, 
            phaseup_caltable_for_phase_rms, timestamps, pool, preceding, qa, ...
```

### Critical Unknowns

1. **Data Duplication**:
   - Are `low_channel_solutions` copies of bandpass caltable already in callibrary?
   - Is there redundant storage?

2. **Attribute Sizes**:
   - Which attributes actually consume the 55 MB?
   - Is it one large attribute or many small ones?

3. **Essentiality**:
   - Are these solutions needed downstream (stages 15-48)?
   - Or only used for Stage 14 weblog rendering?

4. **Reconstruction**:
   - Can bandpass solutions be regenerated from callibrary?
   - What's the cost (time, resources)?

### Profiling Plan

```bash
# Deep analysis of Stage 14
python tools/deep_profile_result.py result-stage14.pickle --max-depth 4

# Output will show:
# - Which attributes are largest
# - If any are >1-2 MB individually
# - Nested structure of complex attributes
# - Possible duplication candidates
```

### Potential Optimization Strategies

**A. Mark Duplicate Solutions as Transient** (if they duplicate callibrary)
- Effort: Low-Medium (2-4 hours)
- Risk: Low (straightforward, like Strategy A)
- Savings: 20-40 MB
- Validation: Verify solutions available in callibrary

**B. External CASA Table Storage** (if solutions must be preserved)
- Effort: Medium-High (6-12 hours)
- Risk: Medium (file I/O added)
- Savings: 40-50 MB
- Approach: Store as bandpass.cal CASA table, keep reference in pickle

**C. Compress Complex Attributes** (alternative if solutions modified)
- Effort: Low-Medium (2-4 hours)
- Risk: Low
- Savings: 15-25 MB
- Approach: Use numpy compression, lazy-load on access

**D. Summary-Only Storage** (if full solutions not needed)
- Effort: Medium (4-6 hours)
- Risk: Medium (validate downstream usage)
- Savings: 40-50 MB
- Approach: Store statistics instead of full solutions

---

## Stage 45: hif_makeimlist (Imaging Metadata)

### Current Status
- **Size**: 15 MB (smallest of three, but still addressable)
- **Type**: Imaging task
- **Result Object**: `MakeImagesResult` with imaging target metadata
- **Pattern**: Similar to Stage 14 - calibration/task-specific data not view arrays

### Investigation Questions

1. **Content Type**:
   - What imaging metadata is stored?
   - Source lists? Target descriptions? Image parameters?

2. **Verbosity**:
   - Why is 15 MB needed for metadata?
   - Typical imaging list should be small (<1 MB)

3. **Reconstruction**:
   - Can metadata be regenerated from input specifications?
   - Is it used downstream or only for reference?

### Profiling Plan

```bash
# Deep analysis of Stage 45
python tools/deep_profile_result.py result-stage45.pickle --max-depth 4

# Expected findings:
# - Identify the 'results' attribute structure
# - Understand why imaging metadata so large
# - Check for duplicated image parameter information
```

### Potential Optimization Strategies

**A. Reference-Only Storage** (if data can be regenerated)
- Effort: Low-Medium (2-4 hours)
- Risk: Low
- Savings: 10-15 MB
- Approach: Store references instead of full metadata

**B. Prune Redundant Metadata** (if duplication exists)
- Effort: Low (1-2 hours)
- Risk: Low
- Savings: 5-10 MB
- Approach: Remove duplicate/derivable information

**C. Compress Large Lists** (if source lists are large)
- Effort: Low (1-2 hours)
- Risk: Low
- Savings: 5-8 MB
- Approach: Use numpy compression, lazy-load

---

## Phased Implementation Plan

### Phase 1: Profiling (2 hours)
1. Run `deep_profile_result.py` on all three stages
2. Identify largest attributes in each
3. Create visualization of storage breakdown
4. Determine which optimization strategy is most appropriate

### Phase 2: Single-Stage Pilot (4 hours)
1. Choose easiest stage (likely Stage 45 - smallest)
2. Implement proposed optimization
3. Run full pipeline validation
4. Measure actual savings
5. Document lessons learned

### Phase 3: Apply to Other Stages (6-8 hours)
1. Apply optimization strategy to remaining stages
2. Handle stage-specific requirements
3. Validate each individually
4. Create comprehensive documentation

### Phase 4: Integration & Merge (2 hours)
1. Create single commit with all optimization improvements
2. Update PR with results (60-80 MB additional savings)
3. Merge to main branch
4. Update documentation with complete optimization roadmap

**Total Effort**: 14-16 hours  
**Expected Outcome**: 1,239 MB → 15-35 MB (**~98-99% total reduction**)

---

## Success Criteria

### Success Metrics
- [ ] Stage 2: Identified storage pattern and optimization approach
- [ ] Stage 14: At least 20 MB reduction (36% of 55 MB)
- [ ] Stage 45: At least 5 MB reduction (33% of 15 MB)
- [ ] Zero functional regressions (all products identical)
- [ ] All weblogs render correctly
- [ ] Backward compatibility confirmed

### Validation Requirements
- Run full hifa_calimage pipeline on small dataset
- Run on large multi-EB dataset (optional, time-permitting)
- Compare products with baseline (ensure identical)
- Measure execution time (ensure no significant slowdown)
- Verify weblog rendering works with all transient approaches

---

## Decision Tree

### Stage 2: hifa_flagdata
```
Size = 11 MB (requires investigation)

IF (large attributes are view/duplicate data):
    → Strategy A extended: Mark as transient
    → Effort: Low
    → Savings: 5-10 MB
ELSE IF (large attributes are commands/rules):
    → Investigate refactoring to FlaggableViewResults
    → Effort: Medium
    → Savings: 8-11 MB
ELSE:
    → Profile first to understand storage pattern
    → Effort: Low (profiling)
```

### Stage 14: hifa_bandpass
```
Size = 55 MB (calibration solutions)

IF (solutions are duplicates in callibrary):
    → Strategy A extended: Mark as transient
    → Effort: Low-Medium
    → Savings: 20-40 MB ✅ RECOMMENDED
ELSE IF (solutions must be preserved):
    → External CASA table storage
    → Effort: Medium-High
    → Savings: 40-50 MB
ELSE IF (only summary needed):
    → Summary-only storage
    → Effort: Medium
    → Savings: 40-50 MB
```

### Stage 45: hif_makeimlist
```
Size = 15 MB (imaging metadata)

IF (metadata can be regenerated):
    → Reference-only storage
    → Effort: Low-Medium
    → Savings: 10-15 MB ✅ RECOMMENDED
ELSE IF (duplication exists):
    → Prune redundant fields
    → Effort: Low
    → Savings: 5-10 MB
ELSE:
    → Compress large lists
    → Effort: Low
    → Savings: 5-8 MB
```

---

## Open Questions

1. **Bandpass Calibration Storage**: Are solutions duplicated in both result AND callibrary? 
   - If yes: Mark as transient immediately
   - If no: Need validation that solutions can be reconstructed

2. **hifa_flagdata Pattern**: Why doesn't Strategy A help Stage 2? What's different from Stage 4?
   - Need profiling to answer

3. **Imaging Metadata**: Why is Stage 45 metadata so verbose (15 MB)?
   - Typical imaging target list should be <1 MB

4. **Downstream Dependencies**: Are optimization targets used in downstream stages or only for reference?
   - Critical for determining if marking transient is safe

5. **Weblog Rendering**: Do renderers for stages 2, 14, 45 require access to current attributes?
   - May need defensive guards like flagging tasks

---

## Next Steps

1. **User Confirmation**: Should we proceed with detailed profiling of all three stages?
2. **Tool Verification**: Confirm `deep_profile_result.py` works as intended?
3. **Timeline**: When would you like results? (1-2 days for profiling, 1 week for full implementation)
4. **Scope**: Focus on one stage first (recommend Stage 45 as pilot) or tackle all three in parallel?

---

## Appendix: Comparison with Strategy A

### Strategy A Success Factors
1. **Clear Target**: Numpy view arrays in flagging results
2. **Easy Detection**: View attributes obviously present and named
3. **Safe to Mark Transient**: Views can be recreated from MS + statistics
4. **Weblog Compatible**: Only used during rendering, not downstream

### Why Strategy A Failed for Stages 2, 14, 45
1. **Different Storage**: Not view arrays, but calibration/metadata objects
2. **Unclear Ownership**: Duplication unclear (is data original or duplicate?)
3. **Downstream Dependency**: Unknown if data needed beyond initial rendering
4. **Complex Validation**: Each stage has unique requirements

### Lessons Learned
- **One-size-fits-all** optimization doesn't work for diverse pipeline tasks
- **Root cause analysis** required for each task type
- **Profiling essential** before choosing optimization strategy
- **Validation critical** when marking data transient

This is why Stage 2, 14, 45 require **custom investigation**, not blanket Strategy A application.
