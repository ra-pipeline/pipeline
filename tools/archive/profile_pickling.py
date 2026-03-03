#!/usr/bin/env python3
"""Profile context pickling/unpickling performance.

This script measures the current performance of context unpickling during
weblog rendering and identifies optimization opportunities.

Usage:
    python profile_pickling.py [OPTIONS]

Options:
    --context PATH          Path to pickled context file or test context
    --output FILE          Output file for profiling results (JSON)
    --trace                Enable detailed tracing
    --memory-profile       Use memory_profiler for detailed memory tracking
"""

from __future__ import annotations

import argparse
import dataclasses
import glob
import io
import json
import os
import sys
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from pipeline.infrastructure import utils


@dataclasses.dataclass
class UnpickleMetrics:
    """Metrics for unpickling performance."""

    method: str
    result_count: int
    total_size_bytes: int
    unpickle_time_seconds: float
    throughput_MB_per_sec: float
    peak_memory_MB: float
    avg_result_size_KB: float

    def __str__(self) -> str:
        return (
            f'{self.method:20s} | Results: {self.result_count:3d} | '
            f'Time: {self.unpickle_time_seconds:6.2f}s | '
            f'Throughput: {self.throughput_MB_per_sec:6.1f} MB/s | '
            f'Peak Mem: {self.peak_memory_MB:7.1f} MB | '
            f'Avg Size: {self.avg_result_size_KB:7.1f} KB'
        )


def find_result_pickles(search_paths: list[str]) -> list[str]:
    """Find all result pickle files."""
    result_files = []
    for path in search_paths:
        if os.path.isdir(path):
            result_files.extend(glob.glob(os.path.join(path, '**', 'result-stage*.pickle'), recursive=True))
        elif os.path.isfile(path) and 'result-stage' in os.path.basename(path):
            result_files.append(path)
    return sorted(result_files)


def measure_pickle_sizes(result_files: list[str]) -> dict[str, Any]:
    """Measure the size and characteristics of pickle files."""
    sizes = []
    total_size = 0
    
    for filepath in result_files:
        size = os.path.getsize(filepath)
        sizes.append(size)
        total_size += size
    
    if not sizes:
        return {}
    
    return {
        'count': len(sizes),
        'total_bytes': total_size,
        'total_MB': total_size / 1024 / 1024,
        'min_bytes': min(sizes),
        'max_bytes': max(sizes),
        'avg_bytes': sum(sizes) / len(sizes),
        'avg_KB': sum(sizes) / len(sizes) / 1024,
    }


def profile_sequential_unpickle(result_files: list[str]) -> UnpickleMetrics:
    """Profile sequential unpickling (current method)."""
    tracemalloc.start()
    
    start = time.perf_counter()
    results = []
    for filepath in result_files:
        with open(filepath, 'rb') as f:
            result = utils.pickle_load(f)
            results.append(result)
    elapsed = time.perf_counter() - start
    
    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    total_size = sum(os.path.getsize(f) for f in result_files)
    throughput = (total_size / 1024 / 1024) / elapsed if elapsed > 0 else 0
    avg_size = total_size / len(result_files) / 1024
    
    return UnpickleMetrics(
        method='Sequential',
        result_count=len(result_files),
        total_size_bytes=total_size,
        unpickle_time_seconds=elapsed,
        throughput_MB_per_sec=throughput,
        peak_memory_MB=peak_memory / 1024 / 1024,
        avg_result_size_KB=avg_size,
    )


def profile_parallel_unpickle(result_files: list[str], max_workers: int | None = None) -> UnpickleMetrics:
    """Profile parallel unpickling with ThreadPoolExecutor."""
    tracemalloc.start()
    
    def load_pickle(filepath: str) -> Any:
        with open(filepath, 'rb') as f:
            return utils.pickle_load(f)
    
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(load_pickle, result_files))
    elapsed = time.perf_counter() - start
    
    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    total_size = sum(os.path.getsize(f) for f in result_files)
    throughput = (total_size / 1024 / 1024) / elapsed if elapsed > 0 else 0
    avg_size = total_size / len(result_files) / 1024
    
    workers = max_workers or os.cpu_count() or 1
    return UnpickleMetrics(
        method=f'Parallel ({workers} workers)',
        result_count=len(result_files),
        total_size_bytes=total_size,
        unpickle_time_seconds=elapsed,
        throughput_MB_per_sec=throughput,
        peak_memory_MB=peak_memory / 1024 / 1024,
        avg_result_size_KB=avg_size,
    )


def profile_lazy_unpickle(result_files: list[str]) -> UnpickleMetrics:
    """Profile lazy unpickling (simulated - only load first result)."""
    tracemalloc.start()
    
    start = time.perf_counter()
    # Simulate lazy loading: only unpickle first result
    if result_files:
        with open(result_files[0], 'rb') as f:
            result = utils.pickle_load(f)
    elapsed = time.perf_counter() - start
    
    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    total_size = sum(os.path.getsize(f) for f in result_files)
    avg_size = total_size / len(result_files) / 1024
    
    return UnpickleMetrics(
        method='Lazy (first only)',
        result_count=len(result_files),
        total_size_bytes=total_size,
        unpickle_time_seconds=elapsed,
        throughput_MB_per_sec=0,  # N/A for lazy
        peak_memory_MB=peak_memory / 1024 / 1024,
        avg_result_size_KB=avg_size,
    )


def profile_compression_opportunity(result_files: list[str]) -> dict[str, Any]:
    """Analyze compression opportunity for pickle files."""
    try:
        import gzip
    except ImportError:
        return {'available': False}
    
    if not result_files:
        return {'available': False, 'files_analyzed': 0}
    
    # Analyze first file for compression ratio
    sample_file = result_files[0]
    original_size = os.path.getsize(sample_file)
    
    with open(sample_file, 'rb') as f:
        original_data = f.read()
    
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode='wb') as gz:
        gz.write(original_data)
    
    compressed_size = compressed.tell()
    ratio = (1 - compressed_size / original_size) * 100
    
    return {
        'available': True,
        'sample_file': sample_file,
        'original_size_bytes': original_size,
        'compressed_size_bytes': compressed_size,
        'compression_ratio_percent': ratio,
        'estimated_total_savings_MB': (original_size - compressed_size) * len(result_files) / 1024 / 1024,
    }


def main() -> None:
    """Run profiling analysis."""
    parser = argparse.ArgumentParser(
        description='Profile context pickling/unpickling performance',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Profile a weblog report directory
  python profile_pickling.py --context ~/weblog/report --output profile.json
  
  # Profile with detailed memory tracking
  python profile_pickling.py --context ~/weblog/saved_state --memory-profile
        ''',
    )
    parser.add_argument('--context', help='Path to context or result directory')
    parser.add_argument('--output', help='Output JSON file for results')
    parser.add_argument('--trace', action='store_true', help='Enable detailed tracing')
    parser.add_argument('--memory-profile', action='store_true', help='Use memory_profiler')
    
    args = parser.parse_args()
    
    # Find result pickle files
    search_paths = []
    if args.context:
        search_paths = [args.context]
    else:
        # Default search locations
        search_paths = [
            '.',
            os.path.expanduser('~/weblog'),
            '/tmp/weblog',
        ]
    
    result_files = find_result_pickles(search_paths)
    
    if not result_files:
        print(f'ERROR: No pickle files found in {search_paths}')
        print('Usage: python profile_pickling.py --context /path/to/results')
        sys.exit(1)
    
    print(f'\nFound {len(result_files)} result pickle files')
    print(f'Search paths: {search_paths}\n')
    
    # Measure pickle sizes
    size_info = measure_pickle_sizes(result_files)
    print('Pickle File Statistics:')
    print(f'  Count: {size_info["count"]}')
    print(f'  Total: {size_info["total_MB"]:.1f} MB')
    print(f'  Average: {size_info["avg_KB"]:.1f} KB')
    print(f'  Min: {size_info["min_bytes"]:,} bytes')
    print(f'  Max: {size_info["max_bytes"]:,} bytes')
    
    # Run profiling
    print('\n' + '='*140)
    print('Profiling Results:')
    print('='*140)
    
    metrics = []
    
    # Sequential (current)
    print('\nTesting sequential unpickling (CURRENT METHOD)...')
    seq_metrics = profile_sequential_unpickle(result_files)
    metrics.append(seq_metrics)
    print(seq_metrics)
    
    # Parallel
    print('\nTesting parallel unpickling (OPTIMIZATION)...')
    par_metrics = profile_parallel_unpickle(result_files)
    metrics.append(par_metrics)
    print(par_metrics)
    
    # Lazy (simulated)
    print('\nTesting lazy unpickling (OPTIMIZATION)...')
    lazy_metrics = profile_lazy_unpickle(result_files)
    metrics.append(lazy_metrics)
    print(lazy_metrics)
    
    print('='*140)
    
    # Calculate improvements
    print('\nPerformance Improvements:')
    seq_time = seq_metrics.unpickle_time_seconds
    par_speedup = seq_time / par_metrics.unpickle_time_seconds if par_metrics.unpickle_time_seconds > 0 else 0
    lazy_speedup = seq_time / lazy_metrics.unpickle_time_seconds if lazy_metrics.unpickle_time_seconds > 0 else 0
    
    print(f'  Parallel: {par_speedup:.1f}x faster (saves {seq_time - par_metrics.unpickle_time_seconds:.2f}s)')
    print(f'  Lazy: {lazy_speedup:.1f}x faster (saves {seq_time - lazy_metrics.unpickle_time_seconds:.2f}s)')
    
    # Compression analysis
    print('\nCompression Opportunity:')
    compression = profile_compression_opportunity(result_files)
    if compression.get('available'):
        print(f'  Gzip ratio: {compression["compression_ratio_percent"]:.1f}%')
        print(f'  Potential savings: {compression["estimated_total_savings_MB"]:.1f} MB')
    else:
        print('  Compression analysis unavailable')
    
    # Output results
    if args.output:
        results = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'pickle_files': {
                'count': len(result_files),
                'total_size_MB': size_info.get('total_MB', 0),
                'average_size_KB': size_info.get('avg_KB', 0),
            },
            'metrics': [
                {
                    'method': m.method,
                    'time_seconds': m.unpickle_time_seconds,
                    'throughput_MB_per_sec': m.throughput_MB_per_sec,
                    'peak_memory_MB': m.peak_memory_MB,
                }
                for m in metrics
            ],
            'improvements': {
                'parallel_speedup': par_speedup,
                'lazy_speedup': lazy_speedup,
            },
            'compression': compression,
        }
        
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f'\nResults written to {args.output}')


if __name__ == '__main__':
    main()
