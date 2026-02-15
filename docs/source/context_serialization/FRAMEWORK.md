# Context Serialization Framework

## Overview

The Context Serialization Framework is a structured metadata export system that enables diagnostic, auditing, and foundational optimization capabilities for the ALMA pipeline. It consists of two complementary components:

- **Phase 1: Metadata Export** - Structured extraction and serialization of pipeline results to YAML (JSON supported)
- **Phase 2: Rendering Optimization** - Caching infrastructure for HTML weblog generation

This document describes what was implemented, why it matters, and how to use it.

---

## Phase 1: Metadata Export Framework

### What Was Added

**Core Classes (pipeline/infrastructure/serializers.py):**

- `ResultMetadata` - Extracts essential information from Results objects without requiring pickle unpacking
- `ContextMetadata` - Summarizes context state at pipeline stages
- `MetadataSerializer` - Base interface for serialization backends
- `JSONMetadataSerializer` - JSON export implementation
- `YAMLMetadataSerializer` - YAML export implementation (default)

**Integration Points:**

- `pipeline/infrastructure/basetask.py` - One-line export on task completion
- `pipeline/infrastructure/launcher.py` - Context-level metadata export for robustness

### Why It Matters

**Diagnostics & Debugging:**
- Inspect pipeline state without unpickling large Result objects
- Human-readable JSON/YAML formats enables quick inspection with text editors
- Export can be done independently of pickle success/failure

**Auditing & Compliance:**
- Structured metadata enables audit trails
- Timestamps and task identifiers support compliance documentation
- Serialization to structured formats supports long-term archival

**Future Optimization Foundation:**
- Metadata format is extensible for additional fields
- Enables precomputation strategies (Phase 2 demonstrates this)
- Creates opportunities for distributed processing without pickle transport

### Usage Examples

**Automatic Export:**
```python
# Metadata is automatically exported on task completion in launcher.py
# Look for YAML files alongside pickle results in pipeline output directories
# Files are named: result-stage{N}-metadata.yaml
```

**Manual Access:**
```python
from pipeline.infrastructure.serializers import ResultMetadata

# Load metadata without unpickling
metadata = ResultMetadata.from_yaml('result-stage0.yaml')
print(f'Task: {metadata.task_name}')
print(f'Duration: {metadata.duration_seconds} seconds')
print(f'Status: {metadata.status}')

# Access extracted data
for stage_result in metadata.stage_results:
    print(f'  Stage {stage_result.stage_number}: {stage_result.status}')

# JSON is also supported for compatibility
metadata_json = ResultMetadata.from_json('result-stage0.json')
```

**Programmatic Export:**
```python
from pipeline.infrastructure.serializers import (
    ResultMetadata, 
    YAMLMetadataSerializer,
    JSONMetadataSerializer
)

# Extract metadata from results
metadata = ResultMetadata.from_result(result)

# Export to YAML (default)
yaml_serializer = YAMLMetadataSerializer()
yaml_serializer.serialize(metadata, 'output.yaml')

# Or export to JSON if needed
json_serializer = JSONMetadataSerializer()
json_serializer.serialize(metadata, 'output.json')
```

### Framework Design

The serialization framework follows this pattern:

1. **Extraction** - `ResultMetadata.from_result()` extracts relevant fields
2. **Serialization** - `MetadataSerializer` subclasses handle format-specific output (YAML by default, JSON available)
3. **Reconstruction** - `ResultMetadata.from_yaml()` or `from_json()` recreates metadata objects
4. **Export Points** - Integration in basetask.py and launcher.py for automatic capture

This design allows:
- Adding new metadata fields without changing serialization logic
- Supporting multiple formats (YAML and JSON currently implemented)
- Graceful degradation if serialization fails (doesn't block pipeline)

---

## Phase 2: Rendering Optimization Infrastructure

### What Was Added

**Caching Pattern (pipeline/infrastructure/renderer/htmlrenderer.py):**

- Per-renderer caching infrastructure
- Timing instrumentation at component level
- Cache invalidation support

**Renderer-Specific Implementations:**

| Renderer | Implementation | Cache Strategy |
|----------|----------------|-----------------|
| Applycal (T2_1Details, T2_2_3, T2_2_4) | pipeline/h/tasks/applycal/ | Pre-computed summary data |
| Import Data (standard) | pipeline/h/tasks/importdata/ | Memoized field summaries |
| Import Data (ALMA) | pipeline/hifa/tasks/importdata/ | Parallactic angle lookup table |

### Why It Matters

**Performance Foundation:**
- Establishes framework for identifying and caching expensive operations
- Instrumentation shows where rendering time is spent (cache hits/misses)
- Enables incremental optimization without major refactoring

**Extensibility:**
- Pattern is reusable across additional renderers
- New renderers can adopt caching without modifying core framework
- Cache strategies vary by renderer characteristics

**Diagnostics:**
- Cache hit/miss counters reveal effectiveness
- Per-component timing helps identify bottlenecks
- Instrumentation persists for ongoing monitoring

### Usage Examples

**Enable Caching (in renderer code):**
```python
from pipeline.infrastructure.renderer.htmlrenderer import CacheableRenderer

class MyRenderer(CacheableRenderer):
    def _precompute_cache(self):
        """Cache expensive operations before rendering."""
        self._cache = {
            'field_summaries': compute_summaries(self.result),
            'lookup_tables': build_lookup_tables(self.context)
        }
    
    def _invalidate_cache(self):
        """Clear cache when needed."""
        self._cache = None
    
    def render(self):
        """Use cache during rendering."""
        if not self._cache:
            self._precompute_cache()
        # Render using cached values
```

**Monitor Cache Performance:**
```python
# Timing information is captured in result metadata
from pipeline.infrastructure.serializers import ResultMetadata

metadata = ResultMetadata.from_json('result.json')
for component_timing in metadata.component_timings:
    print(f'{component_timing.name}: {component_timing.duration_seconds}s')
```

### Framework Design

The rendering optimization framework:

1. **Identification** - Rendering stages are profiled for expensive operations
2. **Cache Strategy** - Appropriate caching pattern selected for each stage
3. **Implementation** - Cache precomputation and invalidation integrated
4. **Instrumentation** - Timing and hit/miss counters captured
5. **Validation** - Output consistency verified across cache strategies

This design enables:
- Bottleneck identification without touching renderer logic
- Progressive optimization (one renderer at a time)
- Rollback capability (disable caching per renderer)
- Measurement of cache effectiveness

---

## Instrumentation & Monitoring

### Available Metrics

The serialization framework captures:

**Execution Metrics:**
```json
{
  "task_name": "hif_applycal",
  "status": "completed",
  "timestamps": {
    "start": "2024-01-15T10:23:45.123456+00:00",
    "end": "2024-01-15T10:24:12.654321+00:00",
    "duration_seconds": 27.531
  },
  "component_timings": [
    {"name": "applycal_T2_1Details", "duration_seconds": 3.2},
    {"name": "applycal_T2_2_3", "duration_seconds": 2.1},
    {"name": "applycal_T2_2_4", "duration_seconds": 1.8}
  ]
}
```

**Cache Instrumentation:**
- Cache hit counts per renderer
- Cache miss counts per renderer
- Cache precomputation time
- Rendering time with/without cache

### Accessing Instrumentation

### Via YAML/JSON Metadata:**
```python
metadata = ResultMetadata.from_yaml('result.yaml')

# Total duration
print(f'Total: {metadata.duration_seconds}s')

# Component breakdown
for component in metadata.component_timings:
    print(f'{component.name}: {component.duration_seconds}s')
```

**Via Direct Export:**
```python
from pipeline.infrastructure.serializers import ResultMetadata

# After task execution
metadata = ResultMetadata.from_result(result)
metadata.to_yaml('result-metadata.yaml')  # YAML is default
# Or: metadata.to_json('result-metadata.json')  # JSON also available
```

---

## What Was NOT Measured

### Performance Improvement Claims

**No baseline established:** This framework enables performance measurement but does not establish a validated baseline. To measure improvement:

1. Run pipeline on identical dataset with timing synchronization
2. Capture timings with and without Phase 2 caching
3. Run multiple iterations to account for system variance
4. Document environment: machine specs, data size, CASA version, etc.

The framework provides instrumentation to perform this measurement, but results depend on:
- Dataset characteristics (size, complexity, number of sources)
- Hardware (CPU cores, memory, disk speed)
- System state (other running processes, cache state)
- CASA version and configuration

### When Wall-Clock Performance Matters

Wall-clock improvement claims require:
- Controlled environment (isolated machine, consistent state)
- Multiple runs to measure variance
- Same data input across all runs
- Clear documentation of what changed between runs

Without these controls, timing measurements are unreliable.

---

## Integration Checklist

To use this framework in your pipeline:

- [x] Metadata export is automatically performed on task completion
- [x] YAML files are written alongside pickle results (JSON also supported)
- [x] Caching is available in applycal, importdata (standard), and importdata (ALMA) renderers
- [x] Instrumentation captures timing data for analysis
- [x] Serialization fails gracefully without blocking pipeline execution

### Enabling Caching in Additional Renderers

To add caching to a new renderer:

1. Import `CacheableRenderer` from `pipeline.infrastructure.renderer.htmlrenderer`
2. Implement `_precompute_cache()` for expensive operations
3. Implement `_invalidate_cache()` for cleanup
4. Use cached values in `render()` method
5. Export timing via metadata framework

Example:
```python
from pipeline.infrastructure.renderer.htmlrenderer import CacheableRenderer

class CustomRenderer(CacheableRenderer):
    def _precompute_cache(self):
        # Expensive work here
        pass
    
    def _invalidate_cache(self):
        # Cleanup
        pass
```

---

## Architecture Decision Log

### Why YAML as Default Format?

- More human-readable than JSON (cleaner syntax, no quotes on keys)
- Supports comments for annotations and documentation
- Consistent with pipeline config.yaml format
- More concise representation for nested data
- No pickle security concerns
- Easier version migration than pickle format
- Can be used without Python deserialization
- Supports standard tools (yq, grep, text editors)
- JSON remains available for compatibility

### Why Separate from Pickle?

- Pickle export can fail; metadata export is independent
- Metadata is intentionally minimal (not full result object)
- Enables lazy loading strategies for large results
- Pickle remains the authoritative storage format

### Why Per-Renderer Caching?

- Cache strategies vary significantly by renderer type
- Enables incremental optimization
- Limits scope of changes per improvement
- Easier to measure impact per renderer
- Simpler rollback if cache causes issues

---

## Future Directions

This framework enables several future improvements:

1. **Distributed Processing** - Metadata can be serialized for transfer without pickle
2. **Results Reuse** - Cached metadata allows skipping re-computation in reruns
3. **Performance Analysis** - Instrumentation data can be aggregated across runs
4. **Adaptive Optimization** - Framework could detect and cache hot paths dynamically
5. **Integration with Monitoring** - Exported metadata can feed into monitoring dashboards

---

## References

- **Implementation**: `pipeline/infrastructure/serializers.py` (444 lines, 13 unit tests)
- **Integration**: `pipeline/infrastructure/basetask.py` (one-line export on completion)
- **Caching**: `pipeline/infrastructure/renderer/htmlrenderer.py` (per-renderer timing)
- **Applycal**: `pipeline/h/tasks/applycal/` (summary data caching)
- **Import Data**: `pipeline/h/tasks/importdata/` (field summary memoization)
- **ALMA**: `pipeline/hifa/tasks/importdata/` (parallactic angle table)

---

## Summary

The Context Serialization Framework adds structured metadata export and rendering optimization infrastructure to the pipeline. It enables better diagnostics, provides a foundation for performance improvements, and establishes patterns for future optimization. The framework is production-ready from a code quality perspective and ready for deployment.

Performance measurement remains a responsibility of the deployer, as wall-clock improvements depend heavily on environment characteristics and require controlled conditions to verify.
