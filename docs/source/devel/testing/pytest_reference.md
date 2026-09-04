# Pytest reference

## Custom options

Pipeline registers several custom pytest options. To list them all:

```console
casa_python -m pytest --help
```

Here `casa_python` is an alias for `PYTHONNOUSERSITE=1 ${casa_dir}/bin/python3`.

```{list-table}
:header-rows: 1
:widths: 20 80

* - Option
  - Description
* - ``--collect-tests``
  - Collect tests and export node IDs to ``collected_tests.txt``
* - ``--nologfile``
  - Suppress CASA log file creation in the working directory. Note: for regression tests,
    logs are still generated inside each test's ``working/`` subdirectory and appear in
    the test weblog. Mainly useful when frequently running unit tests to keep the repo
    directory clean.
* - ``--pyclean``
  - Delete ``.pyc`` files before running to reproduce compile-time warnings
* - ``--compare-only``
  - Skip pipeline execution; compare against existing working-directory results only
* - ``--remove-workdir``
  - Remove individual working directories after regression tests complete
* - ``--longtests``
  - Enable longer-running tests excluded by default
* - ``--data-directory``
  - Path to large input data files; defaults to ``/lustre/cv/projects/pipeline-test-data/regression-test-data/``
```

### Examples

Collect test node IDs without running any tests:

```console
casa_python -m pytest -v --collect-tests <pipeline_dir>
```

Run with parallel execution, suppressing CASA log file creation (keeps the repo directory
clean):

```console
casa_python -m pytest -n 4 -v --pyclean --nologfile <pipeline_dir>
```

Re-evaluate results from a previous run without re-executing the pipeline:

```console
xvfb-run casa --nogui --nologger --log2term --agg -c \
    "import pytest; pytest.main(['-vv', '-m alma and fast', '--compare-only', '<pipeline_dir>'])"
```

Specify a custom data directory for large datasets:

```console
xvfb-run casa --nogui --nologger --log2term --agg -c \
    "import pytest; pytest.main(['-vv', '-m alma and slow', \
     '--data-directory=/users/kberry/big_data_directory/', '<pipeline_dir>'])"
```

## Custom markers

Markers are defined in `pyproject.toml`. Many are applied automatically by `conftest.py`
based on the test's file path; others must be added manually per test function.

Auto-applied markers:

```{list-table}
:header-rows: 1
:widths: 20 80

* - Marker
  - Applied to
* - ``regression``
  - All tests under ``tests/regression/``
* - ``component``
  - All tests under ``tests/component/``
* - ``unit``
  - All other tests (fallback)
* - ``fast``
  - Tests under ``tests/regression/fast/``
* - ``slow``
  - Tests under ``tests/regression/slow/``
* - ``alma``
  - Regression tests with ``alma`` in the file path
* - ``nobeyama``
  - Regression tests with ``nobeyama`` in the file path
* - ``vlass``
  - Regression tests with ``vlass`` in the file path
* - ``vla``
  - Regression tests with ``vla`` (but not ``vlass``) in the file path
* - ``sd``
  - Regression tests with ``sd`` in the file path
* - ``interferometry``
  - Regression tests with ``if`` in the file path
```

Manually applied markers (added with ``@pytest.mark.<name>`` per test function):

```{list-table}
:header-rows: 1
:widths: 20 80

* - Marker
  - Purpose
* - ``twelve``
  - 12 m ALMA test
* - ``seven``
  - 7 m ALMA test
* - ``mpi``
  - Test recommended for an MPI-enabled CASA session; use ``-m mpi`` or ``-m 'not mpi'`` to control execution
* - ``importdata``
  - Component test involving data import
* - ``selfcal``
  - Component test involving self-calibration
* - ``makeimages``
  - Component test involving imaging
```

Select tests with `-m`:

```console
# run only VLASS tests
xvfb-run casa --nogui --nologger --log2term --agg \
    -c "import pytest; pytest.main(['-vv', '-m vlass', '--longtests', '<pipeline_dir>'])"

# combine: fast VLA tests only
xvfb-run casa --nogui --nologger --log2term --agg \
    -c "import pytest; pytest.main(['-vv', '-m vla and fast', 'pipeline'])"

# negate: everything except VLASS
xvfb-run casa --nogui --nologger --log2term --agg \
    -c "import pytest; pytest.main(['-vv', '-m not vlass', 'pipeline'])"

# regression tests, excluding slow ones
PYTHONNOUSERSITE=1 ${casa_dir}/bin/python3 -m pytest -m "regression and not slow" tests/

# component tests involving self-calibration
PYTHONNOUSERSITE=1 ${casa_dir}/bin/python3 -m pytest -m "component and selfcal" tests/component/
```

## `casa-data` and `pipeline-testdata`

See {doc}`test_environment` for configuring `casa-data` and `pipeline-testdata` paths.
