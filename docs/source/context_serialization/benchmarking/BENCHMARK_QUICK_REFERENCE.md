# Benchmarking Quick Reference

Fast cheat sheet for renderer benchmarking workflow.

## Setup (One-time)

```bash
# From pipeline root directory
./setup_benchmark.sh --source /path/to/weblog/output --dest ./bench_test
cd bench_test
```

## Basic Workflow

```bash
# 1. Get baseline
../benchmark_renderer.sh --report-dir . --preset standard -o baseline.json

# 2. Make optimizations to code

# 3. Test changes
../benchmark_renderer.sh --report-dir . --preset standard -o optimized.json

# 4. Compare
../compare_benchmarks.py baseline.json optimized.json
```

## Common Commands

| Task | Command |
|------|---------|
| List renderers | `../benchmark_renderer.sh --list` |
| Quick test | `../benchmark_renderer.sh -r . --preset quick` |
| Standard test | `../benchmark_renderer.sh -r . --preset standard -o result.json` |
| Thorough test | `../benchmark_renderer.sh -r . --preset thorough -o result.json` |
| Single renderer | `../benchmark_renderer.sh -r . -s T1_1Renderer -n 10` |
| With profiling | `../benchmark_renderer.sh -r . --profile --preset quick` |
| Compare results | `../compare_benchmarks.py before.json after.json` |

## Presets

| Preset | Runs | Use Case |
|--------|------|----------|
| `quick` | 3 | Fast validation, dev iteration |
| `standard` | 5 | Default, good for most testing |
| `thorough` | 20 | Final validation, CI/CD |

## Interpretation

```
✓ IMPROVEMENT: X% faster
  → Code change is beneficial

✗ REGRESSION: X% slower  
  → Code change hurts performance

= NO CHANGE
  → Timing impact negligible
```

## Troubleshooting Quick Links

| Problem | Solution |
|---------|----------|
| Context not found | `../benchmark_renderer.sh --context /full/path/context.pickle -n 5` |
| High variance | Increase runs: `-n 20` or set CPU gov: `echo performance \| sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor` |
| Import errors | `export PYTHONPATH=/path/to/pipeline:$PYTHONPATH` |
| Memory issues | Test single renderer: `-s RendererName` |

## Expected Performance

- Quick benchmark: ~30-60 seconds (3 runs of key renderers)
- Standard benchmark: ~2-3 minutes (5 runs of all renderers)  
- Thorough benchmark: ~10-15 minutes (20 runs of all renderers)

vs. Full pipeline: 50+ minutes per run

## Tips

1. **Reduce system noise** before important benchmarks:
   ```bash
   sudo killall firefox python  # Close apps
   ```

2. **Check individual run times** for variance:
   ```bash
   python3 -c "
   import json
   data = json.load(open('result.json'))
   for name, stats in data.items():
       print(f'{name}: {stats[\"times\"]}')"
   ```

3. **Stage your testing**:
   - Quick (3 runs) → promising?
   - Standard (5 runs) → looks good?  
   - Thorough (20 runs) → ready for commit

4. **Create a baseline before optimizing**:
   ```bash
   # First thing: capture baseline
   ../benchmark_renderer.sh -r . -n 10 -o baseline.json
   ```

## File Locations

| File | Purpose |
|------|---------|
| `benchmark_renderer.sh` | Main CLI wrapper |
| `benchmark_renderer.py` | Core Python script |
| `setup_benchmark.sh` | Environment prep |
| `compare_benchmarks.py` | Result comparison |
| `BENCHMARK_README.md` | Full documentation |
| `context.pickle` | Cached context (in test dir) |
| `benchmark_results/` | Output directory |

## Next Steps

1. Read [BENCHMARK_README.md](BENCHMARK_README.md) for full details
2. Run setup: `./setup_benchmark.sh --source ...`
3. Test: `./benchmark_renderer.sh --preset quick`
4. Profile: `./benchmark_renderer.sh --profile --preset quick`
5. Compare: `./compare_benchmarks.py before.json after.json`
