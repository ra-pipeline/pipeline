# Context Storage Modernization: Implementation Roadmap

## Overview

This document provides a clear roadmap for completing the context storage modernization strategy outlined in [CONTEXT_STORAGE_INVESTIGATION.md](CONTEXT_STORAGE_INVESTIGATION.md). It tracks what's been completed and defines actionable next steps.

**Last Updated**: February 25, 2026

---

## 🎯 Modernization Goals

### Primary Goals
1. **Human-readable context inspection** - Enable grep/search without unpickling
2. **Version independence** - Survive Python/library version changes
3. **Faster metadata access** - 100x improvement for common queries
4. **External tool integration** - JSON/YAML accessible without Python
5. **Reduced storage footprint** - Eliminate redundant data serialization

### Non-Goals
- ❌ Complete pickle elimination (pickle remains for complex objects)
- ❌ Breaking backward compatibility (all changes are additive)
- ❌ Task-by-task pickle optimization (strategy superseded)

---

## 📊 Current Status

### ✅ Completed Work (Phases 1-4)

#### Phase 1: Metadata Extraction ✅
**Status**: Production-ready  
**Implementation**: `pipeline/infrastructure/serializers.py`

- [x] `ResultMetadata` dataclass for key result fields
- [x] YAML/JSON export alongside pickles
- [x] Utilities to load metadata without unpickling
- [x] Zero changes to existing pickle path

**Benefits**: 100x faster metadata access, human-readable format

#### Phase 2: Weblog Caching ✅
**Status**: Production-validated  
**Implementation**: `pipeline/infrastructure/renderer/weblog_metadata.py`

- [x] Task-specific metadata serializers (14+ renderer classes)
- [x] Renderer metadata cached alongside results
- [x] Compatibility layer for existing code
- [x] Weblog renderers load cached metadata first

**Benefits**: 30-36% weblog rendering improvement

#### Phase 3: Parallel Unpickling ✅
**Status**: Production-validated  
**Implementation**: `pipeline/infrastructure/renderer/htmlrenderer.py`

- [x] Adaptive parallel unpickling (size-aware worker scaling)
- [x] Thread-safety fixes for CalFrom flyweight pool
- [x] ResultsProxy path support for tuning
- [x] Validated on production datasets

**Benefits**: 1.2-4.8x unpickling speedup (cold cache)

#### Phase 4: Results Slimming (Strategy A) ✅
**Status**: Production-validated  
**Implementation**: `pipeline/infrastructure/basetask.py`, `FlaggingMixin`

- [x] `Results.slim_for_pickle()` with recursive ResultsList support
- [x] `__transient_fields__` mechanism (9 result classes, 7 tasks)
- [x] Renderer hardening (defensive getattr guards)
- [x] ContextDeltaMetadata for incremental tracking

**Benefits**: 92.3% reduction on large flagging datasets (1.24 GB → 94.8 MB)

---

## 🚀 Remaining Work (3-Layer Strategy)

### Layer 1: Structured Metadata (90% Complete)

**Goal**: All tasks export comprehensive YAML/JSON metadata alongside pickles

**What's Done**:
- ✅ Core framework (`ResultMetadata`, `ContextMetadata`)
- ✅ Automatic export on task completion
- ✅ Renderer metadata export (14+ renderers)
- ✅ Context delta tracking

**What Remains**:

#### 1.1 Expand Task Coverage (Priority: Medium)
**Goal**: Ensure all pipeline tasks export comprehensive metadata across all workflows

**Scope**: All pipeline workflows (ALMA-IF, ALMA-SD, VLA, VLASS, etc.)

**Tasks**:
- [ ] Survey all task types across all workflows (h/, hif/, hifa/, hifv/, hsd/, hsdn/)
- [ ] Audit current metadata coverage for each task family
- [ ] Identify tasks with incomplete metadata export
- [ ] Add missing fields to metadata schemas
- [ ] Validate metadata completeness across workflows

**Estimated Effort**: 2-3 days  
**Success Criteria**: All task types across all workflows export metadata covering inputs, outputs, QA scores, timing

#### 1.2 Metadata Schema Validation (Priority: Low)
**Goal**: Ensure metadata consistency and completeness

**Tasks**:
- [ ] Create JSON schema for metadata validation
- [ ] Add validation to export pipeline
- [ ] Create test suite for metadata schemas
- [ ] Document metadata format for external tools

**Estimated Effort**: 1 day  
**Success Criteria**: Automated validation, schema documentation published

---

### Layer 2: Task-Specific Results (30% Complete)

**Goal**: Export structured task results (YAML) for key information currently only in pickles

**What's Done**:
- ✅ Renderer metadata (plots, display contexts)
- ✅ ContextDeltaMetadata (stage-to-stage changes)
- ⚠️ Basic result metadata (task name, status, timing)

**What Remains**:

#### 2.1 Calibration Task Results (Priority: High)
**Goal**: Export calibration metadata without pickling full caltables

**Example Target**: Stage 14 (hifa_bandpass, 55 MB pickle)

**Tasks**:
- [ ] Design calibration result schema
  - Solution table list (names, types, sizes)
  - Applied calibration steps
  - QA scores per solution
  - Antenna/spw coverage metrics
- [ ] Implement `CalibrationResultMetadata` class
- [ ] Update calibration tasks to export metadata
- [ ] Validate calibration weblogs can render from metadata

**Estimated Effort**: 3-4 days  
**Success Criteria**: Calibration weblog sections render without unpickling full results

#### 2.2 Imaging Task Results (Priority: High)
**Goal**: Export image statistics and metadata

**Example Target**: Stage 45 (hif_makeimlist, 15 MB pickle)

**Tasks**:
- [ ] Design imaging result schema
  - Image list (paths, sizes, cube dimensions)
  - RMS/peak statistics per image
  - Clean iteration counts
  - Mask coverage
- [ ] Implement `ImagingResultMetadata` class
- [ ] Update imaging tasks to export metadata
- [ ] Validate imaging weblogs can render from metadata

**Estimated Effort**: 3-4 days  
**Success Criteria**: Imaging weblog sections render without unpickling full results

#### 2.3 Flagging Task Results (Priority: Low)
**Goal**: Export flagging statistics without view arrays

**Note**: Strategy A already achieves 92.3% reduction via transient fields. This extends it with structured export.

**Tasks**:
- [ ] Design flagging result schema
  - Flagging percentages by antenna/spw/time
  - Flag reason counts
  - Before/after statistics
- [ ] Implement `FlaggingResultMetadata` class
- [ ] Update flagging tasks to export metadata
- [ ] Consider deprecating transient field approach in favor of structured export

**Estimated Effort**: 2-3 days  
**Success Criteria**: Flagging statistics available without unpickling

---

### Layer 3: Lazy Loading Framework (0% Complete)

**Goal**: Load pickles only when actually needed, prefer metadata for common operations

**What's Done**:
- ❌ Nothing (current arch unpickles all results for weblog)

**What Remains**:

#### 3.1 Renderer Metadata-First Architecture (Priority: High)
**Goal**: Weblog renderers load metadata first, pickle only if complex object needed

**Current Behavior**:
```python
# htmlrenderer.py line 2141 (current)
context.results = [proxy.read() for proxy in context.results]  # Unpickles ALL results
```

**Target Behavior**:
```python
# Load metadata only
for proxy in context.results:
    proxy.metadata = ResultMetadata.from_yaml(proxy.path + '-metadata.yaml')

# Unpickle only when renderer explicitly needs full result
def render_stage(result_proxy):
    metadata = result_proxy.metadata
    if needs_full_result(metadata):
        full_result = result_proxy.read()
    else:
        # Render from metadata alone
        render_from_metadata(metadata)
```

**Tasks**:
- [ ] Create `ResultsProxy.load_metadata()` method
- [ ] Audit all renderers to identify pickle dependencies
- [ ] Refactor renderers to prefer metadata
- [ ] Add `needs_full_result()` detection logic
- [ ] Update htmlrenderer.py to load metadata first
- [ ] Benchmark memory usage improvement

**Estimated Effort**: 5-7 days  
**Success Criteria**: 
- 50%+ reduction in memory usage during weblog rendering
- 90%+ of weblog content rendered from metadata alone
- Zero functional regressions

#### 3.2 Context Query API (Priority: Medium)
**Goal**: Enable context queries without unpickling

**Example Use Cases**:
```python
# Find all stages with QA warnings
stages = context.query_stages(qa_warnings=True)

# Get timing for specific task
timing = context.get_stage_metadata(stage=14).timestamps

# List all calibration tables created
caltables = context.query_results(task_type='calibration')
```

**Tasks**:
- [ ] Design query API interface
- [ ] Implement metadata-based queries
- [ ] Add caching to avoid repeated file I/O
- [ ] Create usage examples and documentation

**Estimated Effort**: 2-3 days  
**Success Criteria**: Common queries 100x faster than unpickling

#### 3.3 Optional Pickle Generation (Priority: Low)
**Goal**: Make result pickle generation optional for tasks where metadata is sufficient

**Tasks**:
- [ ] Add `--skip-pickle` flag to pipeline
- [ ] Identify tasks safe to skip pickling (most flagging tasks)
- [ ] Update task execution to conditionally pickle
- [ ] Ensure backward compatibility (old code expects pickles)

**Estimated Effort**: 2 days  
**Success Criteria**: 30-50% reduction in saved_state size when flag enabled

---

## 📅 Implementation Phases

### Phase 5: Complete Layer 2 (6-8 days)
**Focus**: Structured task result export

**Deliverables**:
1. Calibration result metadata (3-4 days)
2. Imaging result metadata (3-4 days)

**Success Metrics**:
- 70%+ of weblog content renderable from metadata
- Pickle unpickling reduced by 50%+

---

### Phase 6: Implement Layer 3 (7-10 days)
**Focus**: Lazy loading and metadata-first architecture

**Deliverables**:
1. Renderer metadata-first refactor (5-7 days)
2. Context query API (2-3 days)

**Success Metrics**:
- 90%+ of weblog rendered from metadata
- Memory usage reduced by 50%+
- Query performance 100x faster

---

### Phase 7: Polish and Documentation (3-4 days)
**Focus**: Production readiness and adoption

**Deliverables**:
1. Metadata schema validation (1 day)
2. Complete documentation (1 day)
3. Migration guide for external tools (1 day)
4. Performance benchmarks and tuning (1 day)

**Success Metrics**:
- Documentation complete and published
- External tool integration examples
- Performance regression tests passing

---

## 🎯 Success Criteria

### Overall Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| **Metadata Load Time** | 500ms (unpickle) | 5ms (YAML load) |
| **Memory Usage (Weblog)** | 500 MB (all pickles) | 50-100 MB (metadata only) |
| **Storage Footprint** | 1.24 GB (large dataset) | 200-300 MB (metadata + selective pickle) |
| **Search/Query Time** | Impossible (binary) | <100ms (text search) |
| **External Tool Support** | Python only | Any language (JSON/YAML) |
| **Metadata Coverage** | 30% (basic only) | 90% (comprehensive) |

### Qualitative Goals

- [ ] Context inspection possible without Python
- [ ] Weblog rendering 2x faster (less unpickling)
- [ ] External tools can parse pipeline outputs
- [ ] Version-independent metadata format
- [ ] Zero breaking changes to existing code

---

## 🛠️ Tools and Support

### Investigation Tools (Available)
- `tools/profile_result_objects.py` - Profile result structure and size
- `tools/survey_result_objects.py` - Survey all result classes
- `tools/audit_storage_reduction.py` - Compare before/after storage
- `tools/debug_pickle_contents.py` - Quick pickle inspection

### New Tools Needed
- [ ] Metadata coverage auditor (identify incomplete exports)
- [ ] Renderer dependency analyzer (identify pickle requirements)
- [ ] Metadata schema validator
- [ ] Migration script for external tools

---

## 📝 Implementation Notes

### Design Principles

1. **Additive Changes Only**: All changes must be backward compatible
2. **Metadata First**: Always prefer metadata for common operations
3. **Pickle as Fallback**: Keep pickle for complex objects
4. **Incremental Adoption**: Allow gradual migration, no big-bang switchover
5. **Measure Everything**: Benchmark before/after for all changes

### Testing Strategy

For each phase:
1. Unit tests for new metadata classes
2. Integration tests with full pipeline runs
3. Weblog rendering regression tests
4. Performance benchmarks (memory, CPU, I/O)
5. Validation on small, medium, large datasets

### Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Performance regression | Profile before/after, add caching |
| Incomplete metadata | Create comprehensive schemas, validation |
| Renderer breakage | Extensive regression testing, defensive coding |
| Memory leaks | Monitor memory usage, add automated tests |
| User confusion | Clear documentation, migration examples |

---

## 🔗 Related Documents

- [CONTEXT_STORAGE_INVESTIGATION.md](CONTEXT_STORAGE_INVESTIGATION.md) - Original investigation and strategy
- [STRATEGY_A_IMPLEMENTATION.md](STRATEGY_A_IMPLEMENTATION.md) - Completed Phase 4 work
- [FRAMEWORK.md](FRAMEWORK.md) - Phases 1-3 implementation details
- [SERIALIZATION_INTEGRATION_GUIDE.md](SERIALIZATION_INTEGRATION_GUIDE.md) - How to use current framework
- [OPTIMIZATION_WORK_ARCHIVE.md](OPTIMIZATION_WORK_ARCHIVE.md) - Archived incremental optimization work

---

## 📞 Questions?

**Q: Why not just optimize pickles further?**  
A: Task-specific optimization doesn't scale (see [OPTIMIZATION_WORK_ARCHIVE.md](OPTIMIZATION_WORK_ARCHIVE.md)). Modernization provides structural benefits for all tasks.

**Q: Will this break existing code?**  
A: No. All changes are additive. Pickles remain available. Old code continues to work.

**Q: When can we stop using pickle?**  
A: Never completely - pickle remains for complex objects. But 90%+ of operations should use metadata.

**Q: What's the priority order?**  
A: Phase 5 (Layer 2) → Phase 6 (Layer 3) → Phase 7 (Polish). Focus on calibration/imaging tasks first.

---

## 🚦 Getting Started

### Immediate Next Steps (This Week)

1. **Review this roadmap** with team
2. **Validate priorities** - Is calibration metadata most valuable?
3. **Assign ownership** - Who implements Phase 5?
4. **Set timeline** - When should Phase 5 complete?

### Week 1 Action Items

1. Start Phase 5.1: Design calibration result schema
2. Create `CalibrationResultMetadata` class skeleton
3. Prototype metadata export for one calibration task
4. Validate schema captures 80%+ of weblog needs

---

**Ready to begin implementation!** 🚀
