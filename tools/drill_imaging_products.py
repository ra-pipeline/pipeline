#!/usr/bin/env python3
"""
Drill into imaging product size differences to identify where 700 MB savings come from.

Compares benchmark vs optimized directory to categorize size changes by:
- Imaging stage (s23, s25, s32, s34, s36, etc.)
- Processing type (findcont, regcal, selfcal, cube, etc.)
- File type (image, residual, psf, pb, mask, model, etc.)
"""

import subprocess
import sys
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class FileInfo:
    path: str
    size_bytes: int
    
    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)


def parse_du_output(basedir: str) -> dict[str, int]:
    """Get file sizes from du command."""
    result = {}
    try:
        cmd = ['du', '-b', '-a', basedir]
        output = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if output.returncode == 0:
            for line in output.stdout.strip().split('\n'):
                if not line:
                    continue
                parts = line.split('\t', 1)
                if len(parts) == 2:
                    try:
                        size = int(parts[0])
                        path = parts[1]
                        # Only keep files (not directories)
                        if size > 0 and '.' in Path(path).name:
                            result[path] = size
                    except (ValueError, IndexError):
                        pass
    except Exception as e:
        print(f'Error parsing du output: {e}', file=sys.stderr)
    
    return result


def extract_stage(filename: str) -> str | None:
    """Extract stage number from filename (e.g., s23, s32, s45)."""
    parts = filename.split('.')
    for part in parts:
        if part.startswith('s') and len(part) > 1 and part[1:].split('_')[0].isdigit():
            return part.split('_')[0]  # e.g., 's23' from 's23_0'
    return None


def extract_processing_type(filename: str) -> str:
    """Extract processing type (findcont, regcal, selfcal, cube, etc.)."""
    filename_lower = filename.lower()
    
    for ptype in ['findcont', 'regcal', 'selfcal', 'cube', 'repbw']:
        if ptype in filename_lower:
            return ptype
    
    return 'other'


def extract_file_type(filename: str) -> str:
    """Extract file type (image, residual, psf, pb, mask, model, etc.)."""
    filename_lower = filename.lower()
    
    for ftype in ['image.pbcor', 'image', 'residual', 'psf', 'pb', 'mask', 
                  'model', 'sumwt', 'weight', 'cleanmask', 'alpha', 'mom']:
        if ftype in filename_lower:
            return ftype
    
    return 'other'


def format_bytes(b: int) -> str:
    """Format bytes as human-readable."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if abs(b) < 1024.0:
            return f'{b:.1f}{unit}'
        b /= 1024.0
    return f'{b:.1f}TB'


def analyze_imaging_products(benchmark_dir: str, optimized_dir: str) -> None:
    """Compare imaging products between two runs."""
    print('\n' + '=' * 100)
    print('IMAGING PRODUCTS SIZE ANALYSIS')
    print('=' * 100)
    
    # Get file lists
    benchmark_files = parse_du_output(benchmark_dir)
    optimized_files = parse_du_output(optimized_dir)
    
    print(f'Benchmark files: {len(benchmark_files)}')
    print(f'Optimized files: {len(optimized_files)}')
    
    # Filter to imaging products only
    imaging_pattern_keywords = ['oussid', 'uid_', 'regcal', 'selfcal', 'findcont', 'cube', 'repbw']
    
    benchmark_imaging = {
        k: v for k, v in benchmark_files.items()
        if any(kw in k.lower() for kw in imaging_pattern_keywords) and '.pickle' not in k and '.log' not in k
    }
    optimized_imaging = {
        k: v for k, v in optimized_files.items()
        if any(kw in k.lower() for kw in imaging_pattern_keywords) and '.pickle' not in k and '.log' not in k
    }
    
    print(f'Benchmark imaging files: {len(benchmark_imaging)}')
    print(f'Optimized imaging files: {len(optimized_imaging)}')
    
    # Build comparison by extracting base filenames
    benchmark_by_name = {Path(p).name: s for p, s in benchmark_imaging.items()}
    optimized_by_name = {Path(p).name: s for p, s in optimized_imaging.items()}
    
    # Aggregate by stage and type
    by_stage = defaultdict(lambda: {'benchmark': 0, 'optimized': 0, 'files': []})
    by_type = defaultdict(lambda: {'benchmark': 0, 'optimized': 0, 'files': []})
    by_filetype = defaultdict(lambda: {'benchmark': 0, 'optimized': 0, 'files': []})
    
    # Compare common files
    for filename in set(benchmark_by_name.keys()) | set(optimized_by_name.keys()):
        bench_size = benchmark_by_name.get(filename, 0)
        opt_size = optimized_by_name.get(filename, 0)
        
        if bench_size == 0 and opt_size == 0:
            continue
        
        stage = extract_stage(filename) or 'unknown'
        ptype = extract_processing_type(filename)
        ftype = extract_file_type(filename)
        
        by_stage[stage]['benchmark'] += bench_size
        by_stage[stage]['optimized'] += opt_size
        by_stage[stage]['files'].append((filename, bench_size, opt_size))
        
        by_type[ptype]['benchmark'] += bench_size
        by_type[ptype]['optimized'] += opt_size
        by_type[ptype]['files'].append((filename, bench_size, opt_size))
        
        by_filetype[ftype]['benchmark'] += bench_size
        by_filetype[ftype]['optimized'] += opt_size
        by_filetype[ftype]['files'].append((filename, bench_size, opt_size))
    
    # Print by stage
    print('\n' + '-' * 100)
    print('BY IMAGING STAGE')
    print('-' * 100)
    print(f'{"Stage":<10} {"Benchmark":>15} {"Optimized":>15} {"Change":>15} {"% Change":>10}')
    print('-' * 100)
    
    total_bench_stage = 0
    total_opt_stage = 0
    
    for stage in sorted(by_stage.keys()):
        data = by_stage[stage]
        bench = data['benchmark']
        opt = data['optimized']
        change = opt - bench
        pct = (change / bench * 100) if bench > 0 else 0
        
        total_bench_stage += bench
        total_opt_stage += opt
        
        print(f'{stage:<10} {format_bytes(bench):>15} {format_bytes(opt):>15} {format_bytes(change):>15} {pct:>9.1f}%')
    
    print('-' * 100)
    total_change_stage = total_opt_stage - total_bench_stage
    total_pct_stage = (total_change_stage / total_bench_stage * 100) if total_bench_stage > 0 else 0
    print(f'{"TOTAL":<10} {format_bytes(total_bench_stage):>15} {format_bytes(total_opt_stage):>15} {format_bytes(total_change_stage):>15} {total_pct_stage:>9.1f}%')
    
    # Print by processing type
    print('\n' + '-' * 100)
    print('BY PROCESSING TYPE')
    print('-' * 100)
    print(f'{"Type":<15} {"Benchmark":>15} {"Optimized":>15} {"Change":>15} {"% Change":>10}')
    print('-' * 100)
    
    total_bench_type = 0
    total_opt_type = 0
    
    for ptype in sorted(by_type.keys()):
        data = by_type[ptype]
        bench = data['benchmark']
        opt = data['optimized']
        change = opt - bench
        pct = (change / bench * 100) if bench > 0 else 0
        
        total_bench_type += bench
        total_opt_type += opt
        
        print(f'{ptype:<15} {format_bytes(bench):>15} {format_bytes(opt):>15} {format_bytes(change):>15} {pct:>9.1f}%')
    
    # Print by file type
    print('\n' + '-' * 100)
    print('BY FILE TYPE')
    print('-' * 100)
    print(f'{"Type":<20} {"Benchmark":>15} {"Optimized":>15} {"Change":>15} {"% Change":>10}')
    print('-' * 100)
    
    total_bench_ftype = 0
    total_opt_ftype = 0
    
    for ftype in sorted(by_filetype.keys()):
        data = by_filetype[ftype]
        bench = data['benchmark']
        opt = data['optimized']
        change = opt - bench
        pct = (change / bench * 100) if bench > 0 else 0
        
        total_bench_ftype += bench
        total_opt_ftype += opt
        
        print(f'{ftype:<20} {format_bytes(bench):>15} {format_bytes(opt):>15} {format_bytes(change):>15} {pct:>9.1f}%')
    
    # Top movers
    print('\n' + '-' * 100)
    print('TOP 10 LARGEST SAVINGS (by file)')
    print('-' * 100)
    print(f'{"File":<60} {"Reduction":>15} {"% Reduction":>10}')
    print('-' * 100)
    
    all_files = []
    for fname in set(benchmark_by_name.keys()) | set(optimized_by_name.keys()):
        bench = benchmark_by_name.get(fname, 0)
        opt = optimized_by_name.get(fname, 0)
        if bench > 0:
            reduction = bench - opt
            pct = (reduction / bench * 100)
            if reduction > 0:
                all_files.append((fname, bench, opt, reduction, pct))
    
    all_files.sort(key=lambda x: x[3], reverse=True)
    
    for fname, bench, opt, reduction, pct in all_files[:10]:
        short_name = fname[-60:] if len(fname) > 60 else fname
        print(f'{short_name:<60} {format_bytes(reduction):>15} {pct:>9.1f}%')
    
    print('\n' + '=' * 100)
    print('SUMMARY')
    print('=' * 100)
    print(f'Total imaging product reduction: {format_bytes(total_bench_stage - total_opt_stage)}')
    print(f'This accounts for the largest chunk of the 900 MB disk usage reduction.')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('Usage: python drill_imaging_products.py <benchmark-dir> <optimized-dir>')
        print('Example: python drill_imaging_products.py /path/to/benchmarks/ALMA-IF/working /path/to/tests/context_optimization/ALMA-IF/working')
        sys.exit(1)
    
    benchmark = sys.argv[1]
    optimized = sys.argv[2]
    
    analyze_imaging_products(benchmark, optimized)
