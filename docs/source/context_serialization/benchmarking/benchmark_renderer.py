#!/usr/bin/env python3
"""Benchmark script for weblog renderer performance testing.

This script loads a pre-computed context (or individual stage results) and
repeatedly runs the weblog renderer to get accurate timing statistics.

IMPORTANT: This benchmark measures end-to-end renderer execution time, which
includes both plot generation (first run) and metadata serialization (all runs).
Metadata caching improvements are most visible in production scenarios where
the same measurement set is processed multiple times (e.g., pipeline re-runs,
iterative development). Single-run benchmarks show minimal improvement (~1-2%)
due to system noise and plot I/O dominance.

Usage:
    python benchmark_renderer.py --context PATH [--output PATH] [--runs N]
                                 [--renderers NAME] [--reset-cache]
                                 [--preserve-metadata] [--metadata-dir DIR]

    python benchmark_renderer.py --report-dir PATH [--output PATH] [--runs N]
                                 [--renderers NAME] [--preserve-metadata]
                                 [--metadata-dir DIR]
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import pickle
import shutil
import statistics
import sys
import time
from typing import Any


def load_context_from_pickle(context_path: str) -> Any:
    """Load a pickled context object from disk.

    Args:
        context_path: Path to the pickled context file.

    Returns:
        The unpickled Context object.

    Raises:
        FileNotFoundError: If context file does not exist.
        pickle.UnpicklingError: If pickle file is corrupted.
    """
    if not os.path.exists(context_path):
        raise FileNotFoundError(f'Context file not found: {context_path}')

    with open(context_path, 'rb') as f:
        context = pickle.load(f)
    return context


def find_latest_stage_context(search_roots: list[str]) -> str | None:
    """Find the latest context-stage*.pickle file under given roots.

    Args:
        search_roots: List of directories to search.

    Returns:
        Path to the latest stage context pickle, or None if not found.
    """
    latest_stage = -1
    latest_path: str | None = None

    for root in search_roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                if not filename.startswith('context-stage') or not filename.endswith('.pickle'):
                    continue
                try:
                    stage_part = filename.removeprefix('context-stage').removesuffix('.pickle')
                    stage_num = int(stage_part)
                except ValueError:
                    continue
                if stage_num > latest_stage:
                    latest_stage = stage_num
                    latest_path = os.path.join(dirpath, filename)

    return latest_path


def get_context_with_results(report_dir: str) -> Any:
    """Reconstruct a context object from a weblog report directory.

    This attempts to find pickled context or results files in the
    report directory and its subdirectories.

    Args:
        report_dir: Path to the weblog report directory.

    Returns:
        Context object with results loaded.

    Raises:
        FileNotFoundError: If no context/results found.
    """
    # Search for .context or .pickle files
    search_paths = [
        os.path.join(report_dir, 'context.pickle'),
        os.path.join(report_dir, '..', 'context.pickle'),
        os.path.join(report_dir, '..', '..', 'context.pickle'),
    ]

    for path in search_paths:
        if os.path.exists(path):
            print(f'Found context at: {path}')
            return load_context_from_pickle(path)

    latest_stage_context = find_latest_stage_context(
        [
            report_dir,
            os.path.join(report_dir, '..'),
            os.path.join(report_dir, '..', '..'),
        ]
    )
    if latest_stage_context:
        print(f'Found latest stage context at: {latest_stage_context}')
        return load_context_from_pickle(latest_stage_context)

    raise FileNotFoundError(
        f'Could not find context.pickle near {report_dir}. '
        'Provide explicit --context PATH or ensure context pickle exists.'
    )


def clear_matplotlib_caches() -> None:
    """Clear matplotlib's figure cache and CASA's internal caches.
    
    This helps ensure each benchmark run has a clean state.
    """
    import gc
    
    try:
        import matplotlib
        matplotlib.pyplot.close('all')
        # Clear matplotlib figure manager's figure cache
        if hasattr(matplotlib.pyplot, 'FigureManager'):
            matplotlib.pyplot.FigureManager.figs.clear()
    except Exception:
        pass  # matplotlib may not be available or import may fail
    
    try:
        # Clear CASA's internal caches if available
        from casatools import image
        image().close()
    except Exception:
        pass  # CASA may not be available
    
    try:
        # Clear the summary module's chart caches if available
        from pipeline.infrastructure.displays import summary
        if hasattr(summary, '_chart_cache'):
            summary._chart_cache.clear()
    except Exception:
        pass
    
    # Force garbage collection to free cached objects
    gc.collect()


def benchmark_renderer(
    context: Any,
    num_runs: int = 10,
    num_warmup: int = 1,
    renderer_names: list[str] | None = None,
    reset_cache: bool = False,
    skip_origin_files: bool = False,
    preserve_metadata: bool = False,
    metadata_dir: str | None = None,
) -> dict[str, Any]:
    """Run weblog renderers multiple times and record timing statistics.

    Args:
        context: Pipeline Context object with results loaded.
        num_runs: Number of times to run the renderer suite.
        num_warmup: Number of warmup runs to discard before measuring.
        renderer_names: List of specific renderer names to test.
                       If None, benchmark all renderers.
        reset_cache: If True, reset renderer caches between runs.
        skip_origin_files: If True, temporarily disable origin file checks
                          in chart rendering to prevent caching from
                          previously computed plots.
        preserve_metadata: If True, preserve metadata across runs for reuse.
        metadata_dir: Directory to store shared metadata. If None, uses a temp dir.

    Returns:
        Dictionary mapping renderer names to timing statistics.
    """
    # Import here to avoid issues if pipeline not in path
    try:
        from pipeline.infrastructure.renderer import htmlrenderer
    except ImportError as e:
        print(f'Error: Could not import htmlrenderer: {e}', file=sys.stderr)
        sys.exit(1)

    # Unpickle results if they're proxies (required for renderers to access
    # attributes like .qa, .timestamps, .stage_number, etc.)
    if context.results and hasattr(context.results[0], 'read'):
        print('Unpickling result proxies...')
        context.results = [proxy.read() for proxy in context.results]
        print(f'Unpickled {len(context.results)} results')
    
    # If skip_origin_files is True, clear origin_ms to prevent caching from
    # previously computed plots in original MS locations
    if skip_origin_files and context.observing_run:
        for ms in context.observing_run.measurement_sets:
            ms.origin_ms = ms.name  # Set origin to self to disable origin file checks

    results = {}
    all_renderers = htmlrenderer.WebLogGenerator.renderers

    # Filter renderers by name if specified
    if renderer_names:
        renderers = [r for r in all_renderers
                     if r.__name__ in renderer_names]
        if not renderers:
            print(f'Warning: No renderers matched names: {renderer_names}',
                  file=sys.stderr)
            renderers = all_renderers
    else:
        renderers = all_renderers

    # Store original report_dir
    import tempfile
    original_report_dir = context.report_dir
    
    # Set up metadata preservation directory
    shared_metadata_dir = None
    if preserve_metadata:
        if metadata_dir:
            shared_metadata_dir = metadata_dir
            os.makedirs(shared_metadata_dir, exist_ok=True)
        else:
            import tempfile
            shared_metadata_dir = tempfile.mkdtemp(prefix='benchmark_metadata_')
        print(f'Preserving metadata in: {shared_metadata_dir}\n')
    
    # Run warmup cycles (discarded)
    if num_warmup > 0:
        print(f'Running {num_warmup} warmup cycle(s) (results discarded)...\n')
        for warmup_run in range(num_warmup):
            for renderer in renderers:
                # Each warmup gets its own isolated temp directory
                temp_report_dir = tempfile.mkdtemp(prefix=f'benchmark_warmup_{renderer.__name__}_')
                
                # Deep-copy context to clear any per-object caches
                warmup_context = copy.deepcopy(context)
                warmup_context.report_dir = temp_report_dir
                try:
                    renderer.render(warmup_context)
                except Exception:
                    pass  # Silently skip warmup errors
                finally:
                    shutil.rmtree(temp_report_dir, ignore_errors=True)
        print()

    print(f'Benchmarking {len(renderers)} renderers over {num_runs} runs...\n')

    try:
        for renderer in renderers:
            renderer_name = renderer.__name__

            times = []

            for run_num in range(num_runs):
                # Clear matplotlib and CASA caches before each run
                clear_matplotlib_caches()
                
                # For runs 2+, if preserving metadata, use shared metadata dir as report_dir
                # This allows metadata loading to work correctly (plot paths resolve properly)
                if preserve_metadata and shared_metadata_dir and run_num > 0:
                    # Reuse shared metadata dir for rendering - plots are already there
                    temp_report_dir = shared_metadata_dir
                    use_shared_dir = True
                else:
                    # Create isolated temp directory for this run
                    temp_report_dir = tempfile.mkdtemp(prefix=f'benchmark_{renderer_name}_run{run_num}_')
                    use_shared_dir = False

                # Deep-copy context to clear any per-object caches (e.g., ms._cache attributes)
                run_context = copy.deepcopy(context)
                run_context.report_dir = temp_report_dir

                # Reset caches if requested
                if reset_cache:
                    # Reset any known cache statistics
                    if hasattr(renderer, 'reset_cache_stats'):
                        renderer.reset_cache_stats()

                # Time the renderer
                start = time.perf_counter()
                try:
                    renderer.render(run_context)
                    elapsed = time.perf_counter() - start
                    times.append(elapsed)

                except Exception as e:
                    print(f'  Run {run_num + 1}: ERROR - {e}',
                          file=sys.stderr)
                    continue
                finally:
                    # Clean up temp directory only if it's not the shared metadata dir
                    if not use_shared_dir:
                        shutil.rmtree(temp_report_dir, ignore_errors=True)

                print(f'  {renderer_name} run {run_num + 1}/{num_runs}: '
                      f'{elapsed:.3f}s')

            if times:
                results[renderer_name] = {
                    'times': times,
                    'mean': statistics.mean(times),
                    'median': statistics.median(times),
                    'stdev': statistics.stdev(times) if len(times) > 1 else 0.0,
                    'min': min(times),
                    'max': max(times),
                    'runs': len(times),
                }
                print(f'  {renderer_name} summary: '
                      f'mean={results[renderer_name]["mean"]:.3f}s, '
                      f'median={results[renderer_name]["median"]:.3f}s, '
                      f'stdev={results[renderer_name]["stdev"]:.3f}s\n')

    finally:
        # Restore original report_dir
        context.report_dir = original_report_dir
        
        # Clean up temp metadata dir if we created one
        if preserve_metadata and not metadata_dir and shared_metadata_dir:
            shutil.rmtree(shared_metadata_dir, ignore_errors=True)
    
    return results


def benchmark_single_renderer(
    context: Any,
    renderer_name: str,
    num_runs: int = 10,
    num_warmup: int = 1,
    reset_cache: bool = False,
    skip_origin_files: bool = False,
    preserve_metadata: bool = False,
    metadata_dir: str | None = None,
) -> dict[str, Any]:
    """Benchmark a single renderer in isolation.

    Args:
        context: Pipeline Context object.
        renderer_name: Name of the renderer class to benchmark.
        num_runs: Number of times to run.
        num_warmup: Number of warmup runs to discard.
        reset_cache: If True, reset caches between runs.
        skip_origin_files: If True, disable origin file checks.
        preserve_metadata: If True, preserve metadata across runs for reuse.
        metadata_dir: Directory to store shared metadata. If None, uses a temp dir.

    Returns:
        Timing statistics dictionary.
    """
    try:
        from pipeline.infrastructure.renderer import htmlrenderer
    except ImportError as e:
        print(f'Error: Could not import htmlrenderer: {e}', file=sys.stderr)
        sys.exit(1)

    # Find the renderer
    renderer = None
    for r in htmlrenderer.WebLogGenerator.renderers:
        if r.__name__ == renderer_name:
            renderer = r
            break

    if not renderer:
        print(f'Error: Renderer not found: {renderer_name}', file=sys.stderr)
        available = [r.__name__
                     for r in htmlrenderer.WebLogGenerator.renderers]
        print(f'Available renderers:\n  ' + '\n  '.join(available),
              file=sys.stderr)
        sys.exit(1)

    return benchmark_renderer(
        context,
        num_runs=num_runs,
        num_warmup=num_warmup,
        renderer_names=[renderer_name],
        reset_cache=reset_cache,
        skip_origin_files=skip_origin_files,
        preserve_metadata=preserve_metadata,
        metadata_dir=metadata_dir,
    )


def print_summary(results: dict[str, Any]) -> None:
    """Print formatted summary of benchmark results.

    Args:
        results: Dictionary of renderer timing statistics.
    """
    if not results:
        print('No results to display.')
        return

    print('=' * 80)
    print('BENCHMARK SUMMARY')
    print('=' * 80)

    # Sort by mean time, descending
    sorted_results = sorted(results.items(),
                            key=lambda x: x[1]['mean'],
                            reverse=True)

    print(f'{"Renderer":<40} {"Mean":>10} {"Median":>10} '
          f'{"StDev":>10} {"Min":>10} {"Max":>10}')
    print('-' * 80)

    total_mean = 0
    for name, stats in sorted_results:
        print(f'{name:<40} {stats["mean"]:>10.3f}s {stats["median"]:>10.3f}s '
              f'{stats["stdev"]:>10.3f}s {stats["min"]:>10.3f}s '
              f'{stats["max"]:>10.3f}s')
        total_mean += stats['mean']

    print('-' * 80)
    print(f'{"TOTAL":<40} {total_mean:>10.3f}s')
    print('=' * 80)


def save_results(
    results: dict[str, Any],
    output_path: str,
    meta: dict[str, Any] | None = None,
) -> None:
    """Save benchmark results to JSON file.

    Args:
        results: Dictionary of timing statistics.
        output_path: Path to output JSON file.
        meta: Optional metadata about the benchmark run.
    """
    payload = dict(results)
    if meta:
        payload['__meta__'] = meta
    with open(output_path, 'w') as f:
        json.dump(payload, f, indent=2)
    print(f'\nResults saved to: {output_path}')


def main() -> None:
    """Main entry point for benchmark script."""
    parser = argparse.ArgumentParser(
        description='Benchmark weblog renderer performance.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Benchmark all renderers using saved context
  python benchmark_renderer.py --context /path/to/context.pickle --runs 10

  # Benchmark specific renderers
  python benchmark_renderer.py --context /path/to/context.pickle \\
    --renderers T1_1Renderer T1_2Renderer --runs 5

  # Use weblog report directory to find context
  python benchmark_renderer.py --report-dir /path/to/weblog/output --runs 5

  # Save results to JSON
  python benchmark_renderer.py --context /path/to/context.pickle \\
    --output results.json --runs 10
        '''
    )

    parser.add_argument('--context',
                        help='Path to pickled Context object')
    parser.add_argument('--report-dir',
                        help='Path to weblog report directory (searches for '
                             'context.pickle)')
    parser.add_argument('--output',
                        help='Output file for JSON results (optional)')
    parser.add_argument('--runs', type=int, default=10,
                        help='Number of benchmark runs (default: 10)')
    parser.add_argument('--warmup', type=int, default=1,
                        help='Number of warmup runs to discard (default: 1)')
    parser.add_argument('--verify', action='store_true',
                        help='Run each renderer once to verify setup, then exit')
    parser.add_argument('--renderers', nargs='+',
                        help='Specific renderer names to benchmark '
                             '(default: all)')
    parser.add_argument('--single',
                        help='Benchmark single renderer by name')
    parser.add_argument('--reset-cache', action='store_true',
                        help='Reset renderer caches between runs')
    parser.add_argument('--skip-origin-files', action='store_true',
                        help='Disable origin file checks in renderers to prevent '
                             'caching from previously computed plots')
    parser.add_argument('--preserve-metadata', action='store_true',
                        help='Preserve metadata across runs to measure reuse speedup')
    parser.add_argument('--metadata-dir', type=str, default=None,
                        help='Directory to store shared metadata (default: temp dir)')
    parser.add_argument('--list-renderers', action='store_true',
                        help='List available renderers and exit')

    args = parser.parse_args()

    # Handle --list-renderers
    if args.list_renderers:
        try:
            from pipeline.infrastructure.renderer import htmlrenderer
        except ImportError as e:
            print(f'Error: Could not import htmlrenderer: {e}',
                  file=sys.stderr)
            sys.exit(1)

        print('Available renderers:')
        for r in htmlrenderer.WebLogGenerator.renderers:
            print(f'  {r.__name__}')
        return

    # Determine context source
    if args.context:
        context = load_context_from_pickle(args.context)
    elif args.report_dir:
        context = get_context_with_results(args.report_dir)
    else:
        parser.error('Either --context or --report-dir must be specified')

    # Handle --verify mode
    if args.verify:
        print('VERIFICATION MODE: Running each renderer once...\n')
        if args.single:
            verify_results = benchmark_single_renderer(
                context,
                args.single,
                num_runs=1,
                num_warmup=0,
                reset_cache=False,
                skip_origin_files=args.skip_origin_files,
                preserve_metadata=args.preserve_metadata,
                metadata_dir=args.metadata_dir,
            )
        else:
            verify_results = benchmark_renderer(
                context,
                num_runs=1,
                num_warmup=0,
                renderer_names=args.renderers,
                reset_cache=False,
                skip_origin_files=args.skip_origin_files,
                preserve_metadata=args.preserve_metadata,
                metadata_dir=args.metadata_dir,
            )

        print_summary(verify_results)

        total_time = sum(stats['mean'] for stats in verify_results.values())
        estimated_full = total_time * args.runs
        print(
            f'\nEstimated time for {args.runs} runs: {estimated_full:.1f}s '
            f'({estimated_full/60:.1f} minutes)'
        )
        print('\nVerification complete. Run without --verify to perform full benchmark.')
        return

    # Run benchmark
    if args.single:
        results = benchmark_single_renderer(
            context,
            args.single,
            args.runs,
            args.warmup,
            args.reset_cache,
            args.skip_origin_files,
            args.preserve_metadata,
            args.metadata_dir,
        )
    else:
        results = benchmark_renderer(
            context,
            args.runs,
            args.warmup,
            args.renderers,
            args.reset_cache,
            args.skip_origin_files,
            args.preserve_metadata,
            args.metadata_dir,
        )

    # Print and save results
    print_summary(results)

    if args.output:
        renderers = args.renderers or ([args.single] if args.single else 'all')
        meta = {
            'runs': args.runs,
            'warmup': args.warmup,
            'renderers': renderers,
            'reset_cache': args.reset_cache,
            'skip_origin_files': args.skip_origin_files,
            'preserve_metadata': args.preserve_metadata,
            'metadata_dir': args.metadata_dir,
            'context': args.context,
            'report_dir': args.report_dir,
            'timestamp_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        }
        save_results(results, args.output, meta)


if __name__ == '__main__':
    main()
