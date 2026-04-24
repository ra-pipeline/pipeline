# Running Pipeline tasks with Pixi

[Pixi](https://prefix.dev/docs/pixi/overview) is a fast, cross-platform package manager built on top of the conda ecosystem.
It manages reproducible environments per CASA version and exposes common developer workflows as named tasks.

---

## Prerequisites

Install pixi (one-time, no root required):

```bash
curl -fsSL https://pixi.sh/install.sh | bash
```

Then, from the pipeline source root, install the environment:

```bash
cd pipeline/
pixi install          # resolves and downloads all deps into .pixi/envs/
```

---

## Environments

Each environment pins a specific CASA release.  The `default` environment
tracks the latest supported CASA snapshot.

| Environment | CASA version | Python |
|-------------|-------------|--------|
| `default` (alias: `casa675-py312`) | 6.7.5 | 3.12 |
| `casa675-py313` | 6.7.5 | 3.13 (linux-64 + osx-arm64) |
| `casa675-py312` | 6.7.5 | 3.12 |
| `casa674-py312` | 6.7.4 | 3.12 |
| `casa671-py312` | 6.7.1 | 3.12 |
| `docs` | 6.7.5 | 3.12 (docs extras) |

Select a non-default environment with `--environment` / `-e`:

```bash
pixi run -e casa671-py312 test-unit
```

---

## Available tasks

### `test-unit` — unit tests with coverage

Runs all unit tests (any test not under a `regression` or `component` path is
auto-marked `unit` by `conftest.py`).  Uses `pytest-xdist` with `-n logical`
to parallelize across available CPUs.  Coverage is written to `htmlcov/` and
`coverage.xml` in the working directory.

```bash
pixi run test-unit
```

Runs from the **project root** (`pyproject.toml` directory).

---

### `test-regression` — fast regression suite (serial CASA session, xdist)

Runs the full `tests/regression/fast/` suite inside a plain Python session
(not `mpicasa`) using `pytest-xdist --dist worksteal`.  Tests marked `mpi`
are excluded — use `test-regression-mpi` (not yet defined) for those.

```bash
# default: output lands in ../working/
pixi run test-regression

# custom output directory
PL_WORKDIR=/zfs/scratch/myrun pixi run test-regression
```

`PL_WORKDIR` defaults to `../working` (a sibling of the `pipeline/` source
directory).  Set it to any writable path to keep CASA logs, pipeline output
directories, and coverage files out of the source tree.

---

### `test-pltest1` — single quick ALMA-IF regression test

Runs one small ALMA 7m regression test
(`test_uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small__PPR__regression`)
inside `casashell`.  Useful for a fast smoke-test of the ALMA-IF code path.

```bash
# default output directory: ../working/
pixi run test-pltest1

# custom output directory
PL_WORKDIR=/tmp/pl_scratch pixi run test-pltest1
```

---

### `fetch-casarundata` — initialize CASA runtime data

Triggers the first-time download of CASA runtime data (measures tables, etc.)
by importing `casatools`.  Run once after `pixi install` or after switching to
a new CASA version.

```bash
pixi run fetch-casarundata
```

---

### `build-docs` — build HTML documentation (full clean rebuild)

Builds the Sphinx documentation into `docs/_build/html/`.

```bash
pixi run build-docs

# Use the docs environment (Python 3.12 + docs extras)
pixi run -e docs build-docs
```

---

### `build-docs-fast` — incremental HTML documentation build

Reuses cached doctrees and autosummary stubs.  Much faster during active
documentation development; use `build-docs` for a clean final build.

```bash
pixi run build-docs-fast
```

---

### `build-pdf` — build PDF (LaTeX) documentation

```bash
pixi run build-pdf
```

---

## Controlling the working directory (`PL_WORKDIR`)

By default `test-regression` and `test-pltest1` `cd` into `../working`
before launching.  This prevents CASA log files (`casa-*.log`), pipeline
working directories, and coverage artifacts from polluting the source tree.

```
pipeline/         ← source tree (pyproject.toml here)
working/          ← default PL_WORKDIR; created by you once
  casa-*.log
  pipeline_output_*/
  htmlcov/
  coverage.xml
```

Create it once:

```bash
mkdir -p ../working
```

Override per invocation:

```bash
PL_WORKDIR=/zfs/scratch/PIPE-3061 pixi run test-pltest1
```

---

## Running tasks against a specific CASA version

```bash
# Smoke-test with CASA 6.7.4
pixi run -e casa674-py312 test-pltest1

# Full regression with CASA 6.7.1 / Python 3.12
pixi run -e casa671-py312 test-regression
```

---

## Shell inside a pixi environment

Drop into an interactive shell with the environment activated:

```bash
pixi shell                  # default environment
pixi shell -e casa671-py312 # specific environment
```

---

## Summary

| Task | Command | Default cwd |
|------|---------|-------------|
| Unit tests | `pixi run test-unit` | project root |
| Fast regression (all) | `pixi run test-regression` | `../working` |
| Single ALMA-IF test | `pixi run test-pltest1` | `../working` |
| Init CASA runtime data | `pixi run fetch-casarundata` | project root |
| Build docs (clean) | `pixi run build-docs` | `docs/` |
| Build docs (fast) | `pixi run build-docs-fast` | `docs/` |
| Build PDF docs | `pixi run build-pdf` | `docs/` |
