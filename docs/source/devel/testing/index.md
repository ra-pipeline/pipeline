# Testing

The pipeline has three test categories that differ in scope, speed, and data requirements.

:::{list-table}
:header-rows: 1
:widths: auto

* - Category
  - Location
  - Speed
  - Purpose
* - Unit
  - `pipeline/` (co-located with source)
  - Fast (ms)
  - Validate individual functions and classes
* - Component
  - `tests/component/`
  - Medium
  - Exercise task sequences in isolation
* - Regression
  - `tests/regression/fast/` and `slow/`
  - Slow
  - Validate complete pipeline workflows against reference output
:::

## Repository layout

```text
pipeline/                   # unit tests distributed throughout (co-located)
tests/
├── component/              # component tests
├── regression/
│   ├── fast/               # quick regression tests
│   └── slow/               # longer tests (requires --longtests)
├── testing_utils.py        # PipelineTester framework
└── test_pipeline_testing_framework.py
```

## Quick start

Run unit tests:

```console
PYTHONNOUSERSITE=1 ${casa_dir}/bin/python3 -m pytest -v --pyclean -m unit <pipeline_dir>/.
```

Run component tests:

```console
PYTHONNOUSERSITE=1 ${casa_dir}/bin/python3 -m pytest -vv -n 4 <pipeline_dir>/tests/component/.
```

Run fast regression tests:

```console
PYTHONNOUSERSITE=1 ${casa_dir}/bin/python3 -m pytest -vv <pipeline_dir>/tests/regression/fast/.
```

```{toctree}
:maxdepth: 1

unit_tests
automated_tests
pytest_reference
test_environment
diffing_execution_logs
DataType_Testing
```
