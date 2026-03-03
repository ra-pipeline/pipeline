#!/usr/bin/env python3
"""Compare before/after benchmark results.

Produces comparison table showing performance deltas and percentage changes.

Usage:
    python compare_benchmarks.py baseline.json optimized.json
    python compare_benchmarks.py --before baseline.json --after optimized.json
    python compare_benchmarks.py -b baseline.json -a optimized.json --csv
"""

import argparse
import csv
import json
import sys
from typing import Any


def load_results(filepath: str) -> dict[str, Any]:
    """Load benchmark results from JSON file."""
    with open(filepath, 'r') as f:
        return json.load(f)


def split_meta(results: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split metadata from renderer results.

    Args:
        results: Raw results dict, possibly containing metadata.

    Returns:
        Tuple of (renderer_results, meta).
    """
    meta = {}
    if isinstance(results.get('__meta__'), dict):
        meta = results['__meta__']
    filtered = {key: value for key, value in results.items() if key != '__meta__'}
    return filtered, meta


def compare_results(
    baseline: dict[str, Any],
    optimized: dict[str, Any],
    as_csv: bool = False,
    show_variance: bool = True,
) -> str:
    """Generate comparison between baseline and optimized results.

    Args:
        baseline: Baseline benchmark results.
        optimized: Optimized benchmark results.
        as_csv: If True, output as CSV instead of table.
        show_variance: If True, show variance and significance indicators.

    Returns:
        Formatted comparison string.
    """
    lines = []

    if as_csv:
        fieldnames = ['Renderer', 'Baseline (s)', 'Baseline StDev', 'Optimized (s)',
                      'Optimized StDev', 'Delta (s)', 'Delta (%)', 'Significant']
        writer_obj = csv.DictWriter(
            sys.stdout,
            fieldnames=fieldnames
        )
        writer_obj.writeheader()

    else:
        if show_variance:
            header = (
                f'{"Renderer":<35} '
                f'{"Baseline":>20} {"Optimized":>20} '
                f'{"Delta":>12} {"% Change":>10} {"Sig.":>6}'
            )
            lines.append('=' * 110)
            lines.append(header)
            lines.append('-' * 110)
        else:
            header = (
                f'{"Renderer":<45} '
                f'{"Baseline":>12} {"Optimized":>12} '
                f'{"Delta":>12} {"% Change":>10}'
            )
            lines.append('=' * 93)
            lines.append(header)
            lines.append('-' * 93)

    total_baseline = 0
    total_optimized = 0
    total_delta = 0

    # Sort by renderer name for consistency
    for renderer in sorted(baseline.keys()):
        if renderer not in optimized:
            if not as_csv:
                if show_variance:
                    lines.append(
                        f'{renderer:<35} '
                        f'{"MISSING":>20} {"N/A":>20} {"N/A":>12} {"N/A":>10} {"N/A":>6}'
                    )
                else:
                    lines.append(
                        f'{renderer:<45} '
                        f'{"MISSING":>12} {"N/A":>12} {"N/A":>12} {"N/A":>10}'
                    )
            continue

        base_mean = baseline[renderer]['mean']
        base_stdev = baseline[renderer].get('stdev', 0)
        opt_mean = optimized[renderer]['mean']
        opt_stdev = optimized[renderer].get('stdev', 0)
        delta = opt_mean - base_mean
        pct_delta = (delta / base_mean * 100) if base_mean else 0

        # Simple significance check: if delta is within 1 stdev of baseline, likely not significant
        baseline_range = base_stdev
        is_significant = abs(delta) > baseline_range if baseline_range > 0 else False

        total_baseline += base_mean
        total_optimized += opt_mean
        total_delta += delta

        if as_csv:
            writer_obj.writerow({
                'Renderer': renderer,
                'Baseline (s)': f'{base_mean:.3f}',
                'Baseline StDev': f'{base_stdev:.3f}',
                'Optimized (s)': f'{opt_mean:.3f}',
                'Optimized StDev': f'{opt_stdev:.3f}',
                'Delta (s)': f'{delta:.3f}',
                'Delta (%)': f'{pct_delta:.1f}',
                'Significant': 'Yes' if is_significant else 'No',
            })
        else:
            # Color-code improvement/regression
            delta_str = f'{delta:+.3f}'
            pct_str = f'{pct_delta:+.1f}%'
            sig_marker = '*' if is_significant else ' '

            if show_variance:
                baseline_str = f'{base_mean:.3f}±{base_stdev:.3f}s'
                optimized_str = f'{opt_mean:.3f}±{opt_stdev:.3f}s'
                line = (
                    f'{renderer:<35} '
                    f'{baseline_str:>20} {optimized_str:>20} '
                    f'{delta_str:>12} {pct_str:>10} {sig_marker:>6}'
                )
            else:
                line = (
                    f'{renderer:<45} '
                    f'{base_mean:>12.3f}s {opt_mean:>12.3f}s '
                    f'{delta_str:>12} {pct_str:>10}'
                )
            lines.append(line)

    if not as_csv:
        if show_variance:
            lines.append('-' * 110)
        else:
            lines.append('-' * 93)
        total_pct_delta = (
            (total_delta / total_baseline * 100) if total_baseline else 0
        )
        if show_variance:
            lines.append(
                f'{"TOTAL":<35} '
                f'{total_baseline:>20.3f}s {total_optimized:>20.3f}s '
                f'{total_delta:>+12.3f} {total_pct_delta:>+9.1f}%'
            )
            lines.append('=' * 110)
            lines.append('\nNote: "*" indicates change is > 1 stdev from baseline (more likely significant)')
        else:
            lines.append(
                f'{"TOTAL":<45} '
                f'{total_baseline:>12.3f}s {total_optimized:>12.3f}s '
                f'{total_delta:>+12.3f} {total_pct_delta:>+9.1f}%'
            )
            lines.append('=' * 93)

        # Summary
        improvement = -total_pct_delta  # Negative delta is improvement
        if improvement > 0:
            lines.append(
                f'\n✓ IMPROVEMENT: {improvement:.1f}% faster '
                f'({total_baseline - total_optimized:.2f}s saved)'
            )
        elif improvement < 0:
            lines.append(
                f'\n✗ REGRESSION: {-improvement:.1f}% slower '
                f'({total_optimized - total_baseline:.2f}s added)'
            )
        else:
            lines.append('\n= NO CHANGE')

    return '\n'.join(lines) if not as_csv else ''


def print_statistics(baseline: dict[str, Any],
                     optimized: dict[str, Any]) -> None:
    """Print detailed statistics."""
    print('\nBASELINE STATISTICS:')
    print('-' * 60)
    for name, stats in sorted(baseline.items()):
        print(
            f'{name:<40} '
            f'median={stats["median"]:.3f}s, '
            f'stdev={stats["stdev"]:.3f}s'
        )

    print('\nOPTIMIZED STATISTICS:')
    print('-' * 60)
    for name, stats in sorted(optimized.items()):
        print(
            f'{name:<40} '
            f'median={stats["median"]:.3f}s, '
            f'stdev={stats["stdev"]:.3f}s'
        )


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Compare benchmark results from before and after optimization.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Basic comparison
  python compare_benchmarks.py baseline.json optimized.json

  # With explicit flags
  python compare_benchmarks.py --before baseline.json --after optimized.json

  # Output as CSV
  python compare_benchmarks.py -b baseline.json -a optimized.json --csv

  # Show statistics
  python compare_benchmarks.py -b baseline.json -a optimized.json --statistics
        '''
    )

    parser.add_argument(
        'before', nargs='?',
        help='Baseline results JSON file'
    )
    parser.add_argument(
        'after', nargs='?',
        help='Optimized results JSON file'
    )
    parser.add_argument(
        '-b', '--before', dest='before_opt',
        help='Baseline results JSON file (alternative)'
    )
    parser.add_argument(
        '-a', '--after', dest='after_opt',
        help='Optimized results JSON file (alternative)'
    )
    parser.add_argument(
        '--csv', action='store_true',
        help='Output comparison as CSV'
    )
    parser.add_argument(
        '--statistics', action='store_true',
        help='Also show detailed statistics'
    )
    parser.add_argument(
        '--no-variance', action='store_true',
        help='Hide variance (stdev) in comparison table'
    )

    args = parser.parse_args()

    # Determine files
    before_file = args.before_opt or args.before
    after_file = args.after_opt or args.after

    if not before_file or not after_file:
        parser.error(
            'Both baseline and optimized result files must be specified'
        )

    # Load results
    try:
        baseline_raw = load_results(before_file)
        optimized_raw = load_results(after_file)
    except FileNotFoundError as e:
        print(f'Error: {e}', file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f'Error parsing JSON: {e}', file=sys.stderr)
        sys.exit(1)

    baseline, baseline_meta = split_meta(baseline_raw)
    optimized, optimized_meta = split_meta(optimized_raw)

    if baseline_meta and optimized_meta:
        base_skip = baseline_meta.get('skip_origin_files')
        opt_skip = optimized_meta.get('skip_origin_files')
        if base_skip != opt_skip:
            print(
                'WARNING: Baseline/optimized results used different cache modes. '
                'Re-run with matching --skip-origin-files settings for a fair comparison.',
                file=sys.stderr,
            )

    # Generate comparison
    comparison = compare_results(
        baseline,
        optimized,
        args.csv,
        show_variance=not args.no_variance,
    )
    print(comparison)

    if args.statistics:
        print_statistics(baseline, optimized)


if __name__ == '__main__':
    main()
