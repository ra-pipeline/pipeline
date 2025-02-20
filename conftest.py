"""This file contains some pipeline-specific pytest configuration settings."""

import os
import pathlib

import pytest

from casatasks import casalog


def pytest_addoption(parser):
    """Add custom pytest command-line options."""

    nologfile_help = r"""
        Prevents CASA from creating log files, equivalent to running `casa --nologfile`.
        Note: If using regression-tester.py, CASA log files will still be generated in individual `working/`
        directories and included in test weblogs. In general, this option is recommended for manual or frequent
        unit test runs to keep your local repository clean.
        """
    parser.addoption("--collect-tests", action="store_true", default=False,
                     help="Collect test cases and export their node IDs to `collected_tests.txt`.")
    parser.addoption("--nologfile", action="store_true", default=False,
                     help=nologfile_help)
    parser.addoption("--pyclean", action="store_true", default=False,
                     help="Removes .pyc files to reproduce warnings that only appear when bytecode is compiled.")
    parser.addoption("--remove-workdir", action="store_true", default=False,
                     help="Remove individual working directories after regression testing.")
    parser.addoption("--longtests", action="store_true", default=False, help="Run longer-duration tests.")
    parser.addoption("--compare-only", action="store_true", default=False,
                     help="Skips executing the test recipe and instead performs a comparison using results from a previous test run.")
    parser.addoption("--data-directory", action="store", default="/lustre/cv/projects/pipeline-test-data/regression-test-data/",
                     help="Specify directory where larger test data files are stored.")
    parser.addoption("--dbservice", action="store_true", default=False,
                     help="Enables the online flux service. (Disabled by default.)")

def pytest_sessionstart(session):
    """Prepare pytest session."""

    # redirect casalog for the master process, if requested
    if session.config.getoption('--nologfile') and not hasattr(session.config, 'workerinput'):
        redirect_casalog()

    # clean up .pyc to reproduce certain warnings only when the bytecode is compiled, e.g,
    #   invalid escape sequence warnings
    if session.config.getoption('--pyclean'):
        for p in pathlib.Path('.').rglob('*.py[co]'):
            p.unlink()
        for p in pathlib.Path('.').rglob('__pycache__'):
            p.rmdir()


def pytest_configure(config):
    # pytest.config (global) is deprecated from pytest ver>5.0.
    # we save a copy of its content under `pytest.pytestconfig` for an easy access from helper classes.
    pytest.pytestconfig = config


def pytest_collection_finish(session):
    """Exit after collection if only collect test."""

    if session.config.getoption('--collect-tests'):
        with open('collected_tests.txt', 'w') as f:
            for item in session.items:
                node_id=item.nodeid.split("::")
                node_id[0]=str(item.fspath)
                node_id="::".join(node_id)
                print(node_id)
                f.write(node_id+'\n')
        pytest.exit('Tests collection completed.')


def pytest_collection_modifyitems(config, items):
    if config.getoption("--longtests"):
        # --longtests given in cli: do not skip slow tests
        return
    skip_slow = pytest.mark.skip(reason="need --longtests option to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)


@pytest.fixture(scope="session", autouse=True)
def redirect_casalog_for_workers(request):
    """Remove casalog for each worker, if requested."""
    
    if request.config.getoption("--nologfile") and hasattr(request.config, 'workerinput'):
        redirect_casalog()


def redirect_casalog():
    """Redirect casalog to /dev/null before executeting tests.

    We clean up the default logfile potentially created from the CASA session initialization,
    and then redirect logging to `/dev/null`.
    """
    last_casalog = casalog.logfile()
    if last_casalog != '/dev/null':
        try:
            os.remove(last_casalog)
        except OSError as e:
            pass
        casalog.setlogfile('/dev/null')

