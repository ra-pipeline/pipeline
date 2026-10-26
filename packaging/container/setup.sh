#!/usr/bin/env bash
set -euo pipefail

# Suppress Python 3.12 syntax warnings from legacy CASA escape sequences
export PYTHONWARNINGS=ignore::SyntaxWarning

# 1. System packages
microdnf install -y tar gzip bzip2 libglvnd-glx
microdnf clean all

# 2. Install Pixi without telemetry
export PIXI_NO_TELEMETRY=1
curl -fsSL https://pixi.sh/install.sh | bash
export PATH=/root/.pixi/bin:$PATH

# 3. Install locked dependencies, pre-built wheel (with its runtime dependencies), and precompile bytecode
cd /app
pixi install --environment default --locked --skip pipeline --run-post-link-scripts
/app/.pixi/envs/default/bin/pip install --no-cache-dir --root-user-action=ignore \
    --extra-index-url https://casa-pip.nrao.edu/repository/pypi-group/simple \
    /app/dist/*.whl
/app/.pixi/envs/default/bin/python -m compileall -q -f -x 'contrib' /app || true

# 4. Strip build-time headers, static archives, and redundant files
rm -rf /app/dist
rm -rf /app/.pixi/envs/default/include
find /app/.pixi/envs/default -name "*.a" -delete
find /app/.pixi/envs/default/lib/python3.12/site-packages -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true

# 5. Clean build, package manager, and download caches
pixi clean cache --yes
rm -rf /root/.cache /root/.pixi /var/cache/* /var/log/*
