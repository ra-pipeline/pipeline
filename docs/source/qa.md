(pipeline_qa)=

# Frequently Asked Questions

This section addresses common questions about the ALMA and VLA pipelines.

## General

### What is the difference between PPR and Recipe workflows?

**PPR (Pipeline Processing Request)** is the standard execution method used in ALMA and VLA observatory operations. A PPR is a self-contained XML document that packages both **observation metadata** (project structure, scheduling block IDs, dataset filenames, session definitions) and **processing instructions** (ordered sequence of pipeline tasks and parameters).

PPRs are executed via standalone runner scripts in CASA:

```bash
# ALMA execution
casa --nogui --nologger -c pipeline/runpipeline.py ppr_alma.xml

# VLA execution
casa --nogui --nologger -c pipeline/runvlapipeline.py ppr_vla.xml
```

**Recipe / Procedure (`recipereducer`)** is a programmatic Python API workflow designed for development, validation testing, and custom data reduction. It is driven by generic procedure XML templates (located in `pipeline/recipes/`, e.g., `procedure_hifa_calimage.xml` or `procedure_hifv.xml`) that define *only* the sequence of pipeline tasks and default parameters.

Unlike a PPR, a recipe procedure contains no dataset metadata. Input measurement sets (`vis`), session assignments, and execution options are passed directly as Python arguments:

```python
from pipeline import recipereducer
recipereducer.reduce(vis=['uid___A001_X123_X456.ms'], procedure='procedure_hifa_calimage.xml')
```

:::{note}
In production operations, a dataset-specific PPR XML is dynamically generated online by merging a generic recipe procedure with observation project metadata.
:::

### What Python version does the pipeline require?

The latest pipeline version supports Python 3.12+. Check the branch-specific `pyproject.toml` for exact version constraints and compatible CASA versions.

## Installation & Deployment

### How do I build a CASA6+Pipeline monolithic tarball locally?

You can create a standalone CASA distribution with the pipeline pre-installed using a custom setup script. This is useful for creating reproducible environments to facilitate validation testing of specific CASA and pipeline version combinations not covered by the automated packaging matrix at NRAO.

**Prerequisites:**

- ~3 GB of available disk space
- Internet connection for downloading release tarballs and dependencies
- `git` and `wget` installed
- Bash shell environment

**Step-by-Step Instructions:**

1. **Create the setup script:**
Save the following script as `setup_casa_pipeline.sh`:

```bash
#!/bin/bash
# CASA + Pipeline Setup Script
# Downloads a base CASA distribution and installs a specified pipeline branch.

set -euo pipefail  # Exit on error, undefined vars, and pipe failures

# Specify base CASA version and pipeline git branch/tag (modify as needed)
casa_ver="casa-6.7.1-13-py3.10-gpu.el8"
pipe_ver="release/2026.1.0"

echo "Setting up CASA ${casa_ver} with pipeline branch ${pipe_ver}..."

# Download and extract base CASA distribution
echo "Downloading CASA tarball..."
wget "https://casa.nrao.edu/download/distro/casa/releaseprep/${casa_ver}.tar.xz"

echo "Extracting CASA tarball..."
tar xvf "${casa_ver}.tar.xz"

# Clone target pipeline repository
echo "Cloning pipeline repository..."
git clone --branch "${pipe_ver}" --single-branch \
    https://open-bitbucket.nrao.edu/scm/pipe/pipeline.git

# Install third-party pipeline requirements inside CASA's Python environment
echo "Installing pipeline requirements..."
PYTHONNOUSERSITE=1 "${casa_ver}/bin/pip3" install \
    --disable-pip-version-check \
    --upgrade-strategy=only-if-needed \
    --use-pep517 \
    -r pipeline/requirements.txt

# Install pipeline package into CASA
echo "Installing pipeline package..."
PYTHONNOUSERSITE=1 "${casa_ver}/bin/pip3" install \
    --disable-pip-version-check \
    --upgrade-strategy=only-if-needed \
    --use-pep517 \
    pipeline/.

echo "Setup complete! Pipeline package successfully installed inside ${casa_ver}."
```

1. **Customize target versions:**
   - Modify `casa_ver` inside the script to select a different base CASA release.
   - Modify `pipe_ver` to target a specific git branch, release tag, or commit hash.

2. **Make executable and run:**

```bash
chmod +x setup_casa_pipeline.sh
./setup_casa_pipeline.sh
```

1. **Package as a monolithic tarball (Optional):**
Once setup completes, archive and compress the resulting CASA directory for easy distribution:

```bash
tar czf casa-6.7.1-with-pipeline.tar.gz casa-6.7.1-13-py3.10-gpu.el8/
```

1. **Deploy to target systems:**
Transfer and unpack the standalone bundle on target environments (e.g., HPC clusters):

```bash
# Transfer archive to remote host
scp casa-6.7.1-with-pipeline.tar.gz user@cluster:/shared/software/

# Extract on target machine
tar xzf casa-6.7.1-with-pipeline.tar.gz
```

1. **Verify the installation:**
Test that CASA launches properly and loads the pipeline package revision:

```bash
./casa-6.7.1-13-py3.10-gpu.el8/bin/casa --version
./casa-6.7.1-13-py3.10-gpu.el8/bin/python3 -c "import pipeline; print(pipeline.revision)"
```

:::{tip}
**Editable Development Installation**

If you are actively developing or modifying pipeline source code, replace the final package install command in Step 1 with editable mode (`-e`):

```bash
PYTHONNOUSERSITE=1 "${casa_ver}/bin/pip3" install \
    --disable-pip-version-check \
    --upgrade-strategy=only-if-needed \
    --use-pep517 \
    -e pipeline/.
```

Installing in editable mode links CASA directly to your local git checkout rather than copying files into `site-packages`. Any modifications you make to the pipeline code will take effect immediately upon restarting CASA, without needing to reinstall.
:::

### What are the different Pipeline installation and deployment use cases?

The pipeline can be deployed in several distinct configurations depending on your operational needs:

- **Monolithic CASA Distribution (Self-contained tarball)**
  A complete CASA 6 release bundled with an embedded Python interpreter, all C++/Python libraries, and the Pipeline pre-installed.
  - **Best for:** Observatory production operations and standalone data reduction requiring a self-contained, reproducible environment with near-zero setup.

- **Modular Python Environment (Managed via Pixi or Conda)**
  A standard Python environment where CASA 6 tools (`casatools`, `casatasks`) and Pipeline dependencies are installed dynamically according to the Pipeline project package specifications.
  - **Best for:** Scientific research, customized data workflows, and environments needing minimal initial disk size (requires internet access or a local package cache).

- **Editable Development Installation**
  Built on top of either a monolithic CASA distribution or a modular Python environment, with the Pipeline source repository linked in editable mode (`pip install -e`).
  - **Best for:** Active software development, testing new algorithms, and debugging pipeline recipes without reinstalling after code changes.

- **Containerized Execution (Docker / Singularity / Apptainer)**
  An encapsulated container image that packages the OS runtime, CASA suite, and Pipeline into an immutable, portable environment.
  - **Best for:** High-Performance Computing (HPC/HTC) clusters, cloud-native processing, and automated CI/CD workflows.

## Configuration

### How do I customize pipeline workflow executaion and behaviors?

Parameters are defined in:

- **PPR XML files** — task-specific settings for production runs
- **Recipe procedures** — task parameters passed to `recipereducer`
- **Environment variables** — global configuration (see [Interface Reference](pipeline_icd))

### What environment variables can I set?

Key variables include:

- `FLUX_SERVICE_URL` — ALMA flux density database URL
- `JYPERKDB_URL` — Jy/K conversion database URL
- `SCIPIPE_ROOTDIR` — pipeline data root directory
- `ENABLE_TIER0_PLOTMS` — enable/disable plotms visualization

See [Environment Variables](pipeline_icd.md#environment-variables) for complete list.

## Data Products

### Where are the output products stored?

Pipeline outputs are written to the current working directory by default, managed by export tasks (`hifa_exportdata`, `hsd_exportdata`, etc.). Output structure:

```
./
  uid___*.ms/           # Processed measurement set
  calibration/          # Calibration tables
  products/             # FITS images and weblog
  pipeline_manifest.xml # Processing metadata
  pipeline_aquareport.xml # Quality assessment
```

### What is in pipeline_manifest.xml?

The manifest contains:

- Processing metadata (versions, timestamps, execution time)
- Data product inventory (names, paths, sizes)
- Task execution summary
- Consumed by: ALMA Science Archive, NRAO Archive, AQUA system

### How do I interpret the weblog?

The weblog is an HTML report with:

- Per-stage summaries and diagnostic plots
- Flag statistics and RFI detection results
- Calibration solution plots
- Image statistics and quality metrics

Open `index.html` in the weblog directory to browse results.

## Execution

<!--
### Can I run the pipeline on multiple datasets in parallel?

Yes, the pipeline supports distributed execution via:
- **SLURM** — resource allocation with `SLURM_*` environment variables
- **Dask** — distributed framework for multi-node execution
- **Condor** — with `PYTHON_CPU_COUNT` for CPU allocation

See [Execution Environment](pipeline_icd.md#execution-environment-external-schedulers--workers) for details.
-->

## Troubleshooting

### What if the flux service is unavailable?

The pipeline has fallback behavior:

- Primary service is `FLUX_SERVICE_URL` (almascience.org)
- Backup is `FLUX_SERVICE_URL_BACKUP` (asa.alma.cl)
- Use local `flux.csv` override file for manual values

Set via environment or PPR configuration.

### How do I handle antenna position correction failures?

By default, if the `getantposalma` task fails (e.g., due to ALMA web service issues or network offline states), the pipeline raises a `PipelineException` and halts execution.

If you want the pipeline to log a warning and continue processing without applying corrections, you can enable lenient mode by setting the `ALLOW_GETANTPOSALMA_FAILURE` environment variable to `true` before running the pipeline:

```python
import os
# Lenient mode: Log warning and continue processing if getantposalma fails
os.environ['ALLOW_GETANTPOSALMA_FAILURE'] = 'true'

# Strict mode (default): Crash with PipelineException if getantposalma fails
os.environ['ALLOW_GETANTPOSALMA_FAILURE'] = 'false'
```

### What if I need to run in a headless environment (HPC cluster)?

CASA tasks (mainly `plotms` and viewer tasks) require an active X11 display server. In a headless environment (such as an HPC cluster or CI runner), you should execute CASA using the system-level **`xvfb-run`** utility to redirect graphics to a virtual frame buffer:

```bash
xvfb-run -a casa --nogui --nologger -c pipeline/runpipeline.py ppr_file.xml
```

The pipeline also features an internal virtual display server (powered by the python package `pyvirtualdisplay`, enabled via configuration). If you are already running CASA with the external `xvfb-run` utility, you should manually set the environment variable **`XVFB_RUN=1`**. The pipeline detects this variable and skips starting its own nested virtual display session to avoid resource conflicts:

```bash
export XVFB_RUN=1
xvfb-run -a casa --nogui --nologger -c pipeline/runpipeline.py ppr_file.xml
```
<!--
## API Usage
## Performance
### How can I optimize pipeline performance?
-->

## References

- [Interface Reference](pipeline_icd) — API documentation
- [Dependencies](dependencies) — Required packages
- [Developer Setup](devel/setup/index) — Local development environment
