## Unit tests

The instruction of writing/running pipeline unit tests is described in [PIPE-862](https://open-jira.nrao.edu/browse/PIPE-862). Some tips for running local tests are below:

To invoke unit tests within the pipeline repo directory,

```console
PYTHONNOUSERSITE=1 ${casa_dir}/bin/python3 -m pytest -v --pyclean .
```

Alternatively, use

```console
${casa_dir}/bin/casa --nogui --nologger --agg --nologfile -c "import pytest; pytest.main(['-v', '--pyclean', '.'])"
```

The CASA call version will use `casashell` (i.e., `python3 -m casashell`), which might show slightly different results.
The `--nologfile` (equivalent to `--logfile /dev/null`) here can prevent generating CASA log files in your pipeline repository directory.

If [`pytest-xdist`](https://pytest-xdist.readthedocs.io/en/latest) and [`pytest-cov`](https://pytest-cov.readthedocs.io/en/latest/config.html) are avilable, you can also try:

```console
PYTHONNOUSERSITE=1 ${casa_dir}/bin/python3 -m pytest -n 4 -v --cov=pipeline --cov-report=html .
```

or

```console
${casa_dir}/bin/casa --nogui --nologger --agg --nologfile -c "import pytest; pytest.main(['-v', '.', '-n', '4'])"
```

On a multi-core system, `pytest-xdist` can speed things up significantly, when the parallelization doesn't create a memory/io-bound situation. This is usually true for a light-weight test collection (e.g. unit tests), e.g.,

    walltime   0m21.744s # with pytest-xdist
    walltime   2m13.076s # without pytest-xdist

A summary of various test frameworks and tools is available in [PIPE-806](https://open-jira.nrao.edu/browse/PIPE-806).

## Regression tests

See https://open-confluence.nrao.edu/display/PL/Regression+Testing for details

To add the *xdist* flavor to your local regression run, one can try:

```console
xvfb-run -d ${casa_dir}/bin/casa --nogui --nologger --agg -c \
    "import pytest; pytest.main(['-vv', '--junitxml=regression-results.xml', '-n', '4', '<pipeline_dir>/pipeline/infrastructure/utils/regression-tester.py'])"
```

Here are some additional examples to run selected tests using their [node IDs or custom makers](https://docs.pytest.org/en/latest/example/markers.html):

```console
# select a single test using its node ID
xvfb-run -d ${casa_dir}/bin/casa --nogui --nologger --agg -c \
    "import pytest; pytest.main(['-vv', '--junitxml=regression-results.xml', '<pipeline_dir>/pipeline/infrastructure/utils/regression-tester.py::test_uid___A002_X85c183_X36f_SPW15_23__PPR__regression'])"
```

```console
# select a group of tests using the test marker `hifa`
xvfb-run -d ${casa_dir}/bin/casa --nogui --nologger --agg -c \
    "import pytest; pytest.main(['-vv', '--junitxml=regression-results.xml', '-m', 'hifa', '<pipeline_dir>/pipeline/infrastructure/utils/regression-tester.py'])"
```

```console
# select all tests with `mg2_20170525142607_180419` in the test function names
xvfb-run -d ${casa_dir}/bin/casa --nogui --nologger --agg -c \
    "import pytest; pytest.main(['-vv', '--junitxml=regression-results.xml', '-k', 'mg2_20170525142607_180419', '<pipeline_dir>/pipeline/infrastructure/utils/regression-tester.py'])"
```

Alternatively, if you want to figure out the coverage of a single regression test and also prefer to directly call CASA's python interpreter (therefore skip the `casashell` layer and .casa/startup.py):

```console
PYTHONNOUSERSITE=1 xvfb-run -d ${casa_dir}/bin/python3 -m pytest -v --pyclean --cov=pipeline --cov-report=html \
    ${pipeline_dir}/pipeline/infrastructure/utils/regression-tester.py::test_uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small__procedure_hifa_calimage__regression
```
The coverage report will be saved as `htmlcov/index.html`. A similar call can be issued to report the test coverage of the entire regression test suite, although such run will take much longer. 

## Custom pytest options

Pipeline has several pytest custom options, which can be found by invoking `--help` inside a repository directory.

```console
casa_python -m pytest --help
...
custom options:
  --collect-tests       collect tests and export test node ids to a plain text file `collected_tests.txt`
  --nologfile           do not create CASA log files, equivalent to 'casa --nologfile'
  --pyclean             clean up .pyc to reproduce certain warnings only issued when the bytecode is compiled.
...
```

Here, `casa_python` is an alias to `PYTHONNOUSERSITE=1 ${casa_dir}/bin/python3`.

For example, if you only want to generate a list of test node ids for existing regression tests, try

```console
casa_python -m pytest -v --collect-tests pipeline/infrastructure/utils/regression-tester.py
```

On the other hand, one can use the `--nologfile` option (built in `conftest.py`), to avoid `casa-*log` files spamming your repo working directory.

```console
casa_python -m pytest -n 4 -v --pyclean --nologfile .
```
