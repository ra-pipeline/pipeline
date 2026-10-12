# Dependencies of `Pipeline`

[Pipeline]: https://open-bitbucket.nrao.edu/projects/PIPE
[casaconfig]: https://github.com/casangi/casaconfig
[pipeline-testdata]: https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline-testdata/browse
[casatasks.wvrgcal]: https://casadocs.readthedocs.io/en/stable/api/tt/casatasks.calibration.wvrgcal.html#casatasks.calibration.wvrgcal

## Runtime

### CASA6-equivalent Python environment

```{note}
[Pipeline] is a Python package that depends on CASA6 components and various
general-purpose Python libraries. Like any Python package, it is only compatible
with specific versions of Python and its third-party dependencies. In practice,
each release is tested and validated solely against a monolithic CASA6 release
tied to a particular ALMA/VLA cycle. That monolithic release is a self-contained
Python environment bundling a portable interpreter and all required libraries.
Current target: **CASA >= 6.7.4 with Python 3.12**.
CASA6 itself has limited platform support; see the
[CASA6 compatibility matrix](https://casadocs.readthedocs.io/en/stable/notebooks/introduction.html#Compatibility)
for OS and library requirements.
```

To encourage the use and development of `Pipeline` in a standard Python
environment (e.g. conda), the essential components for a CASA6-equivalent
setup are listed below. All of these are included in the Pipeline-dedicated
CASA releases.

- python3
- ipython
- pip
- numpy
- scipy
- matplotlib
- casatools
- casatasks
- casaplotms
- casampi

```{note}
`casadata` and `almatasks` are no longer required as of `CASA6 >= 6.6.1`
thanks to the introduction of [casaconfig] and the migration of the
[casatasks.wvrgcal] task. `casaconfig` is implicitly required by
`casatasks`.
```

### Other Pipeline dependencies

The following libraries are required by Pipeline but are **not** included in
the CASA6 monolithic distribution.

Python packages (declared under `[project.dependencies]` in `pyproject.toml`):

- cachetools
- docstring-inheritance
- mako
- pypubsub
- intervaltree
- logutils
- ps_mem
- astropy
- bdsf (VLASS source detection and mask creation)

Unix command-line tools:

- **ImageMagick**

  - `convert`: generates thumbnails on Linux; macOS uses the built-in `sips`
    instead. Also used by `ImageMagickWriter` from `matplotlib.animation`
    in `hsd/tasks/common/rasterutil.py` (developer use only).
  - `montage`: required by `hifa_renorm`.

- **poppler-utils**

  - `pdfunite`: required by `hifa_renorm`.

- **Git**: used to obtain the Pipeline revision description string.
- **Xvfb / xvfb-run**: required by the `casampi` module for headless
  execution.
- **uncompress**: used by `tec_maps.py` in CASA for the VLA task
  `hifv_priorcals`.

### Observatory Online Services & CASA Runtime Data

During operation, the pipeline queries external observatory online services and also relies on
[CASA runtime data](https://casadocs.readthedocs.io/en/stable/notebooks/external-data.html). Live health
and availability are tracked via two status monitors:

```{list-table}
:header-rows: 1
:widths: 30 45 25

* - Service / Data Feed
  - Description & Pipeline Touchpoints
  - Status Monitor
* - **CASA Runtime Data (`casa-data`)**
  - Measures tables (IERS Earth Orientation Parameters, leap seconds, geodetic, ephemeris) managed by `casaconfig`.
  - [Casaconfig Monitor](https://www.aoc.nrao.edu/~jmarvil/casaconfig-monitor.html)
* - **ALMA Calibrator Flux Density Service**
  - Queried by {func}`~pipeline.hifa.cli.hifa_importdata` (`dbservice=True`) to fetch calibrator fluxes via `FLUX_SERVICE_URL`.
  - [Pipeline Services Monitor](https://ra-pipeline.github.io/pipeline-services-monitor/)
* - **ALMA Antenna Positions Service**
  - Queried by {func}`~pipeline.hifa.cli.hifa_antpos` via `getantposalma` to obtain baseline corrections.
  - [Pipeline Services Monitor](https://ra-pipeline.github.io/pipeline-services-monitor/)
* - **ALMA Jy/K Database (`jyperk`)**
  - Queried by {func}`~pipeline.hsd.cli.hsd_k2jycal` (`dbservice=True`) via `JYPERKDB_URL` with
    regional fallbacks (JAO, EA, NA, EU) for Single-Dish Kelvin-to-Jansky conversion factors.
  - [Pipeline Services Monitor](https://ra-pipeline.github.io/pipeline-services-monitor/)
* - **VLA Antenna Position Corrections**
  - Queried by {func}`~pipeline.hifv.cli.hifv_priorcals` via CASA `gencal` to retrieve antenna position offset tables.
  - [Pipeline Services Monitor](https://ra-pipeline.github.io/pipeline-services-monitor/)
* - **VLA Ionospheric TEC Maps (`tec_maps`)**
  - Queried by {func}`~pipeline.hifv.cli.hifv_priorcals` to download external daily IONEX maps from CDDIS / NASA / IGS servers.
  - [Pipeline Services Monitor](https://ra-pipeline.github.io/pipeline-services-monitor/)
```

- [Casaconfig Monitor](https://www.aoc.nrao.edu/~jmarvil/casaconfig-monitor.html): Tracks the synchronization, age,
  and health of CASA runtime data (casa-data / casaconfig measures, IERS Earth Orientation Parameters, geodetic tables,
  and upstream FTP/HTTPS tarballs).
- [Pipeline Services Monitor](https://ra-pipeline.github.io/pipeline-services-monitor/): Tracks live operational
  availability and response latencies of external web services queried by the pipeline during reduction (ALMA flux
  density, antenna positions, and Jy/K database; VLA antenna positions and TEC maps).

## Development Tools

### Environment Management

- **Pixi** (>= v0.71.0): Multi-language environment and package manager. The project uses the "Rich Platforms" syntax (inline OS version constraints) which requires Pixi v0.71.0+.
  - Reference: [Rich Platforms documentation](https://pixi.sh/latest/features/rich-platforms/)
  - Set via `pixi-version` in GitHub Actions workflows and required for local development with `pixi run` commands.

### Packaging

- `build`
- `twine`
- `wheel`

### Testing

- `pytest`
- `pytest-cov`
- `pytest-xdist`
- `pytest-html`
- `pytest-xvfb`

### Code quality

- `ruff`
- `pre-commit`
- `memray`
- `line_profiler`

### Documentation

Declared under `[project.optional-dependencies.docs]` in `pyproject.toml`. Key packages:

- `sphinx` with `furo` theme
- `myst-parser`, `myst-nb` (Markdown and notebook support)
- `sphinxcontrib-mermaid` (diagram support)
- `sphinx-automodapi` (API docs)
- `sphinx-copybutton`, `sphinxcontrib-bibtex`

### Version control

- `Git LFS`: for managing the [pipeline-testdata] repository.
