#!/usr/bin/env python3
'''
Estimate Phase 4 results slimming gains without re-running a pipeline.

Loads result pickles, applies slim_for_pickle() when available, and compares
serialized sizes to estimate savings.
'''

from __future__ import annotations

import argparse
import os
import pickle
import sys
import tempfile
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    '''Parse command-line arguments.'''
    parser = argparse.ArgumentParser(
        description='Estimate result pickle size savings from slim_for_pickle() without rerunning the pipeline.',
    )
    parser.add_argument(
        'path',
        help='Path to saved_state directory or result-stage*.pickle file.',
    )
    parser.add_argument(
        '--min-size-mb',
        type=float,
        default=50.0,
        help='Only analyze pickles >= this size (MB). Default: 50.',
    )
    parser.add_argument(
        '--top',
        type=int,
        default=10,
        help='Show top N savings. Default: 10.',
    )
    parser.add_argument(
        '--temp-dir',
        default=None,
        help='Directory for temporary pickle files. Use a path with ample free space.',
    )
    parser.add_argument(
        '--max-size-mb',
        type=float,
        default=None,
        help='Skip pickles larger than this size (MB). Default: no limit.',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Estimate savings from transient fields without re-pickling full results.',
    )
    parser.add_argument(
        '--assume-view-transient',
        action='store_true',
        help='When no _transient_fields are present, estimate size of a view attribute if found.',
    )
    return parser.parse_args()


def format_bytes(num_bytes: int) -> str:
    '''Format bytes as human-readable string.'''
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    size = float(num_bytes)
    for unit in units:
        if size < 1024.0:
            return f'{size:.1f}{unit}'
        size /= 1024.0
    return f'{size:.1f}PB'


def iter_pickles(path: Path) -> list[Path]:
    '''Collect result pickle paths from a file or directory.'''
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.glob('result-stage*.pickle'))
    return []


def slim_object(obj: Any) -> Any:
    '''Return a slimmed object if possible; otherwise return the original.'''
    slim = getattr(obj, 'slim_for_pickle', None)
    if callable(slim):
        try:
            return slim()
        except AttributeError:
            pass

    if isinstance(obj, list):
        return [slim_object(item) for item in obj]
    if isinstance(obj, tuple):
        return tuple(slim_object(item) for item in obj)

    results_attr = getattr(obj, 'results', None)
    if isinstance(results_attr, list):
        slimmed_results = [slim_object(item) for item in results_attr]
        try:
            obj.results = slimmed_results
        except AttributeError:
            pass
        return obj

    return obj


def estimate_transient_size(obj: Any, assume_view_transient: bool) -> int | None:
    '''Estimate total pickle size for transient fields only.'''
    if isinstance(obj, list):
        sizes = [estimate_transient_size(item, assume_view_transient) for item in obj]
        size_total = sum(size for size in sizes if size is not None)
        return size_total if size_total > 0 else None
    if isinstance(obj, tuple):
        sizes = [estimate_transient_size(item, assume_view_transient) for item in obj]
        size_total = sum(size for size in sizes if size is not None)
        return size_total if size_total > 0 else None

    results_attr = getattr(obj, 'results', None)
    if isinstance(results_attr, list):
        sizes = [estimate_transient_size(item, assume_view_transient) for item in results_attr]
        size_total = sum(size for size in sizes if size is not None)
        return size_total if size_total > 0 else None

    transient_fields = getattr(obj, '_transient_fields', None)
    if not transient_fields:
        if assume_view_transient and hasattr(obj, 'view'):
            try:
                return len(pickle.dumps(getattr(obj, 'view'), protocol=pickle.HIGHEST_PROTOCOL))
            except Exception:  # noqa: BLE001 - best-effort estimate
                return None
        return None

    total = 0
    any_size = False
    for field in transient_fields:
        if not hasattr(obj, field):
            continue
        value = getattr(obj, field)
        try:
            size = len(pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL))
        except Exception:  # noqa: BLE001 - best-effort estimate
            continue
        total += size
        any_size = True

    return total if any_size else None


def estimate_pickle_size(obj: Any, temp_dir: str | None, expected_size: int | None) -> int:
    '''Estimate serialized size by writing to a temporary file.'''
    temp_path = None
    if temp_dir is not None:
        temp_path = Path(temp_dir).expanduser().resolve()
        temp_path.mkdir(parents=True, exist_ok=True)

    if temp_path is not None and expected_size is not None:
        stat = os.statvfs(str(temp_path))
        free_bytes = stat.f_frsize * stat.f_bavail
        if free_bytes < int(expected_size * 1.1):
            raise RuntimeError(
                f'Not enough free space in temp dir ({format_bytes(free_bytes)} available). '
                f'Need roughly {format_bytes(int(expected_size * 1.1))}.'
            )

    with tempfile.NamedTemporaryFile(delete=True, dir=str(temp_path) if temp_path else None) as tmp:
        pickle.dump(obj, tmp, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.flush()
        return Path(tmp.name).stat().st_size


def analyze_pickle(
    pickle_path: Path,
    min_size_bytes: int,
    max_size_bytes: int | None,
    temp_dir: str | None,
    dry_run: bool,
    assume_view_transient: bool,
) -> tuple[str, int, int] | None:
    '''Analyze one pickle and return (name, original_size, slim_size).'''
    original_size = pickle_path.stat().st_size
    if original_size < min_size_bytes:
        return None
    if max_size_bytes is not None and original_size > max_size_bytes:
        return None

    try:
        with pickle_path.open('rb') as handle:
            obj = pickle.load(handle)
    except Exception as exc:  # noqa: BLE001 - broad to keep scanning
        print(f'Failed to load {pickle_path.name}: {exc}', file=sys.stderr)
        return None

    if dry_run:
        transient_size = estimate_transient_size(obj, assume_view_transient)
        if transient_size is None:
            print(f'No transient estimate available for {pickle_path.name}', file=sys.stderr)
            return None
        slim_size = max(original_size - transient_size, 0)
    else:
        slimmed = slim_object(obj)
        try:
            slim_size = estimate_pickle_size(slimmed, temp_dir, original_size)
        except Exception as exc:  # noqa: BLE001 - broad to keep scanning
            print(f'Failed to re-pickle {pickle_path.name}: {exc}', file=sys.stderr)
            return None

    return (pickle_path.name, original_size, slim_size)


def main() -> int:
    '''Entry point.'''
    args = parse_args()
    target = Path(args.path)
    pickles = iter_pickles(target)

    if not pickles:
        print(f'No pickles found under: {target}')
        return 1

    min_size_bytes = int(args.min_size_mb * 1024 * 1024)
    max_size_bytes = None
    if args.max_size_mb is not None:
        max_size_bytes = int(args.max_size_mb * 1024 * 1024)

    results: list[tuple[str, int, int]] = []
    for pickle_path in pickles:
        result = analyze_pickle(
            pickle_path,
            min_size_bytes,
            max_size_bytes,
            args.temp_dir,
            args.dry_run,
            args.assume_view_transient,
        )
        if result is not None:
            results.append(result)

    if not results:
        print('No pickles analyzed successfully. Check errors above or adjust --max-size-mb/--temp-dir.')
        return 0

    results.sort(key=lambda item: item[1] - item[2], reverse=True)

    total_original = sum(item[1] for item in results)
    total_slim = sum(item[2] for item in results)
    total_saved = total_original - total_slim
    total_pct = (total_saved / total_original * 100.0) if total_original else 0.0

    print('RESULT SLIMMING ESTIMATES')
    print('=' * 88)
    max_size_label = 'no limit' if args.max_size_mb is None else f'{args.max_size_mb:.1f} MB'
    mode_label = 'dry-run estimate' if args.dry_run else 're-pickle estimate'
    print(f'Analyzed: {len(results)} pickles >= {args.min_size_mb:.1f} MB (max: {max_size_label})')
    print(f'Mode: {mode_label}')
    print(f'Total original: {format_bytes(total_original)}')
    print(f'Total slimmed:  {format_bytes(total_slim)}')
    print(f'Total saved:    {format_bytes(total_saved)} ({total_pct:.1f}%)')
    print('-' * 88)
    print(f'{"Pickle":<32} {"Original":>14} {"Slimmed":>14} {"Saved":>14} {"%":>7}')
    print('-' * 88)

    for name, original, slimmed in results[: args.top]:
        saved = original - slimmed
        pct = (saved / original * 100.0) if original else 0.0
        print(f'{name:<32} {format_bytes(original):>14} {format_bytes(slimmed):>14} '
              f'{format_bytes(saved):>14} {pct:>6.1f}%')

    print('=' * 88)
    note = 'Note: This is a post-hoc estimate. It does not measure runtime.'
    if args.dry_run:
        note = 'Note: This is an estimate based on transient field sizes only.'
    print(note)
    return 0


if __name__ == '__main__':
    sys.exit(main())
