#!/usr/bin/env python3
"""
Profile result object sizes to identify bloated attributes.

This tool loads result pickles and provides detailed size breakdowns of their contents,
helping identify which attributes consume the most space. It's particularly useful for
diagnosing known issues with tasks like hif_rawflagchans and h*_tsysflag that store
large data arrays in result objects.

Usage:
    # Profile a single result pickle
    python profile_result_objects.py /path/to/results-stage7.pickle

    # Deep-dive analysis: recursive structure breakdown
    python profile_result_objects.py /path/to/results-stage14.pickle --deep-dive --max-depth 4

    # Profile all results in a pipeline output directory
    python profile_result_objects.py /path/to/pipeline/output --all

    # Profile only results larger than threshold
    python profile_result_objects.py /path/to/pipeline/output --all --min-size-mb 100

    # Export detailed JSON report
    python profile_result_objects.py /path/to/pipeline/output --all --json report.json

Options:
    --deep-dive:  Perform recursive analysis showing nested structure (single file only)
    --max-depth:  Maximum recursion depth for deep-dive (default: 4)
    --verbose:    Print detailed attribute breakdown
    --json FILE:  Export results to JSON file
    --all:        Profile all result pickles in directory
    --min-size-mb: Minimum file size to include in profile (default: 0)
"""

import argparse
import collections
import json
import pickle
import sys
from pathlib import Path
from typing import Any

import numpy as np


def get_obj_size(obj: Any, seen: set | None = None) -> int:
    """
    Recursively calculate the size of an object in bytes.

    This is adapted from pipeline.infrastructure.utils.get_obj_size
    but made standalone for this diagnostic tool.

    Args:
        obj: Object to measure
        seen: Set of object IDs already visited (prevents double-counting)

    Returns:
        Size in bytes
    """
    size = sys.getsizeof(obj)
    if seen is None:
        seen = set()

    obj_id = id(obj)
    if obj_id in seen:
        return 0

    seen.add(obj_id)

    if isinstance(obj, dict):
        size += sum(get_obj_size(k, seen) + get_obj_size(v, seen) for k, v in obj.items())
    elif hasattr(obj, '__dict__'):
        size += get_obj_size(obj.__dict__, seen)
    elif hasattr(obj, '__iter__') and not isinstance(obj, (str, bytes, bytearray)):
        try:
            size += sum(get_obj_size(i, seen) for i in obj)
        except TypeError:
            pass

    return size


def format_size(bytes_size: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f'{bytes_size:.2f} {unit}'
        bytes_size /= 1024.0
    return f'{bytes_size:.2f} TB'


def analyze_array_attribute(name: str, obj: Any) -> dict | None:
    """Analyze numpy array or similar container attribute."""
    if isinstance(obj, np.ndarray):
        return {
            'type': 'numpy.ndarray',
            'shape': obj.shape,
            'dtype': str(obj.dtype),
            'size_bytes': obj.nbytes,
            'size_human': format_size(obj.nbytes),
        }
    elif isinstance(obj, (list, tuple)) and obj and isinstance(obj[0], np.ndarray):
        total_bytes = sum(arr.nbytes for arr in obj if isinstance(arr, np.ndarray))
        return {
            'type': f'{type(obj).__name__} of numpy arrays',
            'count': len(obj),
            'total_size_bytes': total_bytes,
            'total_size_human': format_size(total_bytes),
        }
    elif isinstance(obj, dict):
        # Check if it's a dictionary of arrays or large objects
        if obj:
            sample_key = next(iter(obj.keys()))
            sample_value = obj[sample_key]
            dict_size = get_obj_size(obj)
            if dict_size > 1_000_000:  # > 1 MB
                return {
                    'type': f'dict[{type(sample_key).__name__}, {type(sample_value).__name__}]',
                    'count': len(obj),
                    'size_bytes': dict_size,
                    'size_human': format_size(dict_size),
                }
    elif isinstance(obj, collections.defaultdict):
        dict_size = get_obj_size(obj)
        if dict_size > 1_000_000:  # > 1 MB
            return {
                'type': f'defaultdict ({len(obj)} entries)',
                'count': len(obj),
                'size_bytes': dict_size,
                'size_human': format_size(dict_size),
            }
    return None


def profile_result_object(result_obj: Any) -> dict:
    """
    Profile a result object, breaking down size by attribute.

    Args:
        result_obj: Result object to profile

    Returns:
        Dictionary with profiling information
    """
    profile = {
        'type': type(result_obj).__name__,
        'attributes': {},
        'total_size_bytes': 0,
        'total_size_human': '',
    }

    # Get all attributes
    if hasattr(result_obj, '__dict__'):
        attrs = result_obj.__dict__
    else:
        return profile

    # Profile each attribute
    attr_sizes = []
    for attr_name, attr_value in attrs.items():
        attr_size = get_obj_size(attr_value)
        attr_info = {
            'size_bytes': attr_size,
            'size_human': format_size(attr_size),
            'type': type(attr_value).__name__,
        }

        # Special handling for known large attribute types
        array_info = analyze_array_attribute(attr_name, attr_value)
        if array_info:
            attr_info.update(array_info)

        # Special handling for view/components dictionaries
        if attr_name in ('view', 'components') and isinstance(attr_value, (dict, collections.defaultdict)):
            attr_info['entry_count'] = len(attr_value)
            if attr_value:
                # Sample the first entry
                sample_key = next(iter(attr_value.keys()))
                sample_value = attr_value[sample_key]
                attr_info['sample_key'] = str(sample_key)[:100]  # Truncate long keys
                attr_info['sample_value_type'] = type(sample_value).__name__
                if isinstance(sample_value, list):
                    attr_info['sample_value_length'] = len(sample_value)
                    if sample_value:
                        attr_info['sample_entry_type'] = type(sample_value[0]).__name__

        profile['attributes'][attr_name] = attr_info
        attr_sizes.append((attr_name, attr_size))

    # Calculate total size
    profile['total_size_bytes'] = get_obj_size(result_obj)
    profile['total_size_human'] = format_size(profile['total_size_bytes'])

    # Rank attributes by size
    attr_sizes.sort(key=lambda x: x[1], reverse=True)
    profile['top_attributes'] = [
        {'name': name, 'size_bytes': size, 'size_human': format_size(size)}
        for name, size in attr_sizes[:10]
    ]

    return profile


def profile_result_pickle(pickle_path: Path) -> dict:
    """
    Profile a result pickle file.

    Args:
        pickle_path: Path to pickle file

    Returns:
        Dictionary with profiling information including file info
    """
    print(f'Loading {pickle_path}...')

    # Get file size
    file_size = pickle_path.stat().st_size

    # Load pickle
    try:
        with open(pickle_path, 'rb') as f:
            result_obj = pickle.load(f)
    except Exception as e:
        return {
            'file': str(pickle_path),
            'file_size_bytes': file_size,
            'file_size_human': format_size(file_size),
            'error': f'Error loading pickle {pickle_path}: {e}',
        }

    # Profile the object
    profile = profile_result_object(result_obj)
    profile['file'] = str(pickle_path)
    profile['file_size_bytes'] = file_size
    profile['file_size_human'] = format_size(file_size)

    # Calculate pickle overhead
    obj_size = profile['total_size_bytes']
    overhead_bytes = file_size - obj_size
    overhead_pct = (overhead_bytes / file_size * 100) if file_size > 0 else 0
    profile['pickle_overhead_bytes'] = overhead_bytes
    profile['pickle_overhead_pct'] = overhead_pct

    return profile


def analyze_object_recursive(obj: Any, name: str = "root", depth: int = 0, max_depth: int = 4) -> dict:
    """
    Recursively analyze object structure and size (deep-dive mode).

    Args:
        obj: Object to analyze
        name: Name of the object
        depth: Current recursion depth
        max_depth: Maximum recursion depth

    Returns:
        Dictionary with nested structure analysis
    """
    result = {
        "name": name,
        "type": type(obj).__name__,
        "module": type(obj).__module__ if hasattr(type(obj), "__module__") else "unknown",
        "size_mb": get_obj_size(obj) / 1_000_000,
        "depth": depth,
        "callable": callable(obj),
    }

    if depth >= max_depth:
        result["truncated"] = True
        return result

    # Analyze containers
    if isinstance(obj, dict):
        result["dict_size"] = len(obj)
        result["keys_sample"] = list(obj.keys())[:10]
        if len(obj) <= 5:
            result["items"] = {
                k: {
                    "type": type(v).__name__,
                    "size_mb": get_obj_size(v) / 1_000_000
                } for k, v in obj.items()
            }

    elif isinstance(obj, (list, tuple)):
        result["len"] = len(obj)
        if len(obj) > 0:
            result["first_item_type"] = type(obj[0]).__name__
            result["first_item_size_mb"] = get_obj_size(obj[0]) / 1_000_000
            if len(obj) <= 3:
                result["items"] = [
                    {
                        "type": type(item).__name__,
                        "size_mb": get_obj_size(item) / 1_000_000
                    } for item in obj
                ]

    elif hasattr(obj, "__dict__") and not isinstance(obj, type):
        # Custom object - analyze attributes
        attrs = obj.__dict__
        result["attributes"] = {}

        for attr_name, attr_val in sorted(attrs.items()):
            if not callable(attr_val):
                attr_size_mb = get_obj_size(attr_val) / 1_000_000
                result["attributes"][attr_name] = {
                    "type": type(attr_val).__name__,
                    "size_mb": attr_size_mb,
                }

                # For large attributes, recurse
                if attr_size_mb > 1.0 and depth < max_depth - 1:
                    child_analysis = analyze_object_recursive(
                        attr_val,
                        attr_name,
                        depth + 1,
                        max_depth
                    )
                    result["attributes"][attr_name]["analysis"] = child_analysis

    return result


def print_deep_dive_report(analysis: dict, indent: int = 0) -> None:
    """Pretty-print deep-dive analysis results."""
    ind = "  " * indent

    size_mb = analysis['size_mb']
    print(f"{ind}{analysis['name']}: {analysis['type']} ({size_mb:.1f} MB)")

    if "dict_size" in analysis:
        print(f"{ind}  Dict with {analysis['dict_size']} keys")
    elif "len" in analysis:
        print(f"{ind}  List/tuple with {analysis['len']} items")

    if "attributes" in analysis:
        attrs = analysis["attributes"]
        # Sort by size
        sorted_attrs = sorted(attrs.items(), key=lambda x: x[1]["size_mb"], reverse=True)

        print(f"{ind}  Attributes ({len(attrs)}):")
        for attr_name, attr_info in sorted_attrs[:15]:  # Top 15
            size_mb = attr_info["size_mb"]
            attr_type = attr_info["type"]
            print(f"{ind}    {attr_name}: {attr_type} ({size_mb:.1f} MB)")

            # Recurse for large nested analyses
            if "analysis" in attr_info and size_mb > 1.0:
                print_deep_dive_report(attr_info["analysis"], indent + 3)


def print_profile_report(profile: dict, verbose: bool = False) -> None:
    """Print human-readable profile report."""
    print(f"\n{'=' * 80}")
    print(f"Result Pickle Profile: {Path(profile['file']).name}")
    print(f"{'=' * 80}")
    print(f"File size:        {profile['file_size_human']} ({profile['file_size_bytes']:,} bytes)")
    print(f"Object size:      {profile['total_size_human']} ({profile['total_size_bytes']:,} bytes)")
    print(f"Pickle overhead:  {profile.get('pickle_overhead_pct', 0):.1f}%")
    print(f"Result type:      {profile['type']}")

    if 'error' in profile:
        print(f"\nERROR: {profile['error']}")
        return

    print(f"\nTop 10 Attributes by Size:")
    print(f"{'-' * 80}")
    for i, attr in enumerate(profile['top_attributes'], 1):
        print(f"{i:2}. {attr['name']:30} {attr['size_human']:>15} ({attr['size_bytes']:,} bytes)")

    if verbose:
        print(f"\nDetailed Attribute Breakdown:")
        print(f"{'-' * 80}")
        for attr_name, attr_info in sorted(
            profile['attributes'].items(),
            key=lambda x: x[1]['size_bytes'],
            reverse=True
        ):
            print(f"\n{attr_name}:")
            print(f"  Type:  {attr_info['type']}")
            print(f"  Size:  {attr_info['size_human']} ({attr_info['size_bytes']:,} bytes)")

            # Print additional details
            for key, value in attr_info.items():
                if key not in ('type', 'size_bytes', 'size_human'):
                    print(f"  {key.replace('_', ' ').title()}: {value}")


def find_result_pickles(output_dir: Path, min_size_mb: float = 0) -> list[Path]:
    """
    Find all result pickle files in a pipeline output directory.

    Args:
        output_dir: Pipeline output directory
        min_size_mb: Minimum file size in MB to include

    Returns:
        List of result pickle paths sorted by size (largest first)
    """
    min_size_bytes = int(min_size_mb * 1024 * 1024)

    # Look for both result-stageN.pickle and results-stageN.pickle patterns
    result_pickles = []
    for pattern in ('**/result-stage*.pickle', '**/results-stage*.pickle'):
        for path in output_dir.glob(pattern):
            if path.stat().st_size >= min_size_bytes:
                result_pickles.append(path)

    # Sort by size descending
    result_pickles.sort(key=lambda p: p.stat().st_size, reverse=True)
    return result_pickles


def main():
    parser = argparse.ArgumentParser(
        description='Profile pipeline result objects to identify memory bloat',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        'path',
        help='Path to result pickle file or pipeline output directory',
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Profile all result pickles in directory (requires path to be directory)',
    )
    parser.add_argument(
        '--min-size-mb',
        type=float,
        default=0,
        help='Minimum file size in MB to profile (default: 0, profile all)',
    )
    parser.add_argument(
        '--json',
        metavar='FILE',
        help='Export detailed results to JSON file',
    )
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Print detailed attribute breakdown',
    )
    parser.add_argument(
        '--deep-dive',
        action='store_true',
        help='Perform deep recursive analysis of object structure (for single file only)',
    )
    parser.add_argument(
        '--max-depth',
        type=int,
        default=4,
        help='Maximum recursion depth for deep-dive analysis (default: 4)',
    )

    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f'Error: Path does not exist: {path}', file=sys.stderr)
        return 1

    # Deep-dive mode requires single file
    if args.deep_dive:
        if not path.is_file():
            print(f'Error: --deep-dive requires path to be a file', file=sys.stderr)
            return 1
        if args.all:
            print(f'Error: --deep-dive is incompatible with --all', file=sys.stderr)
            return 1

    # Collect paths to profile
    if args.all:
        if not path.is_dir():
            print(f'Error: --all requires path to be a directory', file=sys.stderr)
            return 1
        pickle_paths = find_result_pickles(path, args.min_size_mb)
        if not pickle_paths:
            print(f'No result pickles found in {path}', file=sys.stderr)
            return 1
        print(f'Found {len(pickle_paths)} result pickle(s) matching criteria')
    else:
        if not path.is_file():
            print(f'Error: Path is not a file: {path}', file=sys.stderr)
            return 1
        pickle_paths = [path]

    # Profile each pickle
    profiles = []
    for pickle_path in pickle_paths:
        profile = profile_result_pickle(pickle_path)
        profiles.append(profile)

        if args.deep_dive and len(pickle_paths) == 1:
            # Deep-dive mode: load and analyze recursively
            print(f'\n{"=" * 80}')
            print(f'Deep-Dive Analysis: {pickle_path.name}')
            print(f'{"=" * 80}\n')
            try:
                with open(pickle_path, 'rb') as f:
                    result = pickle.load(f)
                analysis = analyze_object_recursive(result, "ResultsList", max_depth=args.max_depth)
                print_deep_dive_report(analysis)
            except Exception as e:
                print(f'Error during deep-dive analysis: {e}', file=sys.stderr)
                return 1
        else:
            print_profile_report(profile, verbose=args.verbose)

    # Print summary if multiple files
    if len(profiles) > 1:
        print(f"\n{'=' * 80}")
        print(f"Summary: {len(profiles)} Result Pickles")
        print(f"{'=' * 80}")
        total_size = sum(p['file_size_bytes'] for p in profiles)
        print(f"Total size: {format_size(total_size)} ({total_size:,} bytes)")
        print(f"\nLargest 5 pickles:")
        for i, profile in enumerate(profiles[:5], 1):
            print(f"{i}. {Path(profile['file']).name:40} {profile['file_size_human']:>15}")

    # Export JSON if requested
    if args.json:
        json_path = Path(args.json)
        print(f'\nExporting detailed results to {json_path}...')
        with open(json_path, 'w') as f:
            json.dump(profiles, f, indent=2, default=str)
        print('Export complete.')

    return 0


if __name__ == '__main__':
    sys.exit(main())
