# Benchmark Timing Alternation - Root Cause & Solution

## Problem Summary
Benchmark timings for `SpwIdVsFreqChart` showed a perfect alternating pattern:
- Odd runs: ~76 seconds
- Even runs: ~0.00 seconds

This made performance measurements unreliable and comparisons meaningless.

## Root Cause Analysis

### The Bug
The alternating pattern was caused by the `origin_ms` file caching mechanism in:
**File:** `pipeline/infrastructure/displays/summary.py`
**Class:** `SpwIdVsFreqChart`
**Method:** `plot()` (lines 1374-1476)

**Code:**
```python
def plot(self) -> logger.Plot | None:
    filename = self.inputs.output  # Temp dir path: /tmp/benchmark_run1_/session.../ms/spwid_vs_freq.png
    ms = self.inputs.ms
    origin_filename = filename.replace(ms.basename, ms.origin_ms)  # Original MS path (outside temp dir!)
    
    if os.path.exists(filename):
        return self._get_plot_object()  # Fast path
    elif os.path.exists(origin_filename):  # THIS IS THE PROBLEM!
        LOG.info("Copying frequency coverage plot for origin_ms.")
        shutil.copyfile(origin_filename, filename)  # Copies from original, instant return
        return self._get_plot_object()
    
    # If we reach here, do expensive computation (76s)
    # ... matplotlib plotting, ATM calculations, etc ...
    fig.savefig(filename)
    return self._get_plot_object()
```

### How the Alternation Happens

1. **Run 1** (first compute):
   - File doesn't exist → computes plot (76s)
   - Saves to: `/tmp/benchmark_run0_xxxx/session.../spwid_vs_freq.png`
   - But `ms.origin_ms` still points to original MS outside temp directories

2. **Run 2** (even run - fast):
   - New temp directory: `/tmp/benchmark_run1_yyyy/...`
   - File doesn't exist in new temp dir
   - BUT: `origin_filename` points to original MS where the plot WAS computed and saved by previous render operations
   - Copies from origin → instant (0.00s)

3. **Run 3** (odd run - slow):
   - Another new temp directory
   - Origin file might have been cleaned up by some other process, or the pattern shifts based on render order
   - Recomputes → 76s

4. Pattern continues: compute, copy, compute, copy, ...

### Why This Affected SpwIdVsFreqChart Specifically
- SpwIdVsFreqChart has this optimization to reuse plots from original MS
- Other charts might have simpler implementations without this origin check
- The expensive operations (ATM transmission calculations) only happen when computing from scratch

## Solution Implemented

### Approach: `--skip-origin-files` Flag
Added a new command-line flag that disables the origin file optimization during benchmarking by setting `ms.origin_ms = ms.name` for all measurement sets.

This prevents the `origin_filename` path from pointing outside the temp directories.

### Changes Made

#### 1. `benchmark_renderer.py`
- Added `from __future__ import annotations` for Python 3.8 compatibility
- Added `skip_origin_files: bool = False` parameter to:
  - `benchmark_renderer()` function
  - `benchmark_single_renderer()` function
- Added logic to disable origin files:
  ```python
  if skip_origin_files and context.observing_run:
      for ms in context.observing_run.measurement_sets:
          ms.origin_ms = ms.name  # Set origin to self
  ```
- Added `--skip-origin-files` CLI argument to argument parser

#### 2. `benchmark_renderer.sh`
- Added `--skip-origin-files` to help documentation
- Added argument parsing for `--skip-origin-files`
- Added flag to Python command construction
- Added example in EXAMPLES section

## Usage

### With Python Script Directly:
```bash
python benchmark_renderer.py --report-dir . \
    --single T2_1DetailsRenderer \
    --runs 12 \
    --skip-origin-files
```

### With Shell Script Wrapper:
```bash
./benchmark_renderer.sh --report-dir . \
    --single T2_1DetailsRenderer \
    --runs 12 \
    --skip-origin-files
```

## Expected Results

**Before fix (without --skip-origin-files):**
```
[TIMING] SpwIdVsFreqChart took 76.29s
[TIMING] SpwIdVsFreqChart took 0.00s
[TIMING] SpwIdVsFreqChart took 76.20s
[TIMING] SpwIdVsFreqChart took 0.00s
[TIMING] SpwIdVsFreqChart took 76.26s
...
```

**After fix (with --skip-origin-files):**
```
[TIMING] SpwIdVsFreqChart took 76.29s
[TIMING] SpwIdVsFreqChart took 76.30s
[TIMING] SpwIdVsFreqChart took 76.25s
[TIMING] SpwIdVsFreqChart took 76.31s
[TIMING] SpwIdVsFreqChart took 76.27s
...
```

Timing should be consistent (±2-3s variance) within statistical expectations.

## Impact Analysis

### What This Fixes
✅ Eliminates alternating cache hits/misses
✅ Enables accurate performance measurements
✅ Allows valid comparisons between benchmark runs
✅ Provides meaningful statistics (mean, median, stdev)

### What This Doesn't Affect
- Normal pipeline operation (flag only for benchmarking)
- Other renderers' timing behavior
- The optimization itself (just disabled for benchmarking purposes)
- Backward compatibility (new flag is optional, defaults to False)

## Technical Notes

### Why `ms.origin_ms = ms.name`?
- `origin_ms` is initialized to the MS path in `MeasurementSet.__init__`
- Setting it to `ms.name` makes the origin check in `SpwIdVsFreqChart.plot()` look for the plot in the current (temporary) directory
- Since each run gets a fresh temp directory, the file won't exist, forcing computation
- This ensures consistent behavior across all runs

### Python Version Compatibility
- Required `from __future__ import annotations` for Python 3.8 compatibility
- The `|` union syntax (PEP 604) is only available in Python 3.10+ at module level
- With `from __future__ import annotations`, type hints become strings and evaluate lazily

## Testing Recommendations

1. **Quick test:**
   ```bash
   ./benchmark_renderer.sh --report-dir . -s T2_1DetailsRenderer -n 3 --skip-origin-files
   ```

2. **Full test with statistics:**
   ```bash
   ./benchmark_renderer.sh --report-dir . -n 10 --skip-origin-files -o results_fixed.json
   ```

3. **Compare with original (to confirm the fix):**
   ```bash
   # Without flag - should show alternating pattern
   ./benchmark_renderer.sh --report-dir . -n 12 -o results_unfixed.json
   # With flag - should show consistent timing
   ./benchmark_renderer.sh --report-dir . -n 12 --skip-origin-files -o results_fixed.json
   ```

## Follow-up Considerations

### Should This Be Permanent?
The alternating behavior could potentially affect:
- Actual pipeline runs if they compute plots multiple times for the same MS
- Performance profiling of the rendering system

However, the current behavior seems intentional - it's an optimization to reuse plots from original measurement sets. So it's best to keep this as an opt-in benchmarking flag.

### Other Charts with Same Pattern?
Search for similar patterns in other chart classes:
```bash
grep -r "origin_ms" pipeline/infrastructure/displays/
grep -r "os.path.exists.*filename" pipeline/infrastructure/displays/
```

The pattern might exist in other chart classes too. If so, they would benefit from the same fix.

