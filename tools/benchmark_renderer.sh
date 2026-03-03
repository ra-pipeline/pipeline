#!/bin/bash
# Wrapper script for weblog renderer benchmarking
# Provides convenient CLI interface with common presets

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCHMARK_SCRIPT="${SCRIPT_DIR}/benchmark_renderer.py"
DEFAULT_RUNS=10
TEST_DIR="$(pwd)"
DEFAULT_OUTPUT_DIR="${TEST_DIR}/benchmark_results"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

usage() {
    cat << EOF
Weblog Renderer Benchmark Tool

Usage: $0 [OPTIONS]

OPTIONS:
    -c, --context PATH          Path to pickled context file (required if --report-dir not set)
    -r, --report-dir PATH       Path to weblog report directory (alt. to --context)
    -n, --runs N                Number of benchmark runs (default: $DEFAULT_RUNS)
    -w, --warmup N              Number of warmup runs to discard (default: 1)
    --verify                    Run each renderer once to verify setup (fast sanity check)
    -s, --single RENDERER       Benchmark single renderer by name
    -o, --output FILE           Output JSON file (default: results_<timestamp>.json)
    -d, --output-dir DIR        Output directory (default: $DEFAULT_OUTPUT_DIR)
    --reset-cache               Reset renderer caches between runs
    --skip-origin-files         Disable origin file checks to prevent caching from
                                previously computed plots (enables consistent timing)
    --preserve-metadata          Preserve metadata across runs for reuse speedup measurement
    --metadata-dir DIR           Directory to store shared metadata (default: temp dir)
    --list                      List all available renderers and exit
    --profile                   Run with profiling (cProfile)
    --preset PRESET             Use preset configuration:
                                  quick    - 3 runs, just a few key renderers
                                  standard - 5 runs, all renderers
                                  thorough - 20 runs, all renderers
    -h, --help                  Show this help message

EXAMPLES:
    # Quick benchmark of all renderers
    $0 -c /path/to/context.pickle --preset quick

    # Thorough benchmark with custom runs
    $0 -c /path/to/context.pickle -n 20 -d ./my_results

    # Benchmark single renderer
    $0 -c /path/to/context.pickle -s T1_1Renderer -n 10

    # Use report directory
    $0 -r /path/to/weblog/output --preset standard

    # Benchmark with skip-origin-files to get consistent timing
    $0 -c /path/to/context.pickle --skip-origin-files -n 12

    # List available renderers
    $0 --list

EOF
    exit 1
}

# Parse preset configurations
apply_preset() {
    local preset=$1
    case "$preset" in
        quick)
            runs=3
            renderers="T1_1Renderer T1_2Renderer T2_1Renderer T2_4MRenderer"
            ;;
        standard)
            runs=5
            renderers=""  # All
            ;;
        thorough)
            runs=10
            renderers=""  # All
            ;;
        *)
            echo -e "${RED}Unknown preset: $preset${NC}"
            exit 1
            ;;
    esac
}

# Initialize variables
context_path=""
report_dir=""
runs=$DEFAULT_RUNS
warmup=1
verify=""
single_renderer=""
output_file=""
output_dir=$DEFAULT_OUTPUT_DIR
reset_cache=""
list_renderers=""
use_profile=""
renderers=""
preserve_metadata=""
metadata_dir=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -c|--context)
            context_path="$2"
            shift 2
            ;;
        -r|--report-dir)
            report_dir="$2"
            shift 2
            ;;
        -n|--runs)
            runs="$2"
            shift 2
            ;;
        -w|--warmup)
            warmup="$2"
            shift 2
            ;;
        --verify)
            verify="--verify"
            shift
            ;;
        -s|--single)
            single_renderer="$2"
            shift 2
            ;;
        -o|--output)
            output_file="$2"
            shift 2
            ;;
        -d|--output-dir)
            output_dir="$2"
            shift 2
            ;;
        --reset-cache)
            reset_cache="--reset-cache"
            shift
            ;;
        --skip-origin-files)
            skip_origin_files="--skip-origin-files"
            shift
            ;;
        --preserve-metadata)
            preserve_metadata="--preserve-metadata"
            shift
            ;;
        --metadata-dir)
            metadata_dir="$2"
            shift 2
            ;;
        --list)
            list_renderers="--list-renderers"
            shift
            ;;
        --profile)
            use_profile=1
            shift
            ;;
        --preset)
            preset="$2"
            apply_preset "$preset"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            usage
            ;;
    esac
done

# Validate inputs
if [[ -n "$list_renderers" ]]; then
    python3 "$BENCHMARK_SCRIPT" $list_renderers
    exit 0
fi

if [[ -z "$context_path" && -z "$report_dir" ]]; then
    echo -e "${RED}Error: Either --context or --report-dir must be specified${NC}"
    usage
fi

if [[ -n "$context_path" && ! -f "$context_path" ]]; then
    echo -e "${RED}Error: Context file not found: $context_path${NC}"
    exit 1
fi

if [[ -n "$report_dir" && ! -d "$report_dir" ]]; then
    echo -e "${RED}Error: Report directory not found: $report_dir${NC}"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 not found in PATH${NC}"
    exit 1
fi

# Create output directory if needed
mkdir -p "$output_dir"

# Generate output filename if not specified
if [[ -z "$output_file" ]]; then
    timestamp=$(date +%Y%m%d_%H%M%S)
    output_file="${output_dir}/benchmark_${timestamp}.json"
fi

# Build python command
cmd=("python3" "$BENCHMARK_SCRIPT")

if [[ -n "$context_path" ]]; then
    cmd+=(--context "$context_path")
fi

if [[ -n "$report_dir" ]]; then
    cmd+=(--report-dir "$report_dir")
fi

cmd+=(--runs "$runs")
cmd+=(--warmup "$warmup")

if [[ -n "$verify" ]]; then
    cmd+=($verify)
fi

cmd+=(--output "$output_file")

if [[ -n "$single_renderer" ]]; then
    cmd+=(--single "$single_renderer")
fi

if [[ -n "$renderers" ]]; then
    cmd+=(--renderers $renderers)
fi

if [[ -n "$reset_cache" ]]; then
    cmd+=($reset_cache)
fi

if [[ -n "$skip_origin_files" ]]; then
    cmd+=($skip_origin_files)
fi

if [[ -n "$preserve_metadata" ]]; then
    cmd+=($preserve_metadata)
fi

if [[ -n "$metadata_dir" ]]; then
    cmd+=(--metadata-dir "$metadata_dir")
fi

# Prevent accidental double runs
lock_file="${output_file}.lock"
if [[ -f "$lock_file" ]]; then
    echo -e "${RED}Error: lock file exists ($lock_file). Another run may be in progress.${NC}"
    exit 1
fi
trap 'rm -f "$lock_file"' EXIT
echo $$ > "$lock_file"

# Run benchmark with optional profiling
echo -e "${YELLOW}Starting benchmark...${NC}"
echo "  Runs: $runs"
echo "  Output: $output_file"
if [[ -n "$single_renderer" ]]; then
    echo "  Renderer: $single_renderer"
fi
echo ""

if [[ -n "$use_profile" ]]; then
    profile_file="${output_dir}/profile_${timestamp}.prof"
    echo -e "${YELLOW}Running with profiling (output: $profile_file)${NC}"
    python3 -m cProfile -o "$profile_file" "${cmd[@]}"
    echo -e "${GREEN}Profile saved to: $profile_file${NC}"
    echo "  View with: python3 -m pstats $profile_file"
else
    "${cmd[@]}"
fi

echo -e "${GREEN}Benchmark complete!${NC}"
if [[ -f "$output_file" ]]; then
    echo -e "${GREEN}Results saved to: $output_file${NC}"
fi
