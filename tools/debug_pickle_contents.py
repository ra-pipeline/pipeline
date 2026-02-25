#!/usr/bin/env python3
"""Debug script to inspect pickle contents and diagnose 512-byte issue."""

import pickle
import sys
from pathlib import Path


def inspect_pickle(pickle_path: Path) -> None:
    """Load and inspect a result pickle."""
    print(f'\n{"=" * 80}')
    print(f'Inspecting: {pickle_path.name}')
    print(f'Size: {pickle_path.stat().st_size:,} bytes')
    print('=' * 80)
    
    try:
        with open(pickle_path, 'rb') as f:
            result = pickle.load(f)
        
        print(f'Type: {type(result).__name__}')
        print(f'Module: {type(result).__module__}')
        
        # Check basic attributes
        attrs = ['stage_number', 'task', '_transient_fields', 'plots', 'metadata']
        for attr in attrs:
            if hasattr(result, attr):
                val = getattr(result, attr)
                if isinstance(val, (list, dict, set)):
                    print(f'{attr}: {type(val).__name__} with {len(val)} items')
                else:
                    print(f'{attr}: {val}')
            else:
                print(f'{attr}: <not present>')
        
        # List all attributes
        all_attrs = [a for a in dir(result) if not a.startswith('_')]
        print(f'\nAll public attributes ({len(all_attrs)}):')
        print(', '.join(sorted(all_attrs)))
        
        # Check for __dict__
        if hasattr(result, '__dict__'):
            print(f'\n__dict__ keys ({len(result.__dict__)}):')
            for key, val in sorted(result.__dict__.items()):
                if isinstance(val, (list, dict)):
                    print(f'  {key}: {type(val).__name__}[{len(val)}]')
                else:
                    val_repr = str(val)[:60]
                    print(f'  {key}: {val_repr}')
    
    except Exception as e:
        print(f'ERROR loading pickle: {e}')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python debug_pickle_contents.py <path-to-saved_state>')
        print('Example: python debug_pickle_contents.py pipeline-procedure_hifa_calimage/saved_state/')
        sys.exit(1)
    
    saved_state_dir = Path(sys.argv[1])
    
    if not saved_state_dir.exists():
        print(f'ERROR: Directory not found: {saved_state_dir}')
        sys.exit(1)
    
    # Find all result pickles
    pickles = sorted(saved_state_dir.glob('result-stage*.pickle'))
    
    if not pickles:
        print(f'ERROR: No result-stage*.pickle files found in {saved_state_dir}')
        sys.exit(1)
    
    print(f'Found {len(pickles)} result pickles')
    
    # Inspect first 5 and last 5
    to_inspect = pickles[:3] + pickles[-2:]
    
    for pickle_path in to_inspect:
        inspect_pickle(pickle_path)
