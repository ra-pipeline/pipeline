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

Python packages (see also `requirements.txt` in the source repository):

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

## Development Tools

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
- `pytest-forked`

### Code quality

- `black`
- `isort`
- `flake8`
- `pylint`
- `pydocstyle`
- `pycodestyle`
- `ruff`
- `pre-commit`
- `memray`
- `line_profiler`

### Documentation

See `requirements_docs.txt` in the source repository. Key packages:

- `sphinx` with `furo` theme
- `myst-parser`, `myst-nb` (Markdown and notebook support)
- `sphinxcontrib-mermaid` (diagram support)
- `sphinx-automodapi`, `sphinx-autoapi` (API docs)
- `sphinx-copybutton`, `sphinxcontrib-bibtex`

### Version control

- `Git LFS`: for managing the [pipeline-testdata] repository.
