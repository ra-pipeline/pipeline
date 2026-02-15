#!/usr/bin/env python3
"""
Verification script to demonstrate that the --skip-origin-files flag fixes
the alternating benchmark timing pattern.

This script compares benchmark results with and without the flag.
"""

import json
import subprocess
import sys
from pathlib import Path

def run_benchmark(report_dir, use_skip_origin_files=False, num_runs=6):
    """Run a benchmark and return the timing results."""
    cmd = [
        'python',
        'benchmark_renderer.py',
        '--report-dir', report_dir,
        '--single', 'T2_1DetailsRenderer',
        '--runs', str(num_runs),
    ]
    
    if use_skip_origin_files:
        cmd.append('--skip-origin-files')
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Parse timing results from stderr
    times = []
    for line in result.stderr.split('\n'):
        if '[TIMING] SpwIdVsFreqChart took' in line:
            try:
                timing = float(line.split('took ')[1].split('s')[0])
                times.append(timing)
            except (ValueError, IndexError):
                pass
    
    return times

def analyze_times(times, label):
    """Analyze and display timing statistics."""
    if not times:
        print(f"\n{label}: No data collected")
        return
    
    mean = sum(times) / len(times)
    variance = sum((t - mean) ** 2 for t in times) / len(times)
    stdev = variance ** 0.5
    alternating = all(
        (times[i] > 70 and times[i+1] < 1) or 
        (times[i] < 1 and times[i+1] > 70)
        for i in range(len(times) - 1)
    )
    
    print(f"\n{label}")
    print(f"  Times: {[f'{t:.2f}s' for t in times]}")
    print(f"  Mean: {mean:.2f}s")
    print(f"  StDev: {stdev:.2f}s")
    print(f"  Min/Max: {min(times):.2f}s / {max(times):.2f}s")
    print(f"  Alternating pattern detected: {alternating}")

def main():
    """Run verification."""
    if len(sys.argv) > 1:
        report_dir = sys.argv[1]
    else:
        report_dir = '.'
    
    print("=" * 70)
    print("Benchmark Timing Verification")
    print("=" * 70)
    
    print("\nPhase 1: Running WITHOUT --skip-origin-files (should show alternating pattern)")
    print("-" * 70)
    times_without = run_benchmark(report_dir, use_skip_origin_files=False, num_runs=6)
    analyze_times(times_without, "WITHOUT --skip-origin-files")
    
    print("\n\nPhase 2: Running WITH --skip-origin-files (should show consistent timing)")
    print("-" * 70)
    times_with = run_benchmark(report_dir, use_skip_origin_files=True, num_runs=6)
    analyze_times(times_with, "WITH --skip-origin-files")
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    # Check if fix is working
    without_alternating = all(
        (times_without[i] > 70 and times_without[i+1] < 1) or 
        (times_without[i] < 1 and times_without[i+1] > 70)
        for i in range(len(times_without) - 1)
    ) if len(times_without) > 1 else False
    
    with_stdev = (sum((t - sum(times_with)/len(times_with)) ** 2 
                      for t in times_with) / len(times_with)) ** 0.5 if times_with else float('inf')
    with_consistent = with_stdev < 5.0
    
    print(f"\n✓ Without flag - Alternating pattern: {without_alternating}")
    print(f"✓ With flag - Consistent timing (stdev < 5s): {with_consistent}")
    
    if without_alternating and with_consistent:
        print("\n✅ FIX VERIFIED: --skip-origin-files successfully eliminates alternating pattern!")
        return 0
    else:
        print("\n⚠️  RESULTS UNEXPECTED - Please check logs above")
        return 1

if __name__ == '__main__':
    sys.exit(main())
