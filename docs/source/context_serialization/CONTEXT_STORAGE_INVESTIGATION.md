# Pipeline Context Storage System Investigation

## Executive Summary

The pipeline currently stores stage information through a **pickle-based hybrid approach** where:
1. The entire `Context` object is pickled to disk
2. Individual `Results` objects are proxied and pickled separately
3. CASA logs are extracted and stored as text files
4. Metadata is maintained in dictionaries within results objects

While this approach works, there are **significant opportunities for improvement** through structured serialization formats that would provide better maintainability, readability, and interoperability.

---

## Current System Architecture

### 1. **Context Storage** ([launcher.py](launcher.py))

```python
# Context is pickled as a complete binary object
def save(self, filename: str | None = None) -> None:
    if filename in ('', None):
        filename = f'{self.name}.context'
    with open(filename, 'wb') as context_file:
        pickle.dump(self, context_file, protocol=-1)
```

**Key Components:**
- **Results List**: `context.results` is a list of `ResultsProxy` objects
- **Task Counter**: `context.task_counter` and `context.subtask_counter` track stage progress
- **State Data**: Multiple dictionaries store calibration, imaging, and processing state
- **Domain Objects**: `context.observing_run` contains metadata about measurement sets, scans, etc.

### 2. **Results Storage** ([basetask.py](basetask.py))

**Results Class Hierarchy:**
```
Results (base class)
├── FailedTaskResults (for exceptions)
└── ResultsList (generic container)
```

**Storage Pattern:**
```python
# ResultsProxy handles lazy loading/unloading of results
class ResultsProxy(object):
    def write(self, result):
        # Pickle individual result to disk
        self._basename = f'result-stage{stage_number}.pickle'
        with open(path, 'wb') as outfile:
            pickle.dump(result, outfile, pickle.HIGHEST_PROTOCOL)
    
    def read(self):
        # Load result from disk when needed
        with open(path, 'rb') as infile:
            return utils.pickle_load(infile)
```

**Directory Structure:**
```
<output_dir>/<context_name>/
├── <context_name>.context                    # Main pickled context
├── saved_state/
│   ├── result-stage0.pickle
│   ├── result-stage1.pickle
│   ├── context-stage0.pickle                 # DEBUG level only
│   └── ...
├── html/
│   ├── casapy.log
│   └── stage<N>/
│       └── casapy.log                        # Stage-specific CASA logs
└── <other files>
```

### 3. **Existing Serialization Elements**

**Limited JSON/YAML Usage:**
- `timetracker.py` exports execution timing as JSON
- `pipeline_statistics.py` references JSON serialization in comments
- `selfcal.py` imports `JsonCustomEncoder` from astropy but primarily uses pickle

**Metadata Storage:**
```python
# Results store metadata as dictionaries
self._metadata = {}  # presentation-focused values for weblog
self.inputs = inputs.as_dict()  # task inputs converted to dict
```

---

## Current Limitations

### 1. **Binary Pickle Issues**

| Issue | Impact |
|-------|--------|
| **Non-Human Readable** | Cannot inspect results without unpickling (can't grep/search) |
| **Version Fragile** | Python version/library updates can break unpickling |
| **Security Risk** | Arbitrary code execution if pickle contains malicious data |
| **Large File Size** | Binary format doesn't compress well; includes redundant data |
| **Difficult Debugging** | Can't easily inspect intermediate state or compare runs |

### 2. **Storage Redundancy**

- **Context**: Contains references to all domain objects + metadata
- **Individual Results**: Each result contains a copy of `inputs.as_dict()` and metadata
- **CASA Logs**: Extracted and stored separately, then deleted from results to "save space"
- **Metadata Duplication**: Same metadata stored in multiple locations

**Example**: A single context file can be **hundreds of MB** even for moderate-sized processing runs

### 3. **Access Patterns**

Current web log rendering requires:
```python
# To access results, must load full pickled object
for proxy in context.results:
    result = proxy.read()  # Unpickles entire result
    # Extract needed information
```

This is inefficient for:
- Querying specific metadata without loading full object
- Streaming large result sets
- Archiving/analyzing completed runs
- Integration with external tools

### 4. **API Instability**

The documentation itself notes:
> "The context class and domain object classes are not officially designated or maintained as public APIs. Consequently, their interfaces and definitions are subject to frequent changes across releases..."

This makes pickle-based storage fragile across versions.

---

## Proposed Improvements

### **Recommended Approach: Hybrid Serialization Strategy**

Rather than replacing pickle entirely, implement a **layered serialization system**:

#### **Layer 1: Structured Metadata (YAML, JSON optional)**
Store easily-accessed, human-readable metadata:
- Task execution summary (name, timing, status)
- Input parameters
- QA scores
- Simple statistics

Example (JSON shown; YAML is the default export format):
```json
{
  "stage": 0,
  "task_name": "hifa_importdata",
  "timestamps": {
    "start": "2026-01-30T14:23:45Z",
    "end": "2026-01-30T14:25:12Z",
    "duration_seconds": 87
  },
  "status": "completed",
  "inputs": {
    "vis": ["uid___A001_X1234_X5678.ms"],
    "asdm": null
  },
  "qa_scores": {
    "overall": 0.85,
    "antenna_qa": 0.92
  }
}
```

#### **Layer 2: Task-Specific Results (YAML or JSON)**
Structured export of key results without pickling:
- Calibration table metadata (not the caltables themselves)
- Image statistics
- Processing flags and warnings
- Sky model information

```yaml
# result-stage0-summary.yaml
task: hifa_importdata
measurement_sets:
  - name: "uid___A001_X1234_X5678.ms"
    source_count: 3
    spw_count: 4
    antenna_count: 47
    time_range: ["2026-01-15T10:00:00", "2026-01-15T12:30:00"]
    intent_counts:
      CALIBRATE_ATMOSPHERE: 12
      CALIBRATE_BANDPASS: 18
      CALIBRATE_DELAY: 6
      CALIBRATE_FLUX: 8
      CALIBRATE_PHASE: 24
      CALIBRATE_POINTING: 10
      OBSERVE_TARGET: 148
warnings:
  - "RFI detected in SPW 2"
  - "Low elevation target observed"
```

#### **Layer 3: Rich Objects (Pickle as Fallback)**
Keep pickle for:
- Complex numpy arrays (image data, visibility metadata)
- Domain objects needed for continuation
- Non-serializable state objects (CASA tool references, etc.)

Store strategically:
- **Full context pickle**: Only on explicit save/resume
- **Result pickles**: Only for complex task-specific data
- **Metadata pickle**: Eliminated in favor of JSON/YAML

### **Benefits of This Approach**

| Benefit | Details |
|---------|---------|
| **Readability** | JSON/YAML layers are human-inspectable and tool-compatible |
| **Maintainability** | Structured formats survive Python/library version changes |
| **Performance** | Small metadata loads fast; large objects load only when needed |
| **Debuggability** | Can search/grep stage metadata; easy to find anomalies |
| **Archival** | Text-based metadata can be easily archived or indexed |
| **Integration** | External tools can parse JSON/YAML without Python dependencies |
| **Compression** | Text formats compress 3-5x better than binary pickle |
| **Backward Compat** | Pickle still available; can migrate incrementally |

---

## Implementation Strategy

### **Phase 1: Metadata Extraction (Low Risk) - ✅ Complete**
1. Created `ResultMetadata` dataclass with key fields
2. Exported YAML/JSON alongside existing pickles
3. Added utilities to load metadata without unpickling
4. No changes to core pickle path

### **Phase 2: Structured Results Export + Weblog Caching (Medium Risk) - ✅ Complete**
1. Implemented task-specific serializers (YAML-based)
2. Stored renderer metadata alongside results
3. Provided compatibility layer for existing code
4. Updated weblog renderers to load cached metadata where possible

### **Phase 3: Context Load Optimization (Higher Risk) - ✅ Complete**
1. Implemented adaptive parallel unpickling in weblog rendering
2. Added thread-safety for shared CalFrom pool
3. Added ResultsProxy path support for size-based tuning
4. Validated on production datasets (INT, SD, Large)

### **Phase 4: Context Optimization (Higher Risk) - 🔜 Next**
1. Refactor context to store metadata separately from heavyweight state
2. Reduce pickle size by excluding serializable data
3. Implement incremental context saves and faster resume

---

## Recommended Serialization Technology

### **JSON**
- **Use For**: Execution metadata, simple statistics, timing data
- **Pros**: Universal support, small file size, human-readable
- **Cons**: No comments, date handling requires special encoder

### **YAML**
- **Use For**: Structured task results, configuration snapshots
- **Pros**: Highly readable, supports comments, native date types
- **Cons**: Parser performance (less critical for metadata)

### **HDF5** (Optional, if advanced use cases emerge)
- **Use For**: Large numpy arrays (images, visibility metadata)
- **Pros**: Efficient storage, compression, chunking
- **Cons**: Additional dependency, learning curve

---

## Code Architecture Example

```python
# New serializer module structure
pipeline/infrastructure/serializers/
├── __init__.py
├── base.py              # Abstract serializer interface
├── json_serializer.py   # JSON metadata export
├── yaml_serializer.py   # YAML task results export
└── legacy.py            # Pickle compatibility layer

# Usage pattern
from pipeline.infrastructure.serializers import ResultMetadata

# Export metadata without pickling full result
metadata = ResultMetadata.from_result(result)
metadata.to_json('result-stage0.json')

# Load metadata efficiently
metadata = ResultMetadata.from_json('result-stage0.json')
print(metadata.task_name, metadata.status, metadata.duration)

# Full result still available if needed
full_result = pickle.load('result-stage0.pickle')
```

---

## Migration Path

### **Non-Breaking Changes** (Implement First)
1. ✅ Add JSON export alongside existing pickles
2. ✅ Create metadata schema
3. ✅ Add utility functions to load metadata
4. ✅ Update documentation

### **Gradual Adoption** (Phase 2-3)
1. Update web log renderer to prefer JSON/YAML
2. Add deprecation warnings for direct pickle access
3. Provide migration script for existing contexts
4. Update CI/tests to validate both formats

### **Future (Long-term)**
1. Make JSON/YAML primary with pickle optional
2. Implement lazy loading framework
3. Remove pickle dependency for simple use cases

---

## Specific Recommendations for Your Use Case

### **If Performance is Priority**
→ Focus on **Layer 1 (JSON Metadata)** + selective pickle caching

### **If Maintainability is Priority**
→ Implement **Layer 1 + 2 (JSON + YAML)** with comprehensive serializers

### **If Integration is Priority**
→ Add **REST API** that serves JSON directly from serialized metadata

### **If Storage is Priority**
→ Implement **compression** and **deduplication** in Layer 3

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Backward compatibility breakage | Implement alongside pickle; test extensively |
| Performance regression | Profile lazy-loading; use caching |
| Incomplete serialization | Create comprehensive test suite; validate round-trips |
| Complex object graph issues | Start with simple tasks; expand gradually |
| User confusion | Clear documentation; provide migration tools |

---

## Next Steps

1. **Review** this analysis with stakeholders
2. **Choose** implementation strategy based on priorities
3. **Prototype** Layer 1 (JSON metadata) as proof-of-concept
4. **Measure** impact on performance/storage/usability
5. **Iterate** based on results
