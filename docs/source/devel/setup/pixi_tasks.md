# Pixi and Running Pixi tasks

[Pixi](https://prefix.dev/docs/pixi/overview) is a fast, cross-platform package manager built on top of the conda ecosystem.
In Pipeline development, Pixi manages reproducible environments per CASA version and exposes common developer workflows as named tasks.

---

## Prerequisites

Clone the repository:

```bash
git clone https://open-bitbucket.nrao.edu/scm/pipe/pipeline.git
cd pipeline/
```

Check out your branch:

```bash
git checkout -b PIPE-1234-my-feature   # new branch
# or
git checkout PIPE-1234-my-feature      # existing branch
```

Install pixi (one-time, no root required):

```bash
curl -fsSL https://pixi.sh/install.sh | bash
```

Install the environment:

```bash
pixi install          # resolves and downloads all deps into .pixi/envs/
```

---

## Environments

Each environment pins a specific CASA release.  The `default` environment
tracks the latest supported CASA snapshot.

```{list-table}
:header-rows: 1
:widths: 42 18 40

* - Environment
  - CASA version
  - Python
* - `default` (alias: `casa675-py312`)
  - 6.7.5
  - 3.12
* - `casa675-py313`
  - 6.7.5
  - 3.13 (linux-64 + osx-arm64)
* - `casa675-py312`
  - 6.7.5
  - 3.12
* - `casa674-py312`
  - 6.7.4
  - 3.12
* - `casa671-py312`
  - 6.7.1
  - 3.12
* - `docs`
  - 6.7.5
  - 3.12 (docs extras)
```

Select a non-default environment with `--environment` / `-e`:

```bash
pixi run -e casa671-py312 test-unit
```

---

## Available tasks

### `test-unit` — unit tests with coverage

Runs all unit tests (any `*_test.py` file under `pipeline/`) using
`pytest-xdist` with `-n logical` to parallelize across available CPUs.
`--max-worker-restart=1` limits retries of crashed xdist workers.
Coverage is accumulated with `--cov-append` and written to `htmlcov/` and
`coverage.xml` **in the directory where `pixi run` is invoked** (`$INIT_CWD`).

```bash
# from a scratch directory so CASA logs and coverage land there
cd /my/workdir
pixi run test-unit
```

:::{tip}
**Test data setup** — unit and regression tests that require data files depend on the [`pipeline-testdata`](https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline-testdata/browse) Git LFS repository and a `~/.casa/config.py` entry pointing to it:

1. Install Git LFS and clone the repository:

   ```bash
   git lfs install
   git clone https://open-bitbucket.nrao.edu/scm/pipe/pipeline-testdata.git /path/to/pipeline-testdata
   ```

   On Linux, increase the credential cache timeout to avoid repeated password prompts during LFS downloads:

   ```bash
   git config --global credential.helper 'cache --timeout=3600'
   ```

2. Add the following to `~/.casa/config.py` (create the file if it does not exist):

   ```python
   datapath = ["/path/to/pipeline-testdata"]
   ```

   Tests use `casatools.ctsys.resolve()` to locate data files, which searches all paths in `datapath`.
:::

---

### `test-regression` — fast regression suite (xdist, no MPI)

Runs the full `tests/regression/fast/` suite in a plain Python session
(not `mpicasa`) using `pytest-xdist -n 12 --dist worksteal` with 12 parallel
workers.  Tests marked `mpi` are excluded.

Output (CASA logs, pipeline working dirs, coverage) lands in the directory
where `pixi run` is invoked (`$INIT_CWD`).

```bash
cd /my/workdir
pixi run test-regression
```

To invoke from outside the source tree:

```bash
cd /my/workdir
pixi run --manifest-path /path/to/pipeline/pyproject.toml test-regression
```

---

### `test-pltest1` — single quick ALMA-IF regression test

Runs one small ALMA 7m regression test
(`test_uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small__PPR__regression`)
inside `casashell`.  Useful for a fast smoke-test of the ALMA-IF code path.

Output lands in `$INIT_CWD` — the directory where `pixi run` is invoked.

```bash
cd /my/workdir
pixi run test-pltest1

# or from anywhere, pointing at the manifest
cd /my/workdir
pixi run --manifest-path /path/to/pipeline/pyproject.toml test-pltest1
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

## Controlling the working directory (`$INIT_CWD`)

All test tasks (`test-unit`, `test-regression`, `test-pltest1`) start with
`cd $INIT_CWD`, where `$INIT_CWD` is the directory from which `pixi run` was
invoked.  This means CASA log files (`casa-*.log`), pipeline output
directories, and coverage artifacts land in your working directory — not in
the source tree.

```
/my/workdir/            ← invoke pixi run from here
  casa-*.log            ← CASA log output
  uid___…_test_output/  ← pipeline working directories
  htmlcov/              ← coverage HTML report
  coverage.xml          ← coverage XML report

pipeline/               ← source tree (pyproject.toml here); stays clean
```

Example workflow:

```bash
mkdir -p /zfs/scratch/PIPE-3061
cd /zfs/scratch/PIPE-3061
pixi run --manifest-path /path/to/pipeline/pyproject.toml test-pltest1
```

> **Note:** pixi's task shell (`deno_task_shell`) is not bash.
> The `$INIT_CWD` variable is set by pixi to the shell's cwd at invocation time.
> `$PIXI_PROJECT_ROOT` always points to the directory containing `pyproject.toml`.

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

## Migrating conda dependencies to pixi

If you have an existing `environment.yml` (conda) and want to migrate its
packages into `pyproject.toml`, use `pixi`'s built-in import command:

```bash
pixi init --import environment.yml
```

This creates a new standalone `pixi.toml` in the current directory with
conda packages mapped to `[dependencies]` and pip packages mapped to
`[pypi-dependencies]`.  To use `pyproject.toml` instead, copy the generated
sections into `[tool.pixi.dependencies]` and `[tool.pixi.pypi-dependencies]`
respectively.

For manual migration or to inspect what pixi would generate, export a solved
conda environment first:

```bash
# Export the currently active conda env to a YAML file
conda env export --no-builds > environment_export.yml

# Or export only explicitly installed packages (cleaner)
conda env export --from-history > environment_export.yml
```

Then map the sections manually into `pyproject.toml`:

```{list-table}
:header-rows: 1
:widths: 45 55

* - `environment.yml` section
  - `pyproject.toml` section
* - `dependencies:` (conda packages)
  - `[tool.pixi.dependencies]`
* - `pip:` block under `dependencies:`
  - `[tool.pixi.pypi-dependencies]`
* - `channels:`
  - `[tool.pixi.workspace]` → `channels = [...]`
* - `name:`
  - becomes the pixi environment name under `[tool.pixi.environments]`
```

Example `environment.yml` fragment and its pixi equivalent:

```yaml
# environment.yml
channels:
  - conda-forge
dependencies:
  - python=3.12
  - openmpi>=5.0
  - pip:
    - casatasks>=6.6.6
```

```toml
# pyproject.toml
[tool.pixi.workspace]
channels = ["conda-forge"]

[tool.pixi.dependencies]
python = "3.12.*"
openmpi = ">=5.0"

[tool.pixi.pypi-dependencies]
casatasks = { version = ">=6.6.6", index = "https://casa-pip.nrao.edu/repository/pypi-group/simple" }
```

> **Tip:** Pixi version constraints use `">=x.y"` (string) rather than conda's
> bare `>=x.y`.  Also use `"x.y.*"` instead of `=x.y` for minor-version pins.

### Exporting a pixi environment to `environment.yml`

To share or reproduce a pixi environment via conda, export it with:

```bash
# Export default environment (reads from pixi.lock)
pixi project export conda-environment > environment_casa675_py312.yml

# Export a specific environment
pixi project export conda-environment -e casa671-py312 > environment_casa671_py312.yml

# From outside the source tree
pixi project export conda-environment \
  --manifest-path /path/to/pipeline/pyproject.toml \
  -e casa675-py312
```

> **Note:** The exported YAML contains pinned conda-managed packages from
> `pixi.lock`.  PyPI-only dependencies (e.g. `casatasks`, `pipeline` itself)
> appear under a `pip:` block if pixi includes them, but some may be omitted —
> verify the output before using it as a standalone conda spec.

#### Private index URLs are not exported

`pixi project export conda-environment` drops the `index =` URLs from
`[tool.pixi.pypi-dependencies]`, so packages sourced from the NRAO CASA pip
index will be listed without their index URL.  A subsequent
`conda env create -f ...` will fail because pip cannot find `casatasks`,
`casashell`, etc. on PyPI.

**Workaround** — insert `--extra-index-url` as the first entry under `pip:`
after exporting:

```bash
pixi project export conda-environment -e casa674-py312 \
  | sed 's|^- pip:$|- pip:\n  - --extra-index-url https://casa-pip.nrao.edu/repository/pypi-group/simple|' \
  > environment_casa674_py312.yml
```

Or add it manually to the exported file:

```yaml
- pip:
  - --extra-index-url https://casa-pip.nrao.edu/repository/pypi-group/simple
  - casashell==6.7.4.*
  - casatasks>=6.6.6
  - ...
```

This is an upstream pixi limitation — there is no flag to include index URLs
in the export.

---

## Summary

```{list-table}
:header-rows: 1
:widths: 25 40 35

* - Task
  - Command
  - Output cwd
* - Unit tests
  - `pixi run test-unit`
  - `$INIT_CWD` (invocation dir)
* - Fast regression (all)
  - `pixi run test-regression`
  - `$INIT_CWD` (invocation dir)
* - Single ALMA-IF test
  - `pixi run test-pltest1`
  - `$INIT_CWD` (invocation dir)
* - Init CASA runtime data
  - `pixi run fetch-casarundata`
  - project root
* - Build docs (clean)
  - `pixi run build-docs`
  - `docs/`
* - Build docs (fast)
  - `pixi run build-docs-fast`
  - `docs/`
* - Build PDF docs
  - `pixi run build-pdf`
  - `docs/`
```
