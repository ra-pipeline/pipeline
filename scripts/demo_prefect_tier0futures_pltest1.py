#!/usr/bin/env python3
"""Run a recipereducer-based pipeline execution with Prefect and Dask.

Usage:
    Must be run within the experimental ('exp') pixi environment, which contains
    the necessary Dask and Prefect dependencies.

    Option 1 (Run directly):
        pixi run -e exp python scripts/demo_prefect_tier0futures_pltest1.py

    Option 2 (Interactive shell):
        pixi shell -e exp
        python scripts/demo_prefect_tier0futures_pltest1.py

    Once running, you can monitor the flow in the local Prefect dashboard:
        http://127.0.0.1:4200
"""

import os
import sys
from contextlib import contextmanager

# --- Configuration -----------------------------------------------------------
raw_dir = '/home/rxue/Workspace/zfs/nrao/tests/pipeline-testdata/pl-unittest'
proc_dir = '/zfs/data2/Workspace/nrao/tests/projs/pltest1/prefect_tier0future/'
prefect_api_url = 'http://127.0.0.1:4200/api'  # set to None to use ephemeral in-process API
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
    if prefect_api_url:
        os.environ.setdefault('PREFECT_API_URL', prefect_api_url)

    from pipeline.infrastructure.utils import work_directory
    import pipeline.recipereducer

    # dask_jobqueue installs a SIGINT handler (via runner.py) that calls sys.exit(),
    # which triggers atexit → stop_daskcluster() → cluster.close(), hanging in
    # distributed.utils.sync().  Override it here (after imports, so we win) with
    # os._exit() to skip atexit cleanup and exit immediately on Ctrl+C.
    import signal

    signal.signal(signal.SIGINT, lambda *_: os._exit(130))

    with work_directory(os.path.join(proc_dir, 'working'), create=True, cleanup=True, reset=True):
        with capture_output('reduc.log'):
            pipeline.recipereducer.reduce(
                vis=[os.path.join(raw_dir, 'uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.ms')],
                procedure='tests/test_procedure_hifa_calimage_tier0.xml', 
                loglevel='debug'
            )