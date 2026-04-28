#!/usr/bin/env python3
"""Run a PPR-based pipeline reduction via executeppr with Prefect and Dask.

Usage:
    Must be run within the experimental ('exp') pixi environment, which contains
    the necessary Dask and Prefect dependencies.

    Option 1 (Run directly):
        pixi run -e exp python scripts/demo_prefect_tier0futures_polcal.py

    Option 2 (Interactive shell):
        pixi shell -e exp
        python scripts/demo_prefect_tier0futures_polcal.py

    Once running, you can monitor the flow in the local Prefect dashboard:
        http://127.0.0.1:4200
"""

import os

# --- Configuration -----------------------------------------------------------
testdata_dir = '/home/rxue/Workspace/zfs/nrao/tests/pipeline-testdata/pl-regressiontest/2022.1.00207.S'
proc_dir = '/zfs/data2/Workspace/nrao/tests/projs/2022.1.00207.S/prefect_tier0future/'

ppr_file = os.path.join(testdata_dir, 'PPR_tier0.xml')
raw_dir = testdata_dir
prefect_api_url = 'http://127.0.0.1:4200/api'  # set to None to use ephemeral in-process API
# -----------------------------------------------------------------------------


if __name__ == '__main__':
    # Pipeline imports MUST be inside the guard because:
    # - `import pipeline` triggers pipeline/__init__.py
    # - With autostart=true, that calls start_daskcluster()
    # - LocalCluster(processes=True) uses multiprocessing.spawn
    # - spawn re-imports __main__, which must have finished bootstrapping
    os.environ['PIPELINE_USE_PREFECT'] = '1'
    if prefect_api_url:
        os.environ.setdefault('PREFECT_API_URL', prefect_api_url)

    import casaconfig.config
    casaconfig.config.logfile='casa.log'

    from pipeline.infrastructure.executeppr import executeppr
    from pipeline.infrastructure.utils import work_directory

    # dask_jobqueue installs a SIGINT handler (via runner.py) that calls sys.exit(),
    # which triggers atexit → stop_daskcluster() → cluster.close(), hanging in
    # distributed.utils.sync().  Override it here (after imports, so we win) with
    # os._exit() to skip atexit cleanup and exit immediately on Ctrl+C.
    import signal

    signal.signal(signal.SIGINT, lambda *_: os._exit(130))

    with work_directory(proc_dir, create=True, cleanup=True, reset=False, subdir=True):
        # Symlink rawdata directory into proc_dir so executeppr can find it
        rawdata_link = os.path.join(proc_dir, 'rawdata')
        if os.path.islink(rawdata_link):
            os.unlink(rawdata_link)
        elif os.path.isdir(rawdata_link):
            try:
                os.rmdir(rawdata_link)
            except OSError:
                import datetime
                backup = f"{rawdata_link}_bak_{datetime.datetime.now():%Y%m%dT%H%M%S}"
                os.rename(rawdata_link, backup)
                print(f'  backed up existing rawdata dir -> {backup}')
        os.symlink(raw_dir, rawdata_link)
        print(f'symlink: rawdata -> {raw_dir}')
        executeppr(
            ppr_file,
            importonly=False,
            loglevel='info',
            plotlevel='summary',
            interactive=False,
        )
