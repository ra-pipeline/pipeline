# Pipeline testing

## Unit tests

The instruction of writing/running pipeline unit tests is described in [PIPE-862](https://open-jira.nrao.edu/browse/PIPE-862). Some tips for running local tests are below:

To invoke all unit tests in the pipeline repo directory,

```console
PYTHONNOUSERSITE=1 ${casa_dir}/bin/python3 -m pytest -v --pyclean -m unit <pipeline_dir>/.
```

Alternatively, use

```console
${casa_dir}/bin/casa --nogui --nologger --agg --nologfile -c "import pytest; pytest.main(['-v', '--pyclean', '-m', 'unit', '<pipeline_dir>'])"
```

The CASA call version will use `casashell` (i.e., `python3 -m casashell`), which might show slightly different results.
The `--nologfile` (equivalent to `--logfile /dev/null`) here can prevent generating CASA log files in your pipeline repository directory.

If [`pytest-xdist`](https://pytest-xdist.readthedocs.io/en/latest) and [`pytest-cov`](https://pytest-cov.readthedocs.io/en/latest/config.html) are avilable, you can also try:

```console
PYTHONNOUSERSITE=1 ${casa_dir}/bin/python3 -m pytest -n 4 -v --cov=pipeline --cov-report=html -m unit <pipeline_dir>
```

or

```console
${casa_dir}/bin/casa --nogui --nologger --agg --nologfile -c "import pytest; pytest.main(['-v', '<pipeline_dir>', '-n', '4', '-m', 'unit', '--cov', 'pipeline', '--cov-report', 'html'])"
```

On a multi-core system, `pytest-xdist` can speed things up significantly, when the parallelization doesn't create a memory/io-bound situation. This is usually true for a light-weight test collection (e.g. unit tests), e.g.,

    walltime   0m21.744s # with pytest-xdist
    walltime   2m13.076s # without pytest-xdist

A summary of various test frameworks and tools is available in [PIPE-806](https://open-jira.nrao.edu/browse/PIPE-806).

## Regression tests

See <https://open-confluence.nrao.edu/display/PL/Regression+Testing> for details

To add the *xdist* flavor to your local regression run, one can try:

```console
PYTHONNOUSERSITE=1 ${casa_dir}/bin/python3 -m pytest -vv --junitxml=regression-results.xml -n 4 <pipeline_dir>/pipeline/regression/.
```

or alternatively

```console
xvfb-run -d ${casa_dir}/bin/casa --nogui --nologger --agg -c \
    "import pytest; pytest.main(['-vv', '--junitxml=regression-results.xml', '-n', '4', '<pipeline_dir>/tests/regression'])"
```

Here are some additional examples to run selected tests using their [node IDs or custom makers](https://docs.pytest.org/en/latest/example/markers.html):

```console
# select a single test using its node ID
xvfb-run -d ${casa_dir}/bin/casa --nogui --nologger --agg -c \
    "import pytest; pytest.main(['-vv', '--junitxml=regression-results.xml', '<pipeline_dir>/tests/regression/fast/alma_if_fast_test.py::test_uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small__PPR__regression'])"
```

```console
# select a group of tests using the test marker `hifa`
xvfb-run -d ${casa_dir}/bin/casa --nogui --nologger --agg -c \
    "import pytest; pytest.main(['-vv', '--junitxml=regression-results.xml', '-m', 'hifa', '<pipeline_dir>/tests/regression'])"
```

```console
# select all tests with `mg2_20170525142607_180419` in the test function names
xvfb-run -d ${casa_dir}/bin/casa --nogui --nologger --agg -c \
    "import pytest; pytest.main(['-vv', '--junitxml=regression-results.xml', '-k', 'mg2_20170525142607_180419', '<pipeline_dir>/tests/regression'])"
```

Alternatively, if you want to figure out the coverage of a single regression test and also prefer to directly call CASA's python interpreter (therefore skip the `casashell` layer and .casa/startup.py):

```console
PYTHONNOUSERSITE=1 xvfb-run -d ${casa_dir}/bin/python3 -m pytest -v --pyclean --cov=pipeline --cov-report=html \
    ${pipeline_dir}/tests/regression/fast/alma_if_fast_test.py::test_uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small__PPR__regression
```

The coverage report will be saved as `htmlcov/index.html`. A similar call can be issued to report the test coverage of the entire regression test suite, although such run will take much longer.

## Component tests

The component tests are meant to exercise task and inter-task behavior without running an entire pipeline workflow.

```console
PYTHONNOUSERSITE=1 ${casa_dir}/bin/python3 -m pytest -vv --junitxml=component-results.xml -n 4 <pipeline_dir>/pipeline/component/.
```

or alternatively

```console
xvfb-run -d ${casa_dir}/bin/casa --nogui --nologger --agg -c \
    "import pytest; pytest.main(['-vv', '--junitxml=component-results.xml', '-n', '4', '<pipeline_dir>/tests/component'])"
```

### Combining Coverage Reports

You can merge coverage reports from multiple test runs into a single, comprehensive report using the `coverage combine` command. This is especially useful when tests are run in parallel, such as in different subdirectories or on separate machines, as each run creates its own data file (e.g., `.coverage.host1`).

First, run `coverage combine` to merge the individual data files. The `find` command in this example gathers all files named `.coverage*` from the subdirectories. Using the `--keep` flag is recommended to prevent the original files from being deleted after combination.

After the data is merged into a single `.coverage` file, you can generate the final HTML report.

```console
# Find and combine all .coverage* files from subdirectories
coverage combine --keep $(find ./* -name ".coverage*")

# Generate the final HTML report from the combined data
coverage html
```

## Custom pytest options

Pipeline has several pytest custom options, which can be found by invoking `--help` inside a repository directory.

```console
casa_python -m pytest --help
...
custom options:
  --collect-tests       collect tests and export test node ids to a plain text file `collected_tests.txt`
  --nologfile           do not create CASA log files, equivalent to 'casa --nologfile'
  --pyclean             clean up .pyc to reproduce certain warnings only issued when the bytecode is compiled.
  --compare-only        do the comparison between the results in a working area from a previously-run test and the saved reference values (do not re-run the pipeline recipe)
  --longtests           run longer-running tests which are excluded by default
...
```

Here, `casa_python` is an alias to `PYTHONNOUSERSITE=1 ${casa_dir}/bin/python3`.

For example, if you only want to generate a list of test node ids for existing regression tests, try

```console
casa_python -m pytest -v --collect-tests <pipeline_dir>
```

On the other hand, one can use the `--nologfile` option (built in `conftest.py`), to avoid `casa-*log` files spamming your repo working directory.

```console
casa_python -m pytest -n 4 -v --pyclean --nologfile <pipeline_dir>
```

The `--compare-only` option is used to generate new pytest results from a previous test run without re-running the pipeline recipe. It uses the existing working directories to extract values for comparison with the reference values. For example, the following will use the existing working directories for the previously run fast alma tests to compare these results to the reference values. This should be run in a directory which contains the test output results for each test.

```console
xvfb-run casa --nogui --nologger --log2term --agg -c \
    "import pytest; pytest.main(['-vv', '-m alma and fast', '--compare-only', '<pipeline_dir>'])"
```

The `--longtests` option enables the longer tests to be run. When this option is not specified, only the quicker set of tests will be run.

The `--data-directory` option allows the specification of the directory where the larger input data files are stored. If not specified, this defaults to `/lustre/cv/projects/pipeline-test-data/regression-test-data/` which requires the tests to be run somewhere with access to lustre.

```console
xvfb-run casa --nogui --nologger --log2term --agg -c \
    "import pytest; pytest.main(['-vv', '-m alma and slow', '--data-directory=/users/kberry/big_data_directory/', '<pipeline_dir>'])"
```

## Custom markers

There are several custom markers used for the pipeline regression tests. These are specified in pyproject.toml and also listed below:

* alma: alma test
* nobeyama: nobeyama test
* vla: vla test (does not include vlass)
* vlass: vlass test
* fast: shorter-running test
* slow: longer-running test
* twelve: 12m ALMA test
* seven: 7m ALMA test
* sd: single dish test
* interferometry: interferometry test

These markers can be used to select the tests to run using the -m option to pytest. For example, if you want to only run vlass tests, try:

```console
xvfb-run casa --nogui --nologger --log2term --agg -c"import pytest; pytest.main(['-vv', '-m vlass', '--longtests', '<pipeline_dir>'])"
```

 Markers can also be combined using 'and', 'or', or 'not'. The following example demonstrates how to run only fast vla tests:

```console
xvfb-run casa --nogui --nologger --log2term --agg -c"import pytest; pytest.main(['-vv', '-m vla and fast', 'pipeline'])"
```

And to run everything besides the vlass tests, run the following:

```console
xvfb-run casa --nogui --nologger --log2term --agg -c"import pytest; pytest.main(['-vv', '-m not vlass', 'pipeline'])"
```

## `casa-data` and `pipeline-testdata`

With an identical software stack, the numerical results from Pipeline tests can still differ due to various factors: runtime session environments (e.g. serial vs. mpicasa sessions, OpenMP threading), OS libraries, as well as the version of [`casa-data`](https://casadocs.readthedocs.io/en/latest/notebooks/external-data.html) (now managed by the [`casaconfig`](https://casadocs.readthedocs.io/en/latest/api/casaconfig.html) package).

To streamline two typical use cases developers/testers usually encounter: Case 1, daily development and analysis with the latest `casa-data` version; Case 2: benchmarking tests or producing reported issues using a specific casa-data version, a recommended code snippet is provided below to customize the `casa-data` and extra [`pipeline-testadata`](https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline-testdata/browse) path for casa sessions from [`~/.casa/config`](https://casadocs.readthedocs.io/en/latest/api/casaconfig.html#config-py):

```python
###################################################################################################
# User customization section
###################################################################################################

# 'casa-data' path discovery list in precedence order: first hit will be picked up by casaconfig.
# note: if the environment variable `CASADATA` is set, the value will be prepended to the discovery
# list.
measurespath_checklist = [
    '~/Workspace/nvme/nrao/casa_dist/casarundata',  # maintained by casaconfig
    '~/Workspace/nvme/nrao/casa_dist/casa-data',  # git-lfs clone
    '~/Workspace/local/nrao/casa_dist/casarundata',  # maintained by casaconfig
    '~/Workspace/local/nrao/casa_dist/casa-data',  # git-lfs clone
]

# all user data paths to be appended
datapath_list = ['~/Workspace/zfs/nrao/tests/pipeline-testdata']

# note: if measurespath is not maintained by casaconfig (i.e. from git clone), auto_update will not
# take effect.
measures_auto_update = True
data_auto_update = True

###################################################################################################
# Assign rundata/measurespath/datapath for casa6
###################################################################################################

if 'CASADATA' in os.environ:
    measurespath_checklist = [os.environ.get('CASADATA')]
else:
    measurespath_checklist = [
        os.path.abspath(os.path.expanduser(path)) for path in measurespath_checklist if isinstance(path, str)
    ]
datapath_list = [os.path.abspath(os.path.expanduser(path)) for path in datapath_list if isinstance(path, str)]

measurespath = None
datapath = []
for path in measurespath_checklist:
    if os.path.isdir(os.path.join(path, 'geodetic')):
        rundata = measurespath = path
        datapath = [measurespath]
        break

try:
    import casaconfig
except ImportError:
    if measurespath is None:
        print(
            '!!! The value of rundata is not set and casatools can not find the expected data in datapath !!!'
        )
        print('!!! CASA6 can not continue. !!!')
        os._exit(os.EX_CONFIG)

datapath += [os.path.expanduser(path) for path in datapath_list if os.path.isdir(path)]

###################################################################################################
```

The rationales of such a setup are as follows:

For Case 1, a tester or developer might define a customized all-in-one discovery list suitable for different computing environments (e.g. nmpost vs. cvpost filesystems, NRAO computing nodes vs. work laptop) as a daily setup.
For testing/benchmarking occasions, i.e. Case 2, one could also use an environment variable `CASADATA` to override the default setup from `~/.casa/config.py` and switch to a specific `casa-data` version checked out from the [`casa-data`](https://open-bitbucket.nrao.edu/projects/CASA/repos/casa-data/browse) repo.

Note that `casaconfig` and the [`casa-data` Git repostory](https://open-bitbucket.nrao.edu/projects/CASA/repos/casa-data/browse) are two equivalent approaches managing the runtime data necessary for a CASA session. `casaconfig` was only introduced at CASA ver 6.6.4, offering Python API to fetch, auto-update, and examine `casa-data`.
Meanwhile, the Git `casa-data` repo provide a manual "hands-on" way to manage the CASA external data.

The CASA `measurespath`/`rundata` configuration values can be pointed at either a directory managed by casaconfig, or a `casa-data` repository local path. When `casaconfig` detects the path to be a directory structure managed by Git, `measure_auto_update` and `data_auto_update` will take no action as `casaconfig` is designed to only handle the directory structured initialized created by `casaconfig` itself.

For testing cases where a specific casa-data is needed, because `casaconfig` currently doesn't offer the capability of rollback to a specific casa-data version, we would still rely on the Git version control of `casa-data` repo to achieve version management. Therefore, it's preferred that `measurespath` or `rundata` is set to a `casa-data` git repository for that instance. However, versions of certain data (e.g. geodetic measures) in such setup might be occasionally behind those offered from the `casaconfig` "auto-update" mechanism because the late can fetch data directly from an external provider (e.g. ASTRO FTP server).
