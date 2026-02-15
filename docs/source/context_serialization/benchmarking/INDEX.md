# Benchmarking Suite - File Index

## Quick Navigation

### 📌 START HERE
- **[README_BENCHMARKING.md](README_BENCHMARKING.md)** - Complete overview & quick start

### 🔧 Scripts (Executable)

| File | Purpose | Usage |
|------|---------|-------|
| [benchmark_renderer.sh](benchmark_renderer.sh) | Main CLI wrapper | `./benchmark_renderer.sh -r . --preset standard` |
| [benchmark_renderer.py](benchmark_renderer.py) | Core Python engine | `python benchmark_renderer.py --context context.pickle` |
| [setup_benchmark.sh](setup_benchmark.sh) | Environment preparation | `./setup_benchmark.sh --source /weblog --dest ./test` |
| [compare_benchmarks.py](compare_benchmarks.py) | Result comparison | `./compare_benchmarks.py baseline.json optimized.json` |

### 📚 Documentation

| File | Best For | Length | Key Topics |
|------|----------|--------|------------|
| [README_BENCHMARKING.md](README_BENCHMARKING.md) | Getting started | 2 pages | Overview, quick start, examples |
| [BENCHMARK_QUICK_REFERENCE.md](BENCHMARK_QUICK_REFERENCE.md) | Daily use | 1 page | Commands, presets, troubleshooting |
| [BENCHMARK_README.md](BENCHMARK_README.md) | Deep reference | 15+ pages | Complete guide, best practices, CI/CD |
| [BENCHMARK_SETUP_COMPLETE.md](BENCHMARK_SETUP_COMPLETE.md) | Technical details | 5 pages | Architecture, features, advanced usage |

## Use Cases → Documentation

**"I just want to run a quick test"**
→ [BENCHMARK_QUICK_REFERENCE.md](BENCHMARK_QUICK_REFERENCE.md)

**"I'm new to the system"**
→ [README_BENCHMARKING.md](README_BENCHMARKING.md)

**"I need comprehensive reference with examples"**
→ [BENCHMARK_README.md](BENCHMARK_README.md)

**"I want to understand the architecture"**
→ [BENCHMARK_SETUP_COMPLETE.md](BENCHMARK_SETUP_COMPLETE.md)

**"I need help with specific problem"**
→ [BENCHMARK_README.md - Troubleshooting section](BENCHMARK_README.md#troubleshooting)

## File Purposes

### Scripts

**`benchmark_renderer.sh`** - Main interface
- Bash wrapper around Python script
- Convenient CLI with presets
- Recommended for most users
- Features: `--preset`, `--list`, `--profile`

**`benchmark_renderer.py`** - Core engine
- Loads context, runs renderers repeatedly
- Collects timing statistics
- Outputs JSON results
- Use when: Need programmatic access

**`setup_benchmark.sh`** - Environment prep
- Copies weblog output + context to test directory
- Creates isolated test environment
- Generates BENCHMARKING.md in test dir
- Run once: `./setup_benchmark.sh --source ... --dest ...`

**`compare_benchmarks.py`** - Result analysis
- Loads two JSON result files
- Calculates deltas and percentage changes
- Displays improvement/regression
- Generates comparison table

### Documentation

**`README_BENCHMARKING.md`** - Main entry point
- Quick start (5 minutes)
- Feature overview
- Common workflows
- 2 pages, easy read

**`BENCHMARK_QUICK_REFERENCE.md`** - Command cheat sheet
- Common commands table
- Preset descriptions
- Quick troubleshooting
- One page reference

**`BENCHMARK_README.md`** - Comprehensive guide
- Detailed workflow examples
- Best practices
- System optimization tips
- Performance tuning
- CI/CD integration
- Troubleshooting with solutions
- 15+ pages, complete reference

**`BENCHMARK_SETUP_COMPLETE.md`** - Setup overview
- What was created
- Key capabilities
- Architecture overview
- Performance expectations
- 5 pages, technical details

## Quick Command Reference

```bash
# Setup (one-time)
./setup_benchmark.sh --source /weblog --dest ./test_dir

# Run benchmark
./benchmark_renderer.sh -r ./test_dir --preset standard -o results.json

# Compare results
./compare_benchmarks.py baseline.json optimized.json

# Get help
./benchmark_renderer.sh --help
```

## Directory Structure

```
context-serializer/
├── INDEX.md                        ← You are here
├── README_BENCHMARKING.md          ← Start here
├── BENCHMARK_SETUP_COMPLETE.md
├── BENCHMARK_README.md
├── BENCHMARK_QUICK_REFERENCE.md
│
├── benchmark_renderer.sh           ← Executable script
├── benchmark_renderer.py           ← Python script
├── setup_benchmark.sh              ← Executable script
└── compare_benchmarks.py           ← Python script

test_directory/                     ← Created by setup_benchmark.sh
├── BENCHMARKING.md
├── context.pickle
├── benchmark_results/
│   ├── baseline.json
│   └── optimized.json
└── [weblog output files]
```

## Common Workflows

### 1. First Time Setup
1. Read: [README_BENCHMARKING.md](README_BENCHMARKING.md)
2. Run: `./setup_benchmark.sh --source ... --dest ...`
3. Test: `./benchmark_renderer.sh -r . --preset quick`

### 2. Daily Development
1. Quick test: `./benchmark_renderer.sh -r . --preset quick`
2. Make changes
3. Retest and compare

### 3. Publication-Ready Results
1. Baseline: `./benchmark_renderer.sh -r . --preset thorough -o baseline.json`
2. Optimize code
3. Final test: `./benchmark_renderer.sh -r . --preset thorough -o final.json`
4. Compare: `./compare_benchmarks.py baseline.json final.json`

## Key Features Summary

| Feature | Script | Doc |
|---------|--------|-----|
| Quick preset | `benchmark_renderer.sh` | QUICK_REFERENCE |
| Profiling | `benchmark_renderer.sh --profile` | README |
| Single renderer | `benchmark_renderer.sh -s Name` | QUICK_REFERENCE |
| Custom runs | `benchmark_renderer.sh -n N` | README |
| Comparison | `compare_benchmarks.py` | README |
| Statistical analysis | JSON output + README | README |
| CI/CD integration | All scripts | README |

## Performance Expectations

- **Quick test** (3 runs): ~1 minute
- **Standard test** (5 runs): ~3 minutes
- **Thorough test** (20 runs): ~15 minutes
- **Full pipeline**: 50+ minutes

**Savings**: 35-90 minutes per optimization cycle!

## Support & Troubleshooting

| Issue | Reference |
|-------|-----------|
| General questions | README_BENCHMARKING.md |
| Command syntax | BENCHMARK_QUICK_REFERENCE.md |
| Complex workflows | BENCHMARK_README.md |
| Error messages | BENCHMARK_README.md - Troubleshooting |
| Python help | `python benchmark_renderer.py --help` |
| Bash help | `./benchmark_renderer.sh --help` |

---

**Last Updated**: February 4, 2026
**Status**: ✅ Production Ready
**Total Scripts**: 4 (all validated)
**Total Docs**: 4 (50+ pages)
