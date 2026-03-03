# Pipeline Result Pickle Optimization Architecture

## Overview

Pipeline result serialization optimization follows a task-type-specific architecture where different optimization strategies are applied based on the underlying data patterns of each task.

---

## Optimization Strategies by Task Type

### 1. View Array Tasks (Flagging Operations)

**Affected Stages**: 3, 4, 6, 7, 10, 11, 15, 32  
**Implementation**: Strategy A (Transient Fields)  
**Production Status**: ✅ VALIDATED (92.3% reduction on large datasets)

#### Characteristics
- Stages that perform flagging operations on measurement sets
- Results contain large numpy view arrays derived from MS data
- View arrays are used for weblog generation and QA checking
- Arrays can be recreated from MS + cached statistics

#### Optimization: Mark `view` as Transient

```python
class FlaggableViewResults(Results):
    def __init__(self):
        self._transient_fields = {'view'}
```

**Result**: View arrays (100+ MB each) excluded from pickle  
**Savings**: 93-99% on individual stage pickles  
**Validation**: Views recreated on demand during weblog rendering (defensive guards)

#### Examples
| Stage | Task | Before | After | Reduction |
|-------|------|--------|-------|-----------|
| 4 | hif_rawflagchans | 1,022 MB | 9.5 KB | 99.999% |
| 7 | hifa_tsyscal | 69 MB | 7.0 KB | 99.99% |
| 10 | hifa_tsysflag | 57 MB | 3.0 MB | 94.7% |

#### Implementation Checklist
- [x] Add `_transient_fields = {'view'}` to base class
- [x] Extend to tsysflag-specific attributes (`plots`, `components`)
- [x] Harden renderers with defensive `getattr(result, 'attr', default)`
- [x] Recursive fix for nested `ResultsList`
- [x] Validation on small + large datasets

---

### 2. Calibration-Heavy Tasks (Unknown Pattern)

**Affected Stages**: 14 (hifa_bandpass)  
**Current Impact**: 55 MB, 0% reduction  
**Investigation Status**: 🔍 IN PROGRESS

#### Characteristics
- Bandpass calibration task
- Results container has attributes like `low_channel_solutions`, `solint_adjustments`
- Size indicates stored calibration solution data (not view arrays)
- **Unknown**: Are solutions duplicates of callibrary entries? Needed downstream?

#### Investigation Required
1. Profile attribute sizes to identify storage breakdown
2. Check if solutions are duplicates (already in callibrary)
3. Verify downstream stage usage
4. Determine if reconstruction is possible

#### Expected Optimization (Once Investigated)

**Hypothesis A**: Solutions are callibrary duplicates
```python
class BandpassResults(Results):
    def __init__(self):
        self._transient_fields = {
            'low_channel_solutions',  # If duplicate
            # ... other calibration data
        }
```
Savings: 20-40 MB (36-73% of Stage 14)

**Hypothesis B**: Solutions must be preserved (external storage)
```python
# Store as CASA table, keep reference in pickle
# Effort: Higher
# Savings: 40-50 MB (73-91% of Stage 14)
```

#### Next Steps
1. Run `deep_profile_result.py result-stage14.pickle --max-depth 4`
2. Analyze attribute breakdown
3. Compare with callibrary contents
4. Decide optimization strategy

---

### 3. Metadata-Heavy Tasks (Unknown Pattern)

**Affected Stages**: 45 (hif_makeimlist), possibly others  
**Current Impact**: 15 MB, 0% reduction  
**Investigation Status**: 🔍 PLANNED

#### Characteristics
- Imaging metadata task
- Result contains target lists, image parameters, metadata
- **Unknown**: Why 15 MB for metadata? Typical list should be <1 MB

#### Investigation Required
1. Understand what "metadata" actually contains
2. Check for redundancy or inefficient storage
3. Determine if data is needed downstream
4. Identify compression or pruning opportunities

#### Expected Optimization (Once Investigated)

**Hypothesis A**: Metadata can be regenerated from inputs
```python
# Store reference only, regenerate on load
# Savings: 10-15 MB (67-100% of Stage 45)
```

**Hypothesis B**: Duplication exists in stored data
```python
# Prune redundant fields
# Savings: 5-10 MB (33-67% of Stage 45)
```

**Hypothesis C**: Compression useful
```python
# Compress large lists with numpy compression
# Savings: 5-8 MB (33-53% of Stage 45)
```

#### Next Steps
1. Run `deep_profile_result.py result-stage45.pickle --max-depth 4`
2. Analyze nested structure of `results` attribute
3. Compare with input specifications
4. Prototype optimization and validate

---

### 4. Manual Flagging Tasks (Unknown Pattern)

**Affected Stages**: 2 (hifa_flagdata)  
**Current Impact**: 11 MB, 0% reduction  
**Investigation Status**: 🔍 PLANNED

#### Characteristics
- Manual flag entry task (different from auto-flagging Stages 3, 4, 6, etc.)
- **Unknown**: Why different pattern? Not using `FlaggableViewResults`
- **Unknown**: Why Strategy A doesn't help?

#### Investigation Required
1. Understand why Stage 2 differs from Stage 4 (auto-flagging)
2. Profile storage breakdown
3. Check if view arrays present but not marked transient
4. Determine if refactoring to `FlaggableViewResults` possible

#### Possible Issues
1. **Pattern Issue**: Stage 2 may use different result class not derived from `FlaggableViewResults`
2. **Data Type Issue**: Flag data stored as commands/rules instead of arrays
3. **Hybrid Issue**: Mix of both approaches (arrays + commands)

#### Expected Optimization (Once Investigated)

**Hypothesis A**: Strategy A applies but missed (extend base class)
```python
# Add Stage 2 to same transient fields pattern
# Savings: 5-10 MB (45-91% of Stage 2)
```

**Hypothesis B**: Different data type (refactor needed)
```python
# Convert to different storage (commands, external file)
# Savings: 8-11 MB (73-100% of Stage 2)
```

#### Next Steps
1. Compare Stage 2 result type with Stage 4
2. Profile Stage 2 to understand storage
3. Trace why Strategy A not applied
4. Implement appropriate fix

---

## Total Optimization Potential

### Current State (After Strategy A)
```
Total result pickles: 1,239 MB (large dataset)

Optimized (Strategy A applied):
  - Flagging tasks: 158 MB → 23 MB (85% reduction)
  
Not optimized (need investigation):
  - Calibration/Metadata/Manual: 91 MB → ??? MB
  
Total: 1,239 MB → 114 MB (baseline + unknowns)
```

### Projected After Full Optimization

**Conservative Estimate** (30% reduction on unknowns):
```
1,239 MB → (23 MB + 64 MB) = 87 MB (93% total reduction)
```

**Optimistic Estimate** (75% reduction on unknowns):
```
1,239 MB → (23 MB + 23 MB) = 46 MB (96% total reduction)
```

**Aggressive Estimate** (90% reduction on unknowns):
```
1,239 MB → (23 MB + 9 MB) = 32 MB (97% total reduction)
```

---

## Implementation Timeline

### Completed ✅
- Strategy A for view arrays (all flagging tasks)
- Recursive `ResultsList.slim_for_pickle()` fix
- Renderer hardening with defensive guards
- Production validation on small + large datasets

### In Progress 🔍
- Stage 14 (hifa_bandpass) profiling
- TBD: Stage 2, 45 profiling

### Planned 📋

**Week 1**:
- Complete profiling of all three stages (2, 14, 45)
- Choose optimization strategy for each stage
- Implement Stage 45 (smallest, fastest iteration)

**Week 2**:
- Validate Stage 45 optimization
- Implement Stage 14 optimization  
- Implement Stage 2 optimization

**Week 3**:
- Validate all three stages
- Create unified commit
- Update PR with full architecture + results
- Prepare for merge

---

## Optimization Decision Framework

### For Each Unknown Task Type:

1. **Profile** (1-2 hours)
   - Use `deep_profile_result.py` to identify largest attributes
   - Understand attribute types and purposes
   - Estimate reconstruction/regeneration feasibility

2. **Classify** (30 min)
   - Which strategy applies? (A, B, C, D below)
   - What's the risk level?
   - What's the expected savings?

3. **Implement** (1-4 hours)
   - Apply chosen strategy
   - Add defensive guards if needed
   - Test on small dataset

4. **Validate** (2-4 hours)
   - Run full pipeline
   - Verify products identical to baseline
   - Measure actual savings
   - Test weblog rendering

### Four Optimization Strategies

| Strategy | Approach | Effort | Risk | Best For |
|----------|----------|--------|------|----------|
| **A** | Mark as transient | Low | Low | View arrays, duplicates |
| **B** | External storage | Medium | Medium | Large calibration tables |
| **C** | Summary-only | Medium | Medium | Metadata, optional data |
| **D** | Compression | Low | Low | Large uncompressible data |

---

## File Structure for Optimization Work

```
docs/source/context_serialization/
├── STRATEGY_A_IMPLEMENTATION.md          # ✅ Complete
├── STAGE14_BANDPASS_OPTIMIZATION.md      # 🔍 Investigation guide
├── OPTIMIZATION_ROADMAP_STAGES_2_14_45.md   # 📋 This document
├── LARGER_RESULT_INVESTIGATION.md        # 🔍 Original findings
└── RECOMMENDATIONS_LARGE_RESULTS.md      # 📋 Initial roadmap

tools/
├── deep_profile_result.py                # 🆕 Deep-dive analysis tool
├── estimate_results_slimming.py          # ✅ Post-hoc measurement
├── profile_result_objects.py             # ✅ Attribute size analysis
└── ... (other tools)
```

---

## Known Limitations & Edge Cases

### 1. Backward Compatibility
- New pickles may not load in older pipeline versions
- **Mitigation**: Document version requirement (2025.1+)
- **Status**: Need verification testing

### 2. Weblog Regeneration
- Cannot regenerate weblogs from pickles alone if views missing
- **Mitigation**: Weblogs render during initial execution
- **Impact**: Post-hoc weblog regeneration requires MS access

### 3. Developer Debugging
- Post-pickle inspection missing transient fields
- **Mitigation**: Fields available during live execution
- **Impact**: Minor (debugging uses live execution)

### 4. Task-Specific Optimization
- Different task types have different storage patterns
- **Mitigation**: Custom investigation & strategy per task type
- **Learning**: One size does NOT fit all

---

## Success Metrics

### For Current Implementation (Strategy A)
- [x] 92.3% reduction on large datasets
- [x] 43.9% reduction on small datasets
- [x] All 48 stages complete successfully
- [x] Zero functional regressions
- [x] Weblogs render correctly

### For Full Implementation (A+B+C)
- [ ] 95%+ total reduction (1,239 MB → <62 MB)
- [ ] All 48 stages complete successfully
- [ ] Zero functional regressions
- [ ] Weblogs render correctly for all stages
- [ ] Execution time within ±5% of baseline
- [ ] Backward compatibility verified

---

## Questions for Optimization Team

1. **Priority Order**: Should we focus on Stage 14 (largest), 45 (smallest/fastest), or 2 (mystery)?

2. **Investigation Time**: How much time can be allocated to profiling before choosing optimization strategy?

3. **Risk Tolerance**: Should we maximize savings (aggressive strategy) or minimize risk (conservative)?

4. **External Storage**: Is external CASA table storage acceptable for calibration data, or must everything stay in pickle?

5. **Compression**: Is acceptable to use numpy compression? Any Python version requirements?

---

## Appendix: Task Type Reference

### View-Array Tasks (Strategy A ✅)
- hif_rawflagchans (Stage 4): View arrays of flags + statistics
- hifa_tsyscal (Stage 7): View arrays of Tsys statistics
- hifa_tsysflag (Stage 10): View arrays of flag summaries
- hifa_wvrgcalflag (Stage 11): View arrays of WVR flag statistics
- [others follow same pattern]

### Calibration-Heavy Tasks (Under Investigation 🔍)
- hifa_bandpass (Stage 14): Bandpass calibration solutions

### Metadata-Heavy Tasks (Under Investigation 🔍)
- hif_makeimlist (Stage 45): Imaging target metadata and lists

### Manual Flagging Tasks (Under Investigation 🔍)
- hifa_flagdata (Stage 2): Manual flag entry and rule specification

---

## Conclusion

The pipeline result optimization is a **multi-phase architecture** where each task type requires custom analysis and optimization. Strategy A (view arrays) achieved excellent results (92.3% reduction) for flagging tasks. The next phase focuses on the three remaining task types where different storage patterns require different optimization strategies.

**Key Insight**: Successful pipeline optimization requires understanding task-specific data patterns, not one-size-fits-all solutions.
