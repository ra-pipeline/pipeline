#!/usr/bin/env python3
"""Run a PPR-based pipeline reduction via executeppr with Prefect and Dask.

Usage:
    Must be run within the experimental ('exp') pixi environment, which contains
    the necessary Dask and Prefect dependencies.

    Option 1 (Run directly):
        pixi run -e exp python scripts/demo_prefect_tier0futures.py

    Option 2 (Interactive shell):
        pixi shell -e exp
        python scripts/demo_prefect_tier0futures.py

    Once running, you can monitor the flow in the local Prefect dashboard:
        http://127.0.0.1:4200
"""
import os
import sys
from contextlib import contextmanager

# --- Configuration -----------------------------------------------------------
ppr_file = '/zfs/data0/Workspace/nrao/datasets/alma_if/2024.1.00848.S/rawdata/PPR_uid___A001_X3788_X780e_tier0.xml'
raw_dir = '/zfs/data0/Workspace/nrao/datasets/alma_if/2024.1.00848.S/rawdata'
work_dir = '/home/rxue/Workspace/scratch/nrao/tests/projs/2024.1.00848.S/prefect_tier0futures'
# -----------------------------------------------------------------------------


@contextmanager
def capture_output(file_path):
    from wurlitzer import pipes, STDOUT
    with open(file_path, 'w') as f, pipes(f, stderr=STDOUT):
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = f, f
        try:
            yield
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr


if __name__ == '__main__':
    # Pipeline imports MUST be inside the guard because:
    # - `import pipeline` triggers pipeline/__init__.py
    # - With autostart=true, that calls start_daskcluster()
    # - LocalCluster(processes=True) uses multiprocessing.spawn
    # - spawn re-imports __main__, which must have finished bootstrapping
    os.environ['PIPELINE_USE_PREFECT'] = '1'

    from pipeline.infrastructure.executeppr import executeppr
    from pipeline.infrastructure.utils import work_directory

    with work_directory(work_dir, create=True, cleanup=True, reset=True, subdir=True):
        # Symlink rawdata directory into work_dir so executeppr can find it
        rawdata_link = os.path.join(work_dir, 'rawdata')
        if not os.path.exists(rawdata_link):
            os.symlink(raw_dir, rawdata_link)
            print(f'  symlink: rawdata -> {raw_dir}')
        with capture_output('reduc.log'):
            executeppr(
                ppr_file,
                importonly=False,
                loglevel='info',
                plotlevel='summary',
                interactive=False,
            )
