# Unit tests

Unit tests are small, focused tests that validate individual functions, classes, or modules
in isolation. They execute quickly and don't require external data files or full pipeline
execution. For further background see [PIPE-862](https://open-jira.nrao.edu/browse/PIPE-862)
and the testing framework overview in [PIPE-806](https://open-jira.nrao.edu/browse/PIPE-806).

## Naming and location

Unit tests are distributed throughout the codebase, co-located with the code they test.
Test files follow one of two naming patterns:

- `<module_name>_test.py` — primary convention
- `test_<module_name>.py` — alternative (less common)

Common locations include:

- `pipeline/infrastructure/` — infrastructure and utility tests (`contfilehandler_test.py`,
  `daskhelpers_test.py`, `executeppr_test.py`, `utils_test.py`, ...)
- `pipeline/infrastructure/utils/` — unit conversions, imaging utilities, math, sorting,
  position corrections, CASA data access, weblog
- `pipeline/hifa/tasks/` — ALMA interferometry tasks (applycal, flagging, importdata)
- `pipeline/hifv/` — VLA tasks and heuristics
- `pipeline/hsd/tasks/` — single-dish baseline, atmcor, common utilities
- `pipeline/hsd/heuristics/` — grouping, pointing outlier detection, raster scan patterns
- `pipeline/h/` — common tasks and heuristics (linefinder, atmutil, importdata)
- `pipeline/qa/` — QA score calculations
- `pipeline/recipes/` — recipe conversion and VLA recipe tests

## Running unit tests

Using CASA's Python interpreter directly (recommended for reproducibility):

```console
PYTHONNOUSERSITE=1 ${casa_dir}/bin/python3 -m pytest -v --pyclean -m unit <pipeline_dir>/.
```

Via CASA's shell:

```console
${casa_dir}/bin/casa --nogui --nologger --agg --nologfile -c \
    "import pytest; pytest.main(['-v', '--pyclean', '-m', 'unit', '<pipeline_dir>'])"
```

With [`pytest-xdist`](https://pytest-xdist.readthedocs.io/en/latest) for parallel execution:

```console
PYTHONNOUSERSITE=1 ${casa_dir}/bin/python3 -m pytest -n 4 -v --pyclean -m unit <pipeline_dir>
```

On a multi-core system, `pytest-xdist` reduces walltime significantly for lightweight test
collections such as unit tests:

```
walltime   0m21.744s  # with pytest-xdist (-n 4)
walltime   2m13.076s  # without pytest-xdist
```

Run tests in a specific subdirectory or file:

```console
PYTHONNOUSERSITE=1 ${casa_dir}/bin/python3 -m pytest -v pipeline/infrastructure/utils/math_test.py
```

### Useful options

Standard pytest flags that are handy for day-to-day unit test runs:

:::{list-table}
:header-rows: 1
:widths: auto

* - Option
  - Effect
* - `-x`
  - Stop after the first failure
* - `--tb=short`
  - Compact traceback
* - `--tb=line`
  - One-line traceback
* - `--pdb`
  - Drop into the Python debugger on failure
* - `--maxfail=N`
  - Stop after N failures
:::

Example — fail-fast with a compact traceback:

```console
PYTHONNOUSERSITE=1 ${casa_dir}/bin/python3 -m pytest -vv -x --tb=short \
    pipeline/infrastructure/utils/
```

### Coverage

With [`pytest-cov`](https://pytest-cov.readthedocs.io/en/latest/) available, measure
coverage while running unit tests:

```console
PYTHONNOUSERSITE=1 ${casa_dir}/bin/python3 -m pytest -n 4 -v --pyclean \
    --cov=pipeline --cov-report=html -m unit <pipeline_dir>
```

The HTML report is saved to `htmlcov/index.html`.

### Scoping: unit tests vs component/regression

Unit tests live in `pipeline/` (co-located with source code), while component and regression
tests live in `tests/`. This means directory paths act as natural category filters:

```console
# unit tests only
PYTHONNOUSERSITE=1 ${casa_dir}/bin/python3 -m pytest pipeline/

# component and regression tests only (no unit tests)
PYTHONNOUSERSITE=1 ${casa_dir}/bin/python3 -m pytest tests/
```

## Writing unit tests

Unit tests use pytest. A basic test file:

```python
import pytest
from module_under_test import function_to_test

def test_basic_functionality():
    result = function_to_test(input_value)
    assert result == expected_value

def test_error_handling():
    with pytest.raises(ValueError):
        function_to_test(invalid_input)
```

### Parametrized tests

For testing multiple cases with the same logic:

```python
import pytest

@pytest.mark.parametrize('input_val, expected', [
    ('input1', 'expected1'),
    ('input2', 'expected2'),
])
def test_multiple_cases(input_val, expected):
    result = function_to_test(input_val)
    assert result == expected
```

### Mocks

For isolating code from external dependencies:

```python
from unittest.mock import Mock, patch

def test_with_mock():
    mock_dep = Mock()
    mock_dep.method.return_value = 'mocked_value'
    result = function_using_dependency(mock_dep)
    assert result == expected_result
    mock_dep.method.assert_called_once()

@patch('module.external_function')
def test_with_patch(mock_function):
    mock_function.return_value = 'patched_value'
    result = function_calling_external()
    assert result == expected_result
```

### Fixtures

For shared setup and teardown:

```python
import pytest

@pytest.fixture
def sample_data():
    return {'key': 'value', 'number': 42}

def test_using_fixture(sample_data):
    assert sample_data['number'] == 42
```

## Best practices

- Place test files in the same directory as the code they test.
- Make each test independent — don't rely on other tests or shared global state.
- Test the happy path, edge cases, and error conditions.
- Mock external dependencies (CASA tools, files, network) to keep tests fast and isolated.
- Use `pytest.approx` for floating-point comparisons.
- Keep unit tests to milliseconds, not seconds; reserve large data and slow operations for
  regression tests.
- Use descriptive test names that describe what is being tested.
