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
store_dir = '/lustre/cv/users/rxue/datasets/alma_if/'
ppr_file = store_dir + '2016.1.00053.S/rawdata/PPR_uid___A001_X889_X107_tier0.xml'
raw_dir = store_dir + '2016.1.00053.S/rawdata/'
work_dir = '/lustre/naasc/sciops/comm/rxue/tests/projs/2016.1.00053.S/prefect_tier0futures/'
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

    from pipeline.infrastructure.executeppr import executeppr
    from pipeline.infrastructure.utils import work_directory

    # dask_jobqueue installs a SIGINT handler (via runner.py) that calls sys.exit(),
    # which triggers atexit → stop_daskcluster() → cluster.close(), hanging in
    # distributed.utils.sync().  Override it here (after imports, so we win) with
    # os._exit() to skip atexit cleanup and exit immediately on Ctrl+C.
    import signal

    signal.signal(signal.SIGINT, lambda *_: os._exit(130))

    with work_directory(work_dir, create=True, cleanup=True, reset=True, subdir=True):
        # Symlink rawdata directory into work_dir so executeppr can find it
        rawdata_link = os.path.join(work_dir, 'rawdata')
        if os.path.islink(rawdata_link):
            os.unlink(rawdata_link)
        elif os.path.isdir(rawdata_link):
            import datetime

            ts = datetime.datetime.now().strftime('%Y%m%dT%H%M%S')
            backup = rawdata_link + f'_bak_{ts}'
            os.rename(rawdata_link, backup)
            print(f'  backed up existing rawdata dir -> {backup}')
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
