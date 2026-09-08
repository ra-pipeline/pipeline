# Pipeline Developer & Maintenance Scripts

This directory contains utility and maintenance scripts for developing, building, testing, and managing the Pipeline codebase.

---

## Table of Contents

- [1. `bundle_assets.py` — Weblog Asset Minification & Bundling](#1-bundle_assetspy--weblog-asset-minification--bundling)
- [2. `procedure_add_parallel.py` — Parallel Procedure Generator](#2-procedure_add_parallelpy--parallel-procedure-generator)
- [3. `update_references.py` — NASA/ADS Reference Synchronizer](#3-update_referencespy--nasaads-reference-synchronizer)
- [4. `build_backend.py` — In-Tree PEP 517 Build Backend Wrapper](#4-build_backendpy--in-tree-pep-517-build-backend-wrapper)

---

## 1. `bundle_assets.py` — Weblog Asset Minification & Bundling

Bundles and minifies static JavaScript and CSS assets used by the Pipeline HTML weblog templates (`pipeline/infrastructure/renderer/templates/resources/`).

This script replaces the legacy `MinifyJSCommand` and `MinifyCSSCommand` from `setup.py`, allowing assets to be bundled independently of the package installation process.

### Bundles Created

| Target Bundle | Source Location | Source Files Combined | Minification Tool |
| :--- | :--- | :--- | :--- |
| **`pipeline_common.min.js`** | `.../resources/js/` | `jquery-3.3.1.js`, `holder.js`, `lazyload.js`, `jquery.fancybox.js`, `plotcmd.js`, `tcleancmd.js`, `purl.js`, `bootstrap.js`, `pipeline.js` | `jsmin` |
| **`pipeline_plots.min.js`** | `.../resources/js/` | `select2.js`, `d3.v3.js` | `jsmin` |
| **`all.min.css`** | `.../resources/css/` | `font-awesome.css`, `jquery.fancybox.css`, `select2.css`, `select2-bootstrap.css`, `pipeline.css` | `csscompressor` |

### Requirements

Requires `csscompressor` and `jsmin`:

```bash
pip install -r requirements_dev.txt
```

### Usage

```bash
# Build / regenerate all minified bundles:
python scripts/bundle_assets.py

# Or via pixi task:
pixi run bundle-assets

# Check if bundles on disk are in sync with source assets (exits 1 if out of sync, useful for CI):
python scripts/bundle_assets.py --check

# Suppress informational output:
python scripts/bundle_assets.py -q
```

---

## 2. `procedure_add_parallel.py` — Parallel Procedure Generator

Inspects Pipeline procedure XML files or Pipeline Processing Requests (PPRs) and injects `parallel=True` into tasks that support parallel execution.

Observatory-delivered procedures usually run serially by default. This script automates generating parallel-enabled copies for faster re-processing and regression testing without manually editing task definitions.

### Usage

```bash
python scripts/procedure_add_parallel.py <input_xml> <output_xml>
```

### Examples

```bash
# Convert a standard ALMA calibration procedure:
python scripts/procedure_add_parallel.py pipeline/recipes/procedure_hifa_cal.xml procedure_hifa_cal_parallel.xml

# Convert an ALMA PPR file:
python scripts/procedure_add_parallel.py PPR_uid___A001_X362b_X53a.xml PPR_uid___A001_X362b_X53a_parallel.xml
```

---

## 3. `update_references.py` — NASA/ADS Reference Synchronizer

Fetches the latest Pipeline publication and bibliography records from the [NASA/ADS Public Library](https://ui.adsabs.harvard.edu/public-libraries/w9Eg1EwtTAK14nz2CuQ2Fg) and writes the resolved BibTeX entries to `docs/source/references/pipeline.bib`.

### Requirements

Requires an active NASA/ADS developer API token. The script checks for the token in the following order:

1. `--token` CLI argument
2. `ADS_DEV_KEY`, `ADS_API_TOKEN`, or `ADSTOKEN` environment variables
3. `~/.ads/dev_key` or `~/.ads/token` config files

### Usage

```bash
# Set your token and run via Pixi task:
export ADS_DEV_KEY="your-ads-token"
pixi run update-references

# Or run directly:
python scripts/update_references.py --token <YOUR_TOKEN>

# Specify a custom output path:
python scripts/update_references.py --output custom_pipeline.bib
```

---

## 4. `build_backend.py` — In-Tree PEP 517 Build Backend Wrapper

Wraps `setuptools.build_meta` to compute and inject the Pipeline package version on-demand during package building and installation (`pip install`, `python -m build`, `pixi`, `uv`).

This in-tree backend replaces the legacy `setup.py` build hooks:

- Dynamically calls `pipeline/infrastructure/version.py` using `get_version_string_from_git()`.
- Generates `pipeline/_version.py` (read at runtime by `pipeline.environment.pipeline_revision`).
- Generates the root `version` file (read by `setuptools` via `dynamic.version = { file = "version" }`).
- Preserves the exact NRAO custom version scheme (`YEAR.MAJOR.MINOR.MICRO+<branch>-<commits>-g<hash>[-dirty]`) without requiring manual release scripts or external version-tagging plugins.

Configured in `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=64.0", "packaging>=22.0.0", "wheel"]
build-backend = "build_backend"
backend-path = ["scripts"]
```

Included in `MANIFEST.in` (`include scripts/build_backend.py`) so that building or installing from source distribution tarballs (`sdist`) works seamlessly in isolated build environments.
