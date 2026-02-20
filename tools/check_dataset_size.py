#!/usr/bin/env python3
'''
Quick check if a dataset is suitable for context optimization testing.
Looks for existing context pickle and checks its size.
'''

import sys
from pathlib import Path


def check_dataset(working_dir: str) -> None:
    '''Check if dataset has large enough context for testing.'''
    path = Path(working_dir)
    
    if not path.exists():
        print(f'Directory not found: {working_dir}')
        sys.exit(1)
    
    # Find context pickle(s)
    context_files = sorted(path.glob('*.context'))

    if not context_files:
        print('No context pickle found. Dataset not yet processed.')
        print('Run at least through hifa_importdata to generate initial context.')
        sys.exit(1)

    candidates = []
    for context_file in context_files:
        size_mb = context_file.stat().st_size / (1024 * 1024)
        pipeline_dir = path / context_file.stem
        saved_state = pipeline_dir / 'saved_state'
        stage_count = 0
        if saved_state.exists():
            stage_count = len(list(saved_state.glob('result-stage*.pickle')))
        candidates.append((context_file, size_mb, saved_state if saved_state.exists() else None, stage_count))

    # Prefer the context with the most stages; break ties by largest size
    candidates.sort(key=lambda item: (item[3], item[1]), reverse=True)
    context_file, size_mb, selected_saved_state, selected_stage_count = candidates[0]

    if len(candidates) > 1:
        print('Multiple context pickles found. Selecting the best candidate:')
        for context_file_item, size_mb_item, saved_state_item, stage_count_item in candidates:
            stage_label = f'{stage_count_item} stages' if stage_count_item else 'no stages'
            saved_state_label = saved_state_item.name if saved_state_item else 'no saved_state'
            print(f'  {context_file_item.name}: {size_mb_item:.2f} MB, {stage_label}, {saved_state_label}')
        print()

    print(f'Context pickle: {context_file.name}')
    print(f'Size: {size_mb:.2f} MB')
    print()
    
    if size_mb < 5:
        print('⚠️  SMALL dataset (<5 MB context)')
        print('   Phase 3/4 improvements unlikely to be measurable.')
        print('   Consider testing on larger dataset.')
    elif size_mb < 20:
        print('✓  MEDIUM dataset (5-20 MB context)')
        print('   May show modest improvements.')
    else:
        print('✓✓ LARGE dataset (>20 MB context)')
        print('   Good candidate for testing Phase 3/4 benefits.')
    
    print()
    print('Stage count check:')
    
    # Check for result pickles in saved_state directories
    saved_state_dirs = []
    if selected_saved_state is not None:
        saved_state_dirs = [selected_saved_state]
    else:
        saved_state_dirs = list(path.glob('pipeline-*/saved_state'))
        if not saved_state_dirs:
            saved_state_dirs = list(path.glob('saved_state'))
    
    stage_count = 0
    large_results = []
    
    if saved_state_dirs:
        saved_state = saved_state_dirs[0]
        result_pickles = sorted(saved_state.glob('result-stage*.pickle'))
        stage_count = len(result_pickles)
        
        print(f'  Found {stage_count} stages in {saved_state.relative_to(path)}')
        
        # Find large result pickles (>100 MB) - prime candidates for slimming
        for result in result_pickles:
            size_mb = result.stat().st_size / (1024 * 1024)
            if size_mb > 100:
                large_results.append((result.name, size_mb))
        
        if large_results:
            print(f'  🔥 Found {len(large_results)} result pickles >100 MB:')
            for name, size_mb in sorted(large_results, key=lambda x: x[1], reverse=True)[:5]:
                print(f'     {name}: {size_mb:.1f} MB')
            print('     ^ Prime candidates for Phase 4 results slimming!')
    else:
        # Fallback to XML files if no saved_state
        results = list(path.glob('*-results_*.xml'))
        stage_count = len(results)
        print(f'  Found {stage_count} result XML files')
    
    if stage_count < 30:
        print('  ⚠️  Short pipeline (<30 stages)')
    else:
        print('  ✓  Long pipeline (30+ stages)')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: python check_dataset_size.py <working-directory>')
        print('Example: python check_dataset_size.py /path/to/ALMA-dataset/working')
        sys.exit(1)
    
    check_dataset(sys.argv[1])
