#!/usr/bin/env python3
"""Run pipeline reductions with Prefect and Dask.

Three demo cases are supported:

  if2016   PPR-based, 2016.1.00053.S; paths resolved by hostname
  polcal   PPR-based, 2022.1.00207.S (polarization calibration)
  pltest1  recipereducer-based, pl-unittest data

Usage:
    Must be run within the experimental ('exp') pixi environment, which contains
    the necessary Dask and Prefect dependencies.

    Option 1 (Run directly):
        pixi run -e exp python scripts/demo_prefect_tier0futures.py <case>

    Option 2 (Interactive shell):
        pixi shell -e exp
        python scripts/demo_prefect_tier0futures.py <case>

    Once running, you can monitor the flow in the local Prefect dashboard:
        http://127.0.0.1:4200
"""

import argparse
import os
import socket
import sys
from contextlib import contextmanager

# --- Configuration -----------------------------------------------------------
_hostname = socket.gethostname()
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


def _setup_rawdata_symlink(proc_dir, raw_dir):
    rawdata_link = os.path.join(proc_dir, 'rawdata')
    if os.path.islink(rawdata_link):
        os.unlink(rawdata_link)
    elif os.path.isdir(rawdata_link):
        try:
            os.rmdir(rawdata_link)
        except OSError:
            import datetime

            backup = f'{rawdata_link}_bak_{datetime.datetime.now():%Y%m%dT%H%M%S}'
            os.rename(rawdata_link, backup)
            print(f'  backed up existing rawdata dir -> {backup}')
    os.symlink(raw_dir, rawdata_link)
    print(f'  symlink: rawdata -> {raw_dir}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Run a pipeline reduction with Prefect and Dask.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            'cases:\n'
            '  if2016   PPR-based, 2016.1.00053.S (hostname-dependent paths)\n'
            '  polcal   PPR-based, 2022.1.00207.S (polarization calibration)\n'
            '  pltest1  recipereducer-based, pl-unittest data'
        ),
    )
    parser.add_argument('case', choices=['if2016', 'polcal', 'pltest1'], help='demo case to run')
    args = parser.parse_args()

    # Pipeline imports MUST be inside the guard because:
    # - `import pipeline` triggers pipeline/__init__.py
    # - With autostart=true, that calls start_daskcluster()
    # - LocalCluster(processes=True) uses multiprocessing.spawn
    # - spawn re-imports __main__, which must have finished bootstrapping
    os.environ['PIPELINE_USE_PREFECT'] = '1'
    if prefect_api_url:
        os.environ.setdefault('PREFECT_API_URL', prefect_api_url)

    if args.case == 'polcal':
        import casaconfig.config

        casaconfig.config.logfile = 'casa.log'

    from pipeline.infrastructure.utils import work_directory

    # dask_jobqueue installs a SIGINT handler (via runner.py) that calls sys.exit(),
    # which triggers atexit → stop_daskcluster() → cluster.close(), hanging in
    # distributed.utils.sync().  Override it here (after imports, so we win) with
    # os._exit() to skip atexit cleanup and exit immediately on Ctrl+C.
    import signal

    signal.signal(signal.SIGINT, lambda *_: os._exit(130))

    if args.case == 'if2016':
        if _hostname.startswith('cvpost'):
            store_dir = '/lustre/cv/users/rxue/datasets/alma_if/'
            proc_dir = '/lustre/naasc/sciops/comm/rxue/tests/projs/2016.1.00053.S/prefect_tier0futures/'
        elif _hostname.startswith('xenon'):
            store_dir = '/zfs/data0/Workspace/nrao/datasets/alma_if/'
            proc_dir = '/zfs/data2/Workspace/nrao/tests/projs/2016.1.00053.S/prefect_tier0future/'
        else:
            raise RuntimeError(f'Unknown host {_hostname!r}: set store_dir and proc_dir manually')

        ppr_file = store_dir + '2016.1.00053.S/rawdata/PPR_uid___A001_X889_X107_tier0.xml'
        raw_dir = store_dir + '2016.1.00053.S/rawdata/'
        from pipeline.infrastructure.executeppr import executeppr

        with work_directory(proc_dir, create=True, cleanup=True, reset=True, subdir=True):
            _setup_rawdata_symlink(proc_dir, raw_dir)
            with capture_output('reduc.log'):
                executeppr(
                    ppr_file,
                    importonly=False,
                    loglevel='info',
                    plotlevel='summary',
                    interactive=False,
                )

    elif args.case == 'polcal':
        if _hostname.startswith('cvpost'):
            testdata_dir = '/users/rxue/Workspace/naasc/tests/pipeline-testdata/pl-regressiontest/2022.1.00207.S'
            proc_dir = '/users/rxue/Workspace/naasc/tests/projs/2022.1.00207.S/prefect_tier0future/'
        elif _hostname.startswith('xenon'):
            testdata_dir = '/home/rxue/Workspace/zfs/nrao/tests/pipeline-testdata/pl-regressiontest/2022.1.00207.S'
            proc_dir = '/zfs/data2/Workspace/nrao/tests/projs/2022.1.00207.S/prefect_tier0future/'
        else:
            raise RuntimeError(f'Unknown host {_hostname!r}: set store_dir and proc_dir manually')

        ppr_file = os.path.join(testdata_dir, 'PPR_tier0.xml')
        raw_dir = testdata_dir
        from pipeline.infrastructure.executeppr import executeppr

        with work_directory(proc_dir, create=True, cleanup=True, reset=False, subdir=True):
            _setup_rawdata_symlink(proc_dir, raw_dir)
            executeppr(
                ppr_file,
                importonly=False,
                loglevel='info',
                plotlevel='summary',
                interactive=False,
            )

    elif args.case == 'pltest1':
        if _hostname.startswith('cvpost'):
            raw_dir = '/users/rxue/Workspace/naasc/tests/pipeline-testdata/pl-unittest'
            proc_dir = '/users/rxue/Workspace/naasc/tests/projs/pltest1/prefect_tier0futures/'
        elif _hostname.startswith('xenon'):
            raw_dir = '/home/rxue/Workspace/zfs/nrao/tests/pipeline-testdata/pl-unittest'
            proc_dir = '/home/rxue/Workspace/scratch/nrao/tests/projs/pltest1/prefect_tier0future/'
        else:
            raise RuntimeError(f'Unknown host {_hostname!r}: set store_dir and proc_dir manually')
        import pipeline.recipereducer

        with work_directory(proc_dir, create=True, cleanup=True, reset=True, subdir=True):
            pipeline.recipereducer.reduce(
                vis=[os.path.join(raw_dir, 'uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.ms')],
                procedure='tests/test_procedure_hifa_calimage_tier0.xml',
                loglevel='debug',
            )
