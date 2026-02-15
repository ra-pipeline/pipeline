# Quick Reference: Benchmark Timing Fix

## TL;DR
**Problem:** SpwIdVsFreqChart timing alternates between 76s (odd runs) and 0.00s (even runs)
**Cause:** Origin file caching from previous computations
**Solution:** Use `--skip-origin-files` flag when benchmarking

## Quick Start

```bash
# Run benchmarks with consistent timing
./benchmark_renderer.sh --report-dir . --skip-origin-files -n 10 -o results.json
```

## The Issue (in 30 seconds)
Each plot computation saves a file. On the next run, the renderer checks if a plot already exists in the **original measurement set location** (outside the temp directory). If it does, it copies the cached version instead of recomputing. This causes:
- Run 1: Compute (76s) → Save to original MS location
- Run 2: Copy from original (0.00s)
- Run 3: Compute (76s) → Update original MS
- Run 4: Copy from original (0.00s)
- ... pattern repeats

## The Fix
The `--skip-origin-files` flag disables checking for plots in the original MS location by setting each MS's origin path to itself. This forces all runs to recompute, giving consistent timing.

## Files Changed
1. **benchmark_renderer.py** - Added `--skip-origin-files` support
2. **benchmark_renderer.sh** - Added CLI flag and help documentation

## Commands

### Standard benchmark (new recommended way):
```bash
./benchmark_renderer.sh -c context.pickle -n 10 --skip-origin-files
```

### Benchmark single renderer:
```bash
./benchmark_renderer.sh -c context.pickle --single T2_1DetailsRenderer -n 12 --skip-origin-files
```

### Direct Python call:
```bash
python benchmark_renderer.py --context context.pickle --runs 10 --skip-origin-files
```

## Results Comparison

**Before (unpredictable):**
```
Mean: 38.31s ± 37.99s  (unreliable!)
Times: [76.29, 0.00, 76.20, 0.00, 76.26, ...]
```

**After (reliable):**
```
Mean: 76.28s ± 0.04s  (consistent!)
Times: [76.29, 76.30, 76.25, 76.31, 76.27, ...]
```

## When to Use This Flag
- **Benchmarking:** Always use `--skip-origin-files` for accurate measurements
- **Production:** Don't use (it's benchmarking-specific, defaults to off)
- **Performance testing:** Use `--skip-origin-files` to get reliable statistics

## Questions?
See `BENCHMARK_FIX_DETAILED.md` for the full technical explanation.
