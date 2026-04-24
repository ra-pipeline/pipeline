# Demo Prefect dask-tier0futures integration on Cluster (with Pixi)

This guide walks you through bootstrapping exactly the environment needed to run a pipeline data processing test using the existing Pipeline dask-based Tier0Futures parallelization layer and the Prefect architecture from scratch.

## 1. Install Pixi (Package & Environment Manager)

On your cluster login or interactive node, install the Pixi package manager. 

```bash
curl -fsSL https://pixi.sh/install.sh | bash
```

After it installs, refresh your shell so the `pixi` command is recognized:
```bash
source ~/.bashrc  # (or ~/.zshrc)
```

## 2. Clone the Repository

Clone the specific pipeline testing repository and check out your working branch:

```bash
git clone https://open-bitbucket.nrao.edu/scm/pipe/pipeline.git
cd pipeline
git checkout PIPE-3073-prefect-workflow-task-adapter-and-tier0future-backend-improvement
```

*Note: Pixi ensures that you do **not** need to install dependencies globally or worry about `module load python`. Once inside the directory, Pixi handles all dependencies internally based on `pyproject.toml`.*

## 3. Configuration & Cluster Readiness

Ensure the experimental orchestration layers are targeted in your configuration.

1. Verify `pipeline/config.yaml` has `tier0futures: true` (if you want decentralized Dask futures processing).
2. Ensure you have the test dataset (e.g. `2016.1.00053.S/rawdata`) correctly symlinked or mounted on the cluster nodes you plan to use. 

If you want the Prefect UI to capture the exact cluster execution:
- Start the server on a known node: `pixi run -e exp prefect server start --host 0.0.0.0`
    - note: to nuke the database: `pixi run -e exp prefect server database reset -y`
    - note: avoid the community upgrade banner: `prefect config set PREFECT_SERVER_UI_SHOW_PROMOTIONAL_CONTENT=False`
- Configure the API endpoint: You can either set the `prefect_api_url` variable directly inside `scripts/demo_prefect_tier0futures.py`, or set the environment variable beforehand: `export PREFECT_API_URL="http://<server-ip>:4200/api"`

## 4. Running the Pipeline on the Cluster

Because this utilizes Prefect orchestration and Dask, we utilize the **experimental (`exp`)** pixi environment.

### Option A: Interactive Cluster Node
If you allocate an interactive node (`srun` or `qsub -I`), execute the demo script natively:

```bash
# Allocate an interactive compute node
srun --nodes=1 --cpus-per-task=16 --pty bash

# Enter your clone directory
cd /path/to/pipeline

# Enable orchestration and run!
export PIPELINE_USE_PREFECT=1
pixi run -e exp python scripts/demo_prefect_tier0futures.py
```

### Option B: Batch Submission (SLURM)
If you want to submit the execution entirely to the queue, you can wrap the `pixi run` sequence in an `sbatch` script (`run_pipeline.sh`):

```bash
#!/bin/bash
#SBATCH --job-name=pipeline-tier0
#SBATCH --nodes=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=12:00:00

cd /path/to/pipeline

# Ensure configuration is active
export PIPELINE_USE_PREFECT=1

# Execute the test natively inside the Pixi managed environment
pixi run -e exp python scripts/demo_prefect_tier0futures.py
```

Submit via: `sbatch run_pipeline.sh`

## 5. View your Results
While the cluster crushes the PPR, check your dashboard UI at whatever `PREFECT_API_URL` you mapped! You will instantly see the dynamic `PPR_uid_...` flow run, and Dask Worker metrics flowing into the **Artifacts** tab.
