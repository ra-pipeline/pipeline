# Optimization Work Archive

## Purpose

This document archives the incremental pickle optimization work (Strategy A and planned extensions) that was completed but ultimately superseded by returning to the original modernization strategy.

---

## What Happened

### Initial Goal (Correct)
The investigation started with the right goal: **modernize the pipeline context storage system** by replacing pickle-based serialization with structured formats (JSON/YAML) as documented in [CONTEXT_STORAGE_INVESTIGATION.md](CONTEXT_STORAGE_INVESTIGATION.md).

### Detour: Incremental Pickle Optimization
During Phase 4 investigation, we discovered large result pickles and pivoted to an incremental optimization approach:

- **Phase 4**: Attempted to slim plot objects (0% improvement - plots were tiny)
- **Strategy A**: Successfully marked numpy view arrays as transient (92.3% reduction on flagging tasks)
- **Planned Phase 2**: Investigating stages 2, 14, 45 for additional optimizations

### The Problem
Strategy A worked beautifully for flagging tasks (99.999% reduction on Stage 4), but investigation revealed that:

1. **Different task types have entirely different storage patterns**
   - Flagging tasks: View arrays (Strategy A works)
   - Calibration tasks (Stage 14): Solution tables (needs custom investigation)
   - Imaging tasks (Stage 45): Metadata (needs custom investigation)
   - Manual flagging (Stage 2): Unknown pattern (needs custom investigation)

2. **Each stage requires custom optimization work**
   - 2-4 hours profiling per stage
   - 2-4 hours implementation per stage
   - 2-3 hours validation per stage
   - **Total: 14-24 hours for just three stages**

3. **This never ends**
   - 48 stages total
   - Each with potentially different patterns
   - Diminishing returns as you optimize smaller pickles

### The Realization
We were **optimizing the wrong thing**. The original goal was to **modernize** the context system, not to micro-optimize every task's pickle format.

**Incremental optimization** = endless task-specific work  
**Modernization** = structural improvement that benefits all tasks

---

## What Was Completed (Strategy A)

### Implementation ✅
- Added `_transient_fields` mechanism to Results base class
- **Critical fix**: Recursive `ResultsList.slim_for_pickle()` override
- Marked `view` transient in `FlaggableViewResults` base class (7 tasks benefit via inheritance)
- Extended to tsysflag-specific attributes (`plots`, `components`)
- Hardened 6 renderers with defensive `getattr()` guards

### Validation ✅
- **Small dataset**: 43.9% reduction (7.96 MB → 4.47 MB)
- **Large dataset**: 92.3% reduction (1.24 GB → 94.8 MB)
- **Stage 4** (hif_rawflagchans): 99.999% reduction (1,022 MB → 9.5 KB)
- **Stage 7** (hifa_tsyscal): 99.99% reduction (69 MB → 7.0 KB)
- All 48 stages complete successfully
- Zero functional regressions
- Weblogs render correctly

### Impact ✅
- **Production validated**: Full pipeline runs on large multi-EB datasets
- **Measurable savings**: 1.1 GB saved on large dataset
- **Backward compatible**: Old pickles load correctly (forward compatibility TBD)

**Recommendation**: **Keep Strategy A** - it's a solid improvement for flagging tasks with minimal maintenance burden once in production.

---

## What Was Planned (But Not Implemented)

### Phase 2 Extensions ❌
Investigation documents prepared for:

1. **Stage 14** (hifa_bandpass, 55 MB)
   - Calibration solution storage analysis
   - Determination if solutions duplicate callibrary data
   - Custom optimization strategy selection

2. **Stage 45** (hif_makeimlist, 15 MB)
   - Imaging metadata verbosity analysis
   - Pruning or compression opportunities

3. **Stage 2** (hifa_flagdata, 11 MB)
   - Pattern analysis (why different from auto-flagging?)
   - Appropriate optimization strategy

### Estimated Effort ❌
- 14-24 hours for three stages
- Unknown effort for remaining 45 stages that might have large pickles
- Ongoing maintenance as new tasks added to pipeline

**Recommendation**: **Archive these plans** - they represent good investigative work but are not aligned with modernization goal.

---

## Archived Files

### Phase 2 Planning (Archived February 24, 2026)

**Root directory:**
- `NEXT_PHASE_QUICK_START.md` - Hands-on guide for continuing optimization
- `PHASE_2_STATUS_REPORT.md` - Status report for Phase 2 work

**Documentation directory** (`docs/source/context_serialization/archive/`):
- `STAGE14_BANDPASS_OPTIMIZATION.md` - Stage 14 investigation plan
- `OPTIMIZATION_ROADMAP_STAGES_2_14_45.md` - Comprehensive roadmap for three stages
- `OPTIMIZATION_ARCHITECTURE.md` - Strategic framework for task-specific optimization
- `NEXT_PHASE_PREPARATION_SUMMARY.md` - Overview of Phase 2 preparation

### Pickle Optimization Docs (Archived February 25, 2026)

**Documentation directory** (`docs/source/context_serialization/archive/`):
- `RECOMMENDATIONS_LARGE_RESULTS.md` - Large pickle investigation (led to Strategy A)
- `LARGE_RESULT_INVESTIGATION.md` - Specific pickle bloat analysis
- `PICKLING_PROFILING.md` - Pickle performance profiling guide
- `PHASE4_RESULTS.md` - Phase 4 results slimming (superseded by Strategy A)

**Tools directory** (`tools/archive/`):
- `estimate_results_slimming.py` - Phase 4 slimming estimation tool
- `drill_imaging_products.py` - Imaging product size breakdown tool
- `profile_pickling.py` - Pickling performance profiler

### Documentation Consolidation (February 25, 2026)

**Consolidated into single README.md** (`docs/source/context_serialization/archive/`):
- `README_OLD.md` (formerly README.md) - Navigation/quick start
- `README_INVESTIGATION_OLD.md` (formerly README_INVESTIGATION.md) - Master overview
- `INDEX_OLD.md` (formerly INDEX.md) - Complete navigation guide

### Current Archive Status

| File | Status | Location | Reason |
|------|--------|----------|--------|
| STRATEGY_A_IMPLEMENTATION.md | ✅ Keep | Active docs | Documents completed, production work |
| STAGE14_BANDPASS_OPTIMIZATION.md | 📦 Archived | `archive/` | Phase 2 work, not pursued |
| OPTIMIZATION_ROADMAP_STAGES_2_14_45.md | 📦 Archived | `archive/` | Phase 2 work, not pursued |
| OPTIMIZATION_ARCHITECTURE.md | 📦 Archived | `archive/` | Task-specific optimization framework, superseded |
| NEXT_PHASE_PREPARATION_SUMMARY.md | 📦 Archived | `archive/` | Phase 2 preparation, not pursued |
| RECOMMENDATIONS_LARGE_RESULTS.md | 📦 Archived | `archive/` | Valuable investigation, optimization-focused |
| LARGE_RESULT_INVESTIGATION.md | 📦 Archived | `archive/` | Pickle bloat investigation |
| PICKLING_PROFILING.md | 📦 Archived | `archive/` | Pickle profiling methodology |
| PHASE4_RESULTS.md | 📦 Archived | `archive/` | Results slimming, superseded by Strategy A |
| estimate_results_slimming.py | 📦 Archived | `tools/archive/` | Phase 4 estimation tool |
| drill_imaging_products.py | 📦 Archived | `tools/archive/` | Product size analysis |
| profile_pickling.py | 📦 Archived | `tools/archive/` | Pickle profiler |
| README_OLD.md | 📦 Archived | `archive/` | Replaced by consolidated README.md |
| README_INVESTIGATION_OLD.md | 📦 Archived | `archive/` | Replaced by consolidated README.md |
| INDEX_OLD.md | 📦 Archived | `archive/` | Replaced by consolidated README.md |

---

## Why Archive (Not Delete)?

### Value of Archived Work

1. **Investigation Methodology**
   - Profiling approach is sound
   - Decision frameworks are useful
   - Lessons learned about task-specific optimization

2. **Reference Material**
   - If future optimization needed for specific task, these docs provide framework
   - Shows what was tried and why it was superseded
   - Demonstrates trade-offs between optimization and modernization

3. **Negative Results Are Valuable**
   - Phase 4: "Don't optimize plot objects, they're tiny"
   - Phase 2 investigation: "Task-specific optimization doesn't scale"
   - Both prevent future wasteful efforts

---

## Lessons Learned

### What Strategy A Taught Us

1. **Inheritance is powerful**: Marking `view` transient in base class benefits 7 derived tasks automatically
2. **Recursive containers are tricky**: `ResultsList` needed explicit override to propagate slimming
3. **Renderers must be defensive**: Can't assume transient fields exist post-pickle
4. **View arrays dominate flagging task storage**: 99.999% reduction proves views are the culprit
5. **Scaling behavior**: Small datasets show modest gains (43.9%), large datasets show dramatic gains (92.3%)

### What Didn't Scale

1. **Task-specific optimization**: Each task type has different storage patterns
2. **Profiling overhead**: 2-4 hours per stage to understand storage
3. **Implementation complexity**: Each task needs custom solution
4. **Maintenance burden**: New tasks require new investigations
5. **Diminishing returns**: Smaller pickles = less benefit per hour invested

### The Core Insight

**Optimization Question**: "How can I make this pickle smaller?"  
**Modernization Question**: "Do I need the pickle at all?"

The modernization approach (JSON/YAML metadata, lazy loading) provides:
- Human-readable context inspection
- Version-independent storage
- Faster access to metadata (no unpickling)
- Better integration with external tools
- Structural improvement that benefits all tasks

---

## Return to Modernization Strategy

### The Original Plan (CONTEXT_STORAGE_INVESTIGATION.md)

**Layer 1**: Structured metadata (JSON/YAML) ✅ Partially complete
- Task execution summary
- Input parameters, QA scores
- Simple statistics
- **Already implemented**: `ContextDeltaMetadata`, per-stage YAML exports

**Layer 2**: Task-specific results (YAML) ⚠️ Needs expansion
- Structured export of key results
- Calibration table metadata (not caltables)
- Image statistics
- Processing flags and warnings

**Layer 3**: Rich objects (Pickle as fallback) ⚠️ Needs strategy
- Keep pickle for complex numpy arrays
- Domain objects needed for continuation
- But: Load only when needed (lazy loading)

### What This Enables

1. **Query metadata without unpickling**
   ```bash
   # Find all stages that completed successfully
   grep "status: completed" saved_state/context-stage*-metadata.yaml
   
   # Find stages with QA warnings
   grep -l "warnings:" saved_state/context-stage*-metadata.yaml
   ```

2. **Weblog generation from metadata alone**
   - Load YAML metadata (fast, 1-10 KB per stage)
   - Only unpickle if complex object needed
   - 90% of weblog content from metadata, 10% from pickles

3. **External tool integration**
   - QA pipeline can parse YAML without Python
   - Archive system can index metadata
   - Debugging tools can inspect without pipeline code

4. **Version independence**
   - YAML survives Python version changes
   - Pickle backward compatibility issues become rare
   - Long-term archival becomes tractable

---

## Next Steps (Modernization Focus)

### Immediate (This Week)

1. ✅ **Archive optimization documents** (this document)
2. ✅ **Consolidate tools** (integrate `deep_profile_result.py` into `profile_result_objects.py`)
3. ⏳ **Update references** in documentation to reflect tool consolidation
4. ⏳ **Review CONTEXT_STORAGE_INVESTIGATION.md** for implementation priorities

### Short-term (Next 2 Weeks)

1. **Expand metadata export** (Layer 1 completion)
   - Add more task-specific fields to metadata
   - Ensure all stages export complete metadata
   - Validate metadata coverage for weblog rendering

2. **Implement lazy loading** (Layer 3 strategy)
   - Weblog renderer loads metadata first
   - Unpickles results only when needed
   - Measure memory reduction and performance impact

3. **Create migration guide**
   - How to access results using new APIs
   - Backward compatibility strategy
   - Deprecation timeline for direct pickle access

### Medium-term (Next Month)

1. **Layer 2 implementation** (Structured task results)
   - YAML export for calibration tasks
   - YAML export for imaging tasks
   - Unified serialization framework

2. **Weblog optimization**
   - Prefer metadata over pickles
   - Profile memory usage
   - Validate performance on large datasets

3. **Documentation and training**
   - Update developer guides
   - Create examples
   - Migration tooling for existing code

---

## Commit Strategy

### What to Commit

**Keep in Git History:**
- Strategy A implementation (production code)
- Strategy A documentation (STRATEGY_A_IMPLEMENTATION.md)
- Investigation tooling (profile_result_objects.py with --deep-dive)
- Investigation methodology (LARGE_RESULT_INVESTIGATION.md)

**Archive (document existence, remove from main docs):**
- This archive document (OPTIMIZATION_WORK_ARCHIVE.md)
- Phase 2 planning documents (move to archive/ subdirectory)

**Delete:**
- Root-level Phase 2 status files (NEXT_PHASE_QUICK_START.md, PHASE_2_STATUS_REPORT.md)
- Redundant tools (deep_profile_result.py already removed)

### Recommended Commit Message

```
Pivot to modernization strategy: Archive incremental pickle optimization work

Context:
- Strategy A (transient fields) successfully achieved 92.3% reduction on large datasets
- Planned Phase 2 would require 14-24 hours for 3 stages with diminishing returns
- Task-specific optimization doesn't scale to 48-stage pipeline

Decision:
- Keep Strategy A implementation (validated, production-ready, minimal maintenance)
- Archive Phase 2 planning (stages 2, 14, 45 investigation)
- Return to original goal: modernize context storage with JSON/YAML metadata

Changes:
- Consolidated tools: Integrated deep-dive analysis into profile_result_objects.py
- Created OPTIMIZATION_WORK_ARCHIVE.md documenting the pivot
- Removed Phase 2 planning files from root directory
- Updated tool references in documentation

Next Phase:
- Focus on CONTEXT_STORAGE_INVESTIGATION.md implementation strategy
- Expand metadata export (Layer 1)
- Implement lazy loading (Layer 3)
- Enable weblog generation from metadata without full pickle unpickling

Strategy A achievements preserved:
- 92.3% reduction on large datasets (1.24 GB → 94.8 MB)
- Production validated on small + large datasets
- Zero functional regressions
```

---

## Conclusion

Strategy A was successful within its scope (flagging tasks), but the investigation revealed that a modernization approach provides better long-term value than endless task-specific optimization.

**We're not abandoning optimization** - we're choosing **strategic modernization over tactical optimization**.

The original CONTEXT_STORAGE_INVESTIGATION.md document had the right idea: structured metadata + lazy loading. Let's execute that vision.

---

## References

### Active Documents
- [CONTEXT_STORAGE_INVESTIGATION.md](CONTEXT_STORAGE_INVESTIGATION.md) - Original modernization strategy (return here)
- [STRATEGY_A_IMPLEMENTATION.md](STRATEGY_A_IMPLEMENTATION.md) - Completed work (keep)
- [README.md](README.md) - Consolidated navigation guide

### Archived Documents
- Phase 2 planning: See `archive/STAGE14_BANDPASS_OPTIMIZATION.md`, `archive/OPTIMIZATION_ROADMAP_STAGES_2_14_45.md`, etc.
- Pickle optimization: See `archive/RECOMMENDATIONS_LARGE_RESULTS.md`, `archive/LARGE_RESULT_INVESTIGATION.md`, etc.
- Old navigation docs: See `archive/README_OLD.md`, `archive/README_INVESTIGATION_OLD.md`, `archive/INDEX_OLD.md`

### Archived Tools
- Phase 4 tools: See `tools/archive/estimate_results_slimming.py`, `tools/archive/drill_imaging_products.py`
- Pickle profiling: See `tools/archive/profile_pickling.py`
