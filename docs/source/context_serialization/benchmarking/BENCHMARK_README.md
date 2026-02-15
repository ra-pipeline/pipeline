# Weblog Renderer Benchmarking Suite

Automated tools for benchmarking the weblog rendering performance without needing to run full 50+ minute pipeline executions.

## Overview

Running full pipeline executions (50+ mins each) to test renderer performance changes is impractical. This suite captures a "render-ready" context from a single pipeline run, then repeatedly tests the renderer in isolation with minimal overhead.

**Key benefits:**
- ⚡ **Fast iteration**: Each benchmark run takes seconds, not minutes
- 🎯 **Isolated testing**: Only benchmarks renderer code, not pipeline stages
- 📊 **Accurate statistics**: Capture variance across multiple runs
- 🔄 **Deterministic**: Uses cached context, eliminating stage dependencies
- 📈 **Comparison tools**: Before/after analysis with percentage deltas

## Quick Start

### 1. Set Up Testing Environment

If you have a full pipeline run output:

```bash
./setup_benchmark.sh --source /path/to/weblog/output --dest ./my_benchmark_test
cd ./my_benchmark_test
```

Or if you already have a pickled context:

```bash
./setup_benchmark.sh --context /path/to/context.pickle --dest ./my_benchmark_test
cd ./my_benchmark_test
```

### 2. List Available Renderers

```bash
../benchmark_renderer.sh --list
```

### 3. Run Benchmark

```bash
# Quick test (3 runs of key renderers)
../benchmark_renderer.sh --report-dir . --preset quick

# Standard test (5 runs of all renderers)
../benchmark_renderer.sh --report-dir . --preset standard

# Thorough test (20 runs of all renderers)
../benchmark_renderer.sh --report-dir . --preset thorough
```

### 4. Compare Before/After

```bash
# Get baseline
../benchmark_renderer.sh --report-dir . -n 10 -o baseline.json

# Make code optimizations...

# Test optimized version
../benchmark_renderer.sh --report-dir . -n 10 -o optimized.json

# Compare
../compare_benchmarks.py baseline.json optimized.json
```

## Scripts

### `benchmark_renderer.sh` - Main Benchmark Wrapper

Convenient bash interface with presets and common options.

```bash
./benchmark_renderer.sh [OPTIONS]

OPTIONS:
  -c, --context PATH           Path to pickled context file
  -r, --report-dir PATH        Path to weblog report directory
  -n, --runs N                 Number of runs (default: 5)
  -s, --single RENDERER        Benchmark single renderer
  -o, --output FILE            Output JSON file
  -d, --output-dir DIR         Output directory
  --reset-cache                Reset renderer caches between runs
  --preset {quick|standard|thorough}
  --profile                    Run with cProfile profiling
  --list                       List available renderers
  -h, --help                   Show help
```

**Examples:**

```bash
# Standard benchmark, all renderers
./benchmark_renderer.sh --report-dir ./weblog_test --preset standard

# Single renderer, 20 runs, with profiling
./benchmark_renderer.sh -r ./weblog_test -s T1_1Renderer -n 20 --profile

# With custom output
./benchmark_renderer.sh -r ./weblog_test -n 10 \
  -o ./results/run_20260204.json -d ./results
```

### `benchmark_renderer.py` - Core Python Script

Low-level Python script for direct control.

```bash
python benchmark_renderer.py [OPTIONS]

OPTIONS:
  --context PATH               Pickled context file (required if --report-dir not set)
  --report-dir PATH            Weblog directory (searches for context.pickle)
  --runs N                     Number of runs
  --renderers NAME [NAME ...]  Specific renderer names
  --single NAME                Single renderer by name
  --output FILE                Output JSON file
  --reset-cache                Reset caches between runs
  --list-renderers             List available renderers
```

**Examples:**

```bash
# All renderers, 10 runs
python benchmark_renderer.py --context context.pickle --runs 10 \
  --output results.json

# Multiple specific renderers
python benchmark_renderer.py --report-dir ./weblog \
  --renderers T1_1Renderer T1_2Renderer T2_1Renderer --runs 5

# Single renderer with cache reset
python benchmark_renderer.py -c context.pickle -s T2_4MRenderer \
  -n 20 --reset-cache --output t2_4m_bench.json
```

### `setup_benchmark.sh` - Environment Preparation

Prepares a clean testing directory with weblog snapshot and context.

```bash
./setup_benchmark.sh [OPTIONS]

OPTIONS:
  -s, --source DIR             Source weblog output directory
  -d, --dest DIR               Destination test directory
  -c, --context FILE           Pickled context file
  -h, --help                   Show help
```

**Examples:**

```bash
# Copy full weblog output
./setup_benchmark.sh --source /pipeline/output/weblog \
  --dest ./benchmark_test

# With explicit context
./setup_benchmark.sh --source /pipeline/output/weblog \
  --context /pipeline/output/context.pickle \
  --dest ./benchmark_test
```

### `compare_benchmarks.py` - Result Comparison

Compare before/after benchmark results.

```bash
python compare_benchmarks.py baseline.json optimized.json
python compare_benchmarks.py -b baseline.json -a optimized.json [OPTIONS]

OPTIONS:
  --csv                        Output as CSV
  --statistics                 Show detailed statistics
```

**Example output:**

```
======================================================================================
Renderer                                        Baseline    Optimized       Delta   % Change
======================================================================================
T1_1Renderer                                       5.234s       4.892s     -0.342s      -6.5%
T2_4MRenderer                                      12.156s      11.834s     -0.322s      -2.6%
T2_1DetailsRenderer                               28.442s      26.156s     -2.286s      -8.0%
...
TOTAL                                            156.234s     142.892s    -13.342s      -8.5%
======================================================================================

✓ IMPROVEMENT: 8.5% faster (13.34s saved)
```

## Workflow Example

### Complete Optimization Cycle

```bash
# 1. Prepare test environment
./setup_benchmark.sh -s /pipeline/output/weblog -d ./bench_test
cd bench_test

# 2. Get baseline measurements
../benchmark_renderer.sh --report-dir . --preset standard \
  -o ../baseline.json

# 3. Profile hotspots
../benchmark_renderer.sh --report-dir . -s T2_4MRenderer \
  --profile -n 3

# 4. Make optimizations to htmlrenderer.py

# 5. Test optimized version
../benchmark_renderer.sh --report-dir . --preset standard \
  -o ../optimized.json

# 6. Compare results
../compare_benchmarks.py ../baseline.json ../optimized.json

# 7. If improvement is good, verify with thorough test
../benchmark_renderer.sh --report-dir . --preset thorough \
  -o ../final_validation.json

# 8. Compare final vs baseline
../compare_benchmarks.py ../baseline.json ../final_validation.json
```

## Understanding Results

### JSON Output Format

```json
{
  "RendererName": {
    "times": [5.234, 5.189, 5.267, ...],
    "mean": 5.230,
    "median": 5.234,
    "stdev": 0.032,
    "min": 5.167,
    "max": 5.312,
    "runs": 10
  }
}
```

- **times**: Array of individual run times (in seconds)
- **mean**: Average of all runs
- **median**: Middle value (more robust to outliers)
- **stdev**: Standard deviation (lower = more consistent)
- **min/max**: Best and worst times
- **runs**: Number of successful runs

### Interpreting Statistics

- **Median vs Mean**: If very different, indicates some runs are much slower (investigate variance)
- **StDev**: 
  - < 2% of mean: Very consistent, can trust results
  - 2-5% of mean: Acceptable variance
  - \> 5% of mean: High variance, consider more runs or system tuning

## Best Practices

### 1. Minimize System Variance

Before running benchmarks, reduce background noise:

```bash
# Linux: Set CPU governor to performance
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Optional: Increase priority
nice -n -10 ../benchmark_renderer.sh --report-dir . --preset standard

# Monitor system load
watch -n 1 'cat /proc/loadavg; uptime'
```

### 2. Determine Number of Runs

- **Quick development test**: 3 runs (preset: `quick`)
- **Standard validation**: 5-10 runs (preset: `standard`)
- **Publication-quality**: 20+ runs (preset: `thorough`)

Rule of thumb: Run until coefficient of variation (stdev/mean) < 2%

```bash
# Calculate variance
python3 << 'EOF'
import json
with open('result.json') as f:
    data = json.load(f)
for name, stats in data.items():
    cv = stats['stdev'] / stats['mean'] * 100
    print(f'{name}: CV = {cv:.1f}%')
EOF
```

### 3. Validate Results

Always sanity-check before/after:

```bash
# Check individual run times (outliers indicate variance)
python3 << 'EOF'
import json
with open('result.json') as f:
    data = json.load(f)
for name, stats in sorted(data.items()):
    print(f'{name}:')
    print(f'  Times: {[f"{t:.3f}" for t in stats["times"]]}')
    print(f'  Mean:  {stats["mean"]:.3f}s')
EOF
```

### 4. Profiling for Optimization

Use `--profile` flag to identify hotspots:

```bash
# Run with profiling
./benchmark_renderer.sh --report-dir . -s T2_4MRenderer \
  --profile -n 3

# Analyze profile
python3 -m pstats profile_20260204_120000.prof
```

### 5. Staging Tests

Test incrementally:

```bash
# Stage 1: Quick check
./benchmark_renderer.sh -r . --preset quick -o test1.json

# Stage 2: If promising, standard test
./benchmark_renderer.sh -r . --preset standard -o test2.json

# Stage 3: If good, thorough test
./benchmark_renderer.sh -r . --preset thorough -o test3.json
```

## Troubleshooting

### "Context file not found"

Ensure context.pickle exists in test directory or provide explicit path:

```bash
# Option 1: Copy context to test directory
cp /pipeline/output/context.pickle ./weblog_test/

# Option 2: Provide explicit path
./benchmark_renderer.sh --context /full/path/to/context.pickle -n 10
```

### "No renderers matched"

List available renderers:

```bash
./benchmark_renderer.sh --list
```

### High variance in results

```bash
# 1. Stop other processes
sudo killall firefox chrome python  # as appropriate

# 2. Increase run count
./benchmark_renderer.sh -r . -n 20 -o results.json

# 3. Run again with system tuning
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
./benchmark_renderer.sh -r . -n 20 -o results_tuned.json
```

### Out of memory during rendering

```bash
# Benchmark single renderers instead of all at once
for renderer in T1_1Renderer T1_2Renderer T2_1Renderer; do
  ./benchmark_renderer.sh -r . -s $renderer -n 10 \
    -o results_$renderer.json
done
```

### PYTHONPATH issues

```bash
# Ensure pipeline package is accessible
export PYTHONPATH=/path/to/pipeline:$PYTHONPATH
./benchmark_renderer.sh --list
```

## Performance Tuning Tips

### Rendering-Specific Optimizations

1. **Cache plots**: Ensure plot caching is enabled
   ```python
   # In htmlrenderer.py - use renderer caches
   if hasattr(ms, '_t2_1_details_cache'):
       return ms._t2_1_details_cache
   ```

2. **Lazy loading**: Defer expensive operations
   ```python
   # Load data only when needed
   if renderer_name in renderers_to_run:
       load_expensive_data()
   ```

3. **Parallel rendering**: Consider multiprocessing for independent renderers
   ```python
   # Renderers that don't share state can run in parallel
   with multiprocessing.Pool() as pool:
       results = pool.map(renderer.render, [context] * num_runs)
   ```

### Profiling Results

Common hotspots:
- **Plotting**: Sky/weather plots (use caching)
- **Unpickling**: Use lazy loading with proxies
- **Template rendering**: Cache template compilation
- **I/O**: Use buffered writes

## Integration with CI/CD

Add to CI pipeline for performance regression detection:

```yaml
# Example GitHub Actions
- name: Benchmark renderers
  run: |
    ./benchmark_renderer.sh -r weblog_test --preset standard \
      -o benchmark_result.json
    
- name: Compare with baseline
  run: |
    python compare_benchmarks.py \
      baseline_benchmark.json benchmark_result.json > comparison.txt
    
- name: Check for regressions
  run: |
    python check_regression.py comparison.txt --threshold 5  # 5% regression
```

## File Structure

```
context-serializer/
├── benchmark_renderer.sh          # Main bash wrapper
├── benchmark_renderer.py           # Core Python script
├── setup_benchmark.sh              # Environment setup
├── compare_benchmarks.py           # Result comparison
└── benchmark_results/              # Generated results (auto-created)
    ├── benchmark_20260204_100000.json
    └── benchmark_20260204_101500.json

weblog_bench_test/                  # Test directory (created by setup_benchmark.sh)
├── BENCHMARKING.md                 # Instructions
├── context.pickle                  # Pickled context (loaded each run)
├── benchmark_results/              # Generated results
│   ├── baseline.json
│   └── optimized.json
├── t1-1.html                       # Cached weblog output
└── resources/                      # CSS, JS, images
```

## Advanced Usage

### Continuous Integration

```bash
# Save historical benchmark data
./benchmark_renderer.sh -r . --preset standard \
  -o "benchmark_$(date +%Y%m%d_%H%M%S).json"

# Track performance over time
python analyze_trends.py benchmark_*.json
```

### Custom Profiling

```bash
# Get full cProfile stats
python benchmark_renderer.py --context context.pickle --runs 1 \
  --single T2_4MRenderer | python -m cProfile -s cumulative
```

### Memory Analysis

```bash
# Run with memory profiling
python -m memory_profiler benchmark_renderer.py \
  --context context.pickle --single T2_1DetailsRenderer
```

## Contributing

To add new benchmarking features:

1. Modify `benchmark_renderer.py` for core functionality
2. Update `benchmark_renderer.sh` for CLI interface
3. Test with: `./benchmark_renderer.sh --preset quick`

## See Also

- [Pipeline Infrastructure Documentation](../infrastructure/)
- [Htmlrenderer Source](htmlrenderer.py)
- [Performance Profiling Guide](../docs/performance.md)
