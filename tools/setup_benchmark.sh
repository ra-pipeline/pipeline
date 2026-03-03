#!/bin/bash
# Setup script for renderer benchmarking
# Helps prepare a testing environment with cached context

set -e

usage() {
    cat << EOF
Renderer Benchmark Setup Helper

Usage: $0 [OPTIONS]

OPTIONS:
    -s, --source DIR            Source full pipeline output directory
    -d, --dest DIR              Destination testing directory (default: ./weblog_bench_test)
    -c, --context FILE          Pickled context file to use
    --saved-state DIR           Directory containing context-stage*.pickle files
    -h, --help                  Show this help message

DESCRIPTION:
    This script helps set up a testing environment for renderer benchmarking.
    It can:
    1. Copy the entire weblog output directory for safe benchmarking
    2. Extract and prepare the pickled context for repeated testing
    3. Create a README with benchmark instructions

    This avoids interfering with production output and provides a clean
    snapshot for consistent benchmark runs.

EXAMPLES:
    # Copy full pipeline output to test directory
    $0 -s /output/path/weblog -d ./benchmark_test

    # Use existing context file
    $0 -c /path/to/context.pickle -d ./benchmark_test

    # Use saved_state directory with per-stage context pickles
    $0 --saved-state /output/path/saved_state -d ./benchmark_test

EOF
    exit 1
}

# Initialize
source_dir=""
dest_dir="./weblog_bench_test"
context_file=""
saved_state_dir=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -s|--source)
            source_dir="$2"
            shift 2
            ;;
        -d|--dest)
            dest_dir="$2"
            shift 2
            ;;
        -c|--context)
            context_file="$2"
            shift 2
            ;;
        --saved-state)
            saved_state_dir="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo "Unknown option: $1"
            usage
            ;;
    esac
done

# Validate
if [[ -z "$source_dir" && -z "$context_file" && -z "$saved_state_dir" ]]; then
    echo "Error: Either --source, --context, or --saved-state must be specified"
    usage
fi

if [[ -n "$source_dir" && ! -d "$source_dir" ]]; then
    echo "Error: Source directory not found: $source_dir"
    exit 1
fi

if [[ -n "$context_file" && ! -f "$context_file" ]]; then
    echo "Error: Context file not found: $context_file"
    exit 1
fi

if [[ -n "$saved_state_dir" && ! -d "$saved_state_dir" ]]; then
    echo "Error: Saved state directory not found: $saved_state_dir"
    exit 1
fi

# Create destination
echo "Creating test directory: $dest_dir"
mkdir -p "$dest_dir"

# Copy weblog if source provided
if [[ -n "$source_dir" ]]; then
    echo "Copying weblog output..."
    cp -r "$source_dir"/* "$dest_dir/"
    echo "✓ Copied weblog to $dest_dir"
fi

# Copy or locate context
if [[ -n "$context_file" ]]; then
    echo "Copying context file..."
    cp "$context_file" "$dest_dir/context.pickle"
    echo "✓ Copied context to $dest_dir/context.pickle"
else
    # Try to find context in source
    if [[ -f "$source_dir/context.pickle" ]]; then
        echo "✓ Found context in source"
        cp "$source_dir/context.pickle" "$dest_dir/context.pickle"
    elif [[ -f "$source_dir/../context.pickle" ]]; then
        echo "Found context in parent directory"
        cp "$source_dir/../context.pickle" "$dest_dir/context.pickle"
    else
        # Try to find latest per-stage context pickle
        search_dirs=()
        if [[ -n "$saved_state_dir" ]]; then
            search_dirs+=("$saved_state_dir")
        fi
        if [[ -n "$source_dir" ]]; then
            search_dirs+=("$source_dir" "$source_dir/..")
        fi

        latest_context=""
        latest_stage=-1
        for search_dir in "${search_dirs[@]}"; do
            while IFS= read -r context_path; do
                stage_num=$(basename "$context_path" | sed -E 's/.*context-stage([0-9]+)\.pickle/\1/')
                if [[ "$stage_num" =~ ^[0-9]+$ ]] && (( stage_num > latest_stage )); then
                    latest_stage=$stage_num
                    latest_context="$context_path"
                fi
            done < <(find "$search_dir" -type f -name 'context-stage*.pickle' 2>/dev/null)
        done

        if [[ -n "$latest_context" ]]; then
            echo "Found latest stage context: $latest_context"
            cp "$latest_context" "$dest_dir/context.pickle"
            echo "✓ Copied context to $dest_dir/context.pickle"
        else
            echo "Warning: Could not locate context.pickle"
            echo "Please ensure context.pickle is in the test directory"
        fi
    fi
fi

# Create README
cat > "$dest_dir/BENCHMARKING.md" << 'EOF'
# Renderer Benchmarking Guide

This directory contains a snapshot of weblog output suitable for benchmarking
renderer performance without running the full pipeline.

## Quick Start

```bash
# List available renderers
../benchmark_renderer.sh --list

# Quick benchmark (3 runs)
../benchmark_renderer.sh --report-dir . --preset quick

# Standard benchmark (5 runs, all renderers)
../benchmark_renderer.sh --report-dir . --preset standard

# Thorough benchmark (20 runs, all renderers)
../benchmark_renderer.sh --report-dir . --preset thorough

# Benchmark single renderer
../benchmark_renderer.sh --report-dir . --single T1_1Renderer -n 10
```

## Detailed Usage

### Using context file directly
```bash
../benchmark_renderer.sh --context context.pickle -n 10
```

### Using report directory
```bash
../benchmark_renderer.sh --report-dir . -n 10 -o results.json
```

### With profiling
```bash
../benchmark_renderer.sh --report-dir . --preset standard --profile
```

### Reset caches between runs
```bash
../benchmark_renderer.sh --report-dir . --reset-cache -n 10
```

## Understanding Results

The output JSON contains:
- **times**: Individual run times
- **mean**: Average execution time
- **median**: Median execution time (more robust to outliers)
- **stdev**: Standard deviation
- **min/max**: Best and worst times
- **runs**: Number of successful runs

## Tips for Accurate Benchmarking

1. **System Stability**: Stop other processes to reduce variance
   ```bash
   # On Linux, set CPU governor to performance
   echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
   ```

2. **Multiple Runs**: Use at least 5-10 runs for stable averages
   ```bash
   # Standard: 5 runs
   ../benchmark_renderer.sh --report-dir . --preset standard

   # Thorough: 20 runs for high-variance operations
   ../benchmark_renderer.sh --report-dir . --preset thorough
   ```

3. **Compare Results**: Save baseline and after-optimization results
   ```bash
   ../benchmark_renderer.sh --report-dir . -n 10 -o baseline.json
   # ... make optimizations ...
   ../benchmark_renderer.sh --report-dir . -n 10 -o optimized.json
   ```

4. **Profiling**: Use `--profile` flag to identify hotspots
   ```bash
   ../benchmark_renderer.sh --report-dir . --profile --preset quick
   ```

## Performance Notes

- Initial run may be slower (first-time imports, cache population)
- Consider discarding the first run in analysis
- Cache statistics printed at end of run (if available)
- T2_1Details and Sky plots have their own caching layers

## Comparing Before/After

```bash
# Run baseline
../benchmark_renderer.sh --report-dir . -n 10 -o baseline.json

# Make code changes...

# Run optimized version
../benchmark_renderer.sh --report-dir . -n 10 -o optimized.json

# Compare (requires Python)
python3 << 'PYSCRIPT'
import json

with open('baseline.json') as f:
    baseline = json.load(f)
with open('optimized.json') as f:
    optimized = json.load(f)

print("Comparison (optimized vs baseline):\n")
print(f"{'Renderer':<40} {'Before':>10} {'After':>10} {'Δ':>10} {'% Δ':>10}")
print("-" * 80)

for renderer, opt_stats in sorted(optimized.items()):
    if renderer not in baseline:
        continue
    base_mean = baseline[renderer]['mean']
    opt_mean = opt_stats['mean']
    delta = opt_mean - base_mean
    pct_delta = (delta / base_mean) * 100 if base_mean else 0

    print(f"{renderer:<40} {base_mean:>10.3f}s {opt_mean:>10.3f}s "
          f"{delta:>10.3f}s {pct_delta:>9.1f}%")

PYSCRIPT
```

## Directory Structure

```
weblog_bench_test/
├── BENCHMARKING.md           # This file
├── context.pickle            # Pickled context (loaded on each run)
├── t1-1.html                 # Cached output (regenerated by renderers)
├── resources/                # CSS, JS, images
├── session*/                 # Session-specific output
├── stage*/                   # Stage-specific output
└── benchmark_results/        # Generated benchmark results (JSON)
    ├── benchmark_20260204_120000.json
    └── benchmark_20260204_120100.json
```

## Troubleshooting

**Import Error**: Ensure the pipeline package is in PYTHONPATH
```bash
export PYTHONPATH=/path/to/pipeline:$PYTHONPATH
```

**Context not found**: Explicitly provide context path
```bash
../benchmark_renderer.sh --context /path/to/context.pickle -n 10
```

**No renderers found**: Check context was properly unpickled
```bash
python3 -c "import pickle; pickle.load(open('context.pickle', 'rb'))"
```

EOF

echo ""
echo "✓ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Review the BENCHMARKING.md file"
echo "  2. Run: cd $dest_dir"
echo "  3. Test: ../benchmark_renderer.sh --list"
echo "  4. Benchmark: ../benchmark_renderer.sh --report-dir . --preset quick"
