# syntax=docker/dockerfile:1
FROM ubuntu:24.04

# Define a variable for the non-root user
ARG USER_NAME=pipeline
# Define a variable for the conda environment name
ARG CONDA_ENV_NAME=pipeline

# 1. System Setup and Micromamba Installation
# Define environment variables
ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    MAMBA_ROOT_PREFIX=/opt/conda \
    PIP_NO_CACHE_DIR=off

# Create the user and set up permissions
# Use a single RUN layer for user setup and system packages to minimize layers
RUN useradd -m -s /bin/bash "${USER_NAME}" && \
    mkdir -p "${MAMBA_ROOT_PREFIX}" && \
    chown -R "${USER_NAME}":"${USER_NAME}" "${MAMBA_ROOT_PREFIX}"

# Install system dependencies and Micromamba
# Use 'SHELL' for a single RUN command to ensure proper execution
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && \
    # Install dependencies with minimal layers and cleanup
    apt-get install -y --no-install-recommends \
        bash curl tar file bzip2 ca-certificates git xvfb nano less rsync \
        libfuse2 fuse libxcb-cursor0 libglib2.0-0t64 libfontconfig1 libfreetype6 \
        libsm6 libxext6 libxml2-utils libxrender1 && \
    # Install micromamba to global path
    curl -Ls https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj -C /bin/ --strip-components=1 bin/micromamba && \
    # Cleanup in the same layer
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /tmp/* /var/tmp/*

# 2. Create Python Environment
# Switch to the non-root user for environment installation
USER "${USER_NAME}"
WORKDIR /home/${USER_NAME}

# Copy definition files
COPY --chown="${USER_NAME}:${USER_NAME}" environment.yml requirements.txt ./

# Create environment, clean up, and reduce size in a single layer
RUN micromamba env create -f environment.yml -n "${CONDA_ENV_NAME}" --yes && \
    # Clean up artifacts to reduce image size
    micromamba clean --all --yes && \
    rm -rf /home/${USER_NAME}/.mamba/pkgs "${MAMBA_ROOT_PREFIX}"/pkgs && \
    rm -rf /home/${USER_NAME}/.cache/pip && \
    # Remove definition files
    rm environment.yml requirements.txt && \
    # Aggressive cleanup of static and intermediate files
    find "${MAMBA_ROOT_PREFIX}" -follow -type f -name '*.a' -delete && \
    find "${MAMBA_ROOT_PREFIX}" -follow -type f -name '*.o' -delete && \
    find "${MAMBA_ROOT_PREFIX}" -follow -type f -name "*.lock" -delete && \
    find "${MAMBA_ROOT_PREFIX}" -follow -type f -name '*.js.map' -delete && \
    # We could uncomment these lines if .pyc files and __pycache__ dirs need to be removed.
    # However, this may affect performance and trigger SyntaxWarnings for initial casashell/casatasks start-up.
    # find "${MAMBA_ROOT_PREFIX}" -follow -type f -name '*.pyc' -delete && \
    # find "${MAMBA_ROOT_PREFIX}" -follow -type d -name '__pycache__' -delete && \
    # Create CASA data directory (as user)
    mkdir -p /home/${USER_NAME}/.casa/data

# 3. Final Configuration
# Set the final environment variables including the updated PATH
ENV CONDA_DEFAULT_ENV="${CONDA_ENV_NAME}" \
    PATH="${MAMBA_ROOT_PREFIX}/envs/${CONDA_ENV_NAME}/bin:$PATH" \
    # Keep DISPLAY here if X-forwarding is needed at runtime
    DISPLAY=:0

# Final command
CMD ["bash"]