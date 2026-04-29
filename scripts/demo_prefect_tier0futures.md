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
    - note: to change the port (default `4200`): add `--port <number>`, e.g. `pixi run -e exp prefect server start --host 0.0.0.0 --port 4201`; update `prefect_api_url` in the script to match
    - note: to nuke the database: `pixi run -e exp prefect server database reset -y`
    - note: avoid the community upgrade banner: `prefect config set PREFECT_SERVER_UI_SHOW_PROMOTIONAL_CONTENT=False`
    - **Recommended: start with tuned settings** to avoid SQLite connection pool exhaustion when many Dask workers post logs/artifacts concurrently (default pool is only 5+10 connections):
        ```bash
        PREFECT_SERVER_DATABASE_POOL_SIZE=20 \
        PREFECT_SERVER_DATABASE_MAX_OVERFLOW=40 \
        PREFECT_SERVER_DATABASE_TIMEOUT=60 \
        PREFECT_LOGGING_LEVEL=WARNING \
        PREFECT_API_URL=http://127.0.0.1:4201/api \
        pixi run -e exp prefect server start --host 0.0.0.0 --port 4201
        ```
        | Variable | Purpose |
        |---|---|
        | `PREFECT_SERVER_DATABASE_POOL_SIZE=20` | Max persistent DB connections (default: 5); raise to handle concurrent Dask worker requests |
        | `PREFECT_SERVER_DATABASE_MAX_OVERFLOW=40` | Extra connections allowed beyond pool size (default: 10); prevents `QueuePool limit reached` errors |
        | `PREFECT_SERVER_DATABASE_TIMEOUT=60` | Seconds to wait for a DB connection before raising `TimeoutError` (default: 30) |
        | `PREFECT_LOGGING_LEVEL=WARNING` | Suppresses verbose INFO logs from the server process itself |
        | `PREFECT_API_URL=...` | Tells the server (and any CLI tools in the same shell) which URL to bind/advertise |
    - **Optional: use PostgreSQL instead of SQLite** for better concurrency under heavy Dask workloads:
        ```bash
        # One-time setup
        initdb -D ~/.prefect/prefect-pg && pg_ctl -D ~/.prefect/prefect-pg start
        createdb prefect

        # Start server pointing at PostgreSQL
        PREFECT_API_DATABASE_CONNECTION_URL="postgresql+asyncpg://localhost/prefect" \
        PREFECT_SERVER_DATABASE_POOL_SIZE=20 \
        PREFECT_SERVER_DATABASE_MAX_OVERFLOW=40 \
        PREFECT_SERVER_DATABASE_TIMEOUT=60 \
        PREFECT_LOGGING_LEVEL=WARNING \
        PREFECT_API_URL=http://127.0.0.1:4201/api \
        pixi run -e exp prefect server start --host 0.0.0.0 --port 4201
        ```
- Configure the API endpoint so the script reports runs to the correct server. `--port` and `PREFECT_API_URL` serve different purposes and must agree:
    - **`--port <number>`** tells the **server** which port to listen on (affects the URL you open in a browser).
    - **`PREFECT_API_URL`** tells the **client** (the script, CLI commands, etc.) where to find the server.
    - For the dashboard to show flow runs you need both pointing at the same port. On the default port `4200` neither is needed. On a custom port, set both:
        ```bash
        # Terminal 1 — start server on port 4201
        PREFECT_API_URL=http://127.0.0.1:4201/api pixi run -e exp prefect server start --host 0.0.0.0 --port 4201

        # Terminal 2 — run the script against that server
        PREFECT_API_URL=http://127.0.0.1:4201/api pixi run -e exp python scripts/demo_prefect_tier0futures.py pltest1
        ```
    - Note the `/api` suffix is required in `PREFECT_API_URL`.
    - **Accessing the server from other machines**: `--host 0.0.0.0` makes the server listen on all network interfaces, but clients must connect using the server machine's actual IP or hostname — not `0.0.0.0`. Use `hostname -f` to get a routable address dynamically:
        ```bash
        SERVER_IP=$(hostname -f)   # fully-qualified hostname, routable from other nodes
        # or: SERVER_IP=$(hostname -I | awk '{print $1}')  # first IP address

        PREFECT_SERVER_DATABASE_POOL_SIZE=20 \
        PREFECT_SERVER_DATABASE_MAX_OVERFLOW=40 \
        PREFECT_SERVER_DATABASE_TIMEOUT=60 \
        PREFECT_LOGGING_LEVEL=WARNING \
        PREFECT_API_URL=http://${SERVER_IP}:4201/api \
        pixi run -e exp prefect server start --host 0.0.0.0 --port 4201
        ```
        From another node, point the client at the same address:
        ```bash
        PREFECT_API_URL=http://<server-hostname>:4201/api \
        pixi run -e exp python scripts/demo_prefect_tier0futures.py pltest1
        ```
        If the port is blocked by a firewall, use an SSH tunnel instead:
        ```bash
        # On your local/client machine
        ssh -L 4201:localhost:4201 <server-hostname>
        # Then connect to http://localhost:4201 (UI) and use PREFECT_API_URL=http://127.0.0.1:4201/api
        ```

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
pixi run -e exp python scripts/demo_prefect_tier0futures.py if2016
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
pixi run -e exp python scripts/demo_prefect_tier0futures.py if2016
```

Submit via: `sbatch run_pipeline.sh`

## 5. View your Results
While the cluster crushes the PPR, check your dashboard UI at whatever `PREFECT_API_URL` you mapped! You will instantly see the dynamic `PPR_uid_...` flow run, and Dask Worker metrics flowing into the **Artifacts** tab.
