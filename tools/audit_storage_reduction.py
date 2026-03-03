#!/usr/bin/env python3
"""
Comprehensive storage audit to attribute all 900 MB savings.

This script compares directory sizes between baseline and optimized runs
to account for every byte of improvement.
"""

import subprocess
import sys
from pathlib import Path
from dataclasses import dataclass


@dataclass
class DirSize:
    """Represents size of a directory component."""
    path: str
    size_bytes: int
    
    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)


def get_dir_sizes(root_path: str) -> dict[str, int]:
    """Get sizes of all top-level directories."""
    result = {}
    root = Path(root_path)
    
    if not root.exists():
        print(f"ERROR: {root_path} does not exist", file=sys.stderr)
        return result
    
    try:
        for item in sorted(root.iterdir()):
            if item.is_dir():
                try:
                    # Use du -sb for byte-accurate results
                    cmd = ['du', '-sb', str(item)]
                    output = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                    if output.returncode == 0:
                        size_bytes = int(output.stdout.split()[0])
                        result[item.name] = size_bytes
                except Exception as e:
                    print(f"Warning: Could not measure {item.name} in directory {root_path}: {e}", file=sys.stderr)
            elif item.is_file():
                # Count top-level files separately
                try:
                    result[f'FILE:{item.name}'] = item.stat().st_size
                except Exception as e:
                    print(f"Warning: Could not measure {item.name}: {e}", file=sys.stderr)
    except PermissionError as e:
        print(f"ERROR: Permission denied on {root_path}: {e}", file=sys.stderr)
    
    return result


def format_bytes(b: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if abs(b) < 1024.0:
            return f'{b:.1f} {unit}'
        b /= 1024.0
    return f'{b:.1f} TB'


def compare_runs(baseline_path: str, optimized_path: str) -> None:
    """Compare storage between baseline and optimized runs."""
    print('\n' + '=' * 100)
    print('STORAGE AUDIT: Component-by-Component Breakdown')
    print('=' * 100)
    
    baseline = get_dir_sizes(baseline_path)
    optimized = get_dir_sizes(optimized_path)
    
    if not baseline or not optimized:
        print('ERROR: Could not read directory sizes')
        return
    
    print(f'\nBaseline:  {baseline_path}')
    print(f'Optimized: {optimized_path}\n')
    
    # Get all unique component names
    all_components = sorted(set(baseline.keys()) | set(optimized.keys()))
    
    total_baseline = 0
    total_optimized = 0
    
    print(f'{"Component":<40} {"Baseline":>15} {"Optimized":>15} {"Change":>15} {"% Change":>10}')
    print('-' * 100)
    
    phase4_components = {'html', 'saved_state'}
    phase4_savings = 0
    
    for component in all_components:
        baseline_size = baseline.get(component, 0)
        optimized_size = optimized.get(component, 0)
        change = optimized_size - baseline_size
        
        total_baseline += baseline_size
        total_optimized += optimized_size
        
        if baseline_size == 0:
            pct_change = '—'
        else:
            pct_change = f'{(change / baseline_size) * 100:.1f}%'
        
        print(
            f'{component:<40} {format_bytes(baseline_size):>15} '
            f'{format_bytes(optimized_size):>15} {format_bytes(change):>15} {pct_change:>10}'
        )
        
        # Track Phase 4 attributed savings
        if component in phase4_components:
            if change < 0:
                phase4_savings += abs(change)
    
    print('-' * 100)
    total_change = total_optimized - total_baseline
    total_savings = abs(total_change) if total_change < 0 else 0
    total_pct = f'{(total_change / total_baseline) * 100:.1f}%' if total_baseline > 0 else '—'
    
    print(
        f'{"TOTAL":<40} {format_bytes(total_baseline):>15} '
        f'{format_bytes(total_optimized):>15} {format_bytes(total_change):>15} {total_pct:>10}'
    )
    
    # Attribution summary
    print('\n' + '=' * 100)
    print('ATTRIBUTION ANALYSIS')
    print('=' * 100)
    print(f'Total storage reduction: {format_bytes(total_savings)} ({(total_savings/total_baseline)*100:.1f}%)')
    print(f'Phase 4 attributed (html + saved_state): {format_bytes(phase4_savings)}')
    
    unattributed = total_savings - phase4_savings
    if unattributed > 0:
        print(f'UNATTRIBUTED: {format_bytes(unattributed)} ({(unattributed/total_savings)*100:.1f}% of savings)')
        print('\n⚠️  Investigation needed for unattributed savings:')
        print('   1. Check if measurement sets (MS) were trimmed')
        print('   2. Look for CASA working directories/caches cleared')
        print('   3. Verify temporary files/logs were not part of comparison')
        print('   4. Compare file lists to ensure same data was processed')
    else:
        print(f'\n✅ All savings attributed to Phase 4 changes')
    
    # Recommendations
    print('\n' + '=' * 100)
    print('DETAILED COMPONENT ANALYSIS')
    print('=' * 100)
    print('''
Components to investigate for Phase 4 attribution:

1. **html/** (Phase 2 + 4 impact)
   - Metadata caching (Phase 2) reduces renderers that rerun
   - Results slimming (Phase 4) reduces pickle load time
   - Smaller pickles = fewer temporary objects = smaller working set

2. **saved_state/** (Phase 4 direct impact)
   - Results slimming: Removes plots from flagging task pickles
   - Delta metadata: Lightweight exports instead of full Context pickles
   - Metadata snapshots: Separate YAML files instead of pickle duplication

3. **Measurement Sets (vis/)** (Unexpected - should not change)
   - If reduced: Data was re-processed differently
   - If same size: Verify comparison is fair

4. **CASA Working Files** (Potential Phase 3 impact)
   - Parallel unpickling may cache differently
   - CalFrom pool synchronization impacts memory layout
   - Could affect temporary file generation

5. **Logs/** (Should not change unless pipeline behavior differs)
   - If changed: Indicates different execution path
   - Check if stages ran differently

6. **Caches/** (Could be affected by metadata caching in Phase 2)
   - Renderer cache hits mean fewer rebuilds
   - Fewer builds = smaller temp file footprint
''')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('Usage: python audit_storage_reduction.py <baseline-dir> <optimized-dir>')
        print('Example: python audit_storage_reduction.py /path/to/baseline /path/to/optimized')
        sys.exit(1)
    
    baseline = sys.argv[1]
    optimized = sys.argv[2]
    
    compare_runs(baseline, optimized)
