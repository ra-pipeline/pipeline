FROM almalinux:9-minimal

LABEL maintainer="NRAO Science Data Processing Pipeline" \
      description="CASA and Pipeline Operational Container"

# Environment configuration
ENV LC_ALL=C.UTF-8 \
    PYTHONNOUSERSITE=1 \
    PYTHONWARNINGS=ignore::SyntaxWarning \
    OMP_PLACES=threads \
    OMP_PROC_BIND=false \
    OMP_NUM_THREADS=4 \
    OPENBLAS_NUM_THREADS=4 \
    FI_PROVIDER=^psm3 \
    PATH=/app/.pixi/envs/default/bin:$PATH

WORKDIR /app

# Copy dependency manifests, pre-built wheel, and common provisioning script
COPY pyproject.toml pixi.lock /app/
COPY dist/*.whl /app/dist/
COPY packaging/container/setup.sh /app/setup.sh

# Run common installation script and cleanup
RUN bash /app/setup.sh && rm -f /app/setup.sh

ENTRYPOINT ["/app/.pixi/envs/default/bin/python", "-m", "casashell"]
