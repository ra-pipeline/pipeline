#!/usr/bin/env bash
set -euo pipefail

# Locate project root dynamically
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

ENV_NAME="${ENV_NAME:-default}"
VERSION="${1:-${VERSION:-$(python3 -c "from pipeline._version import version; print(version)" 2>/dev/null || echo "2026.3.0")}}"
DIST_DIR="dist"
BUILD_DIR="${PROJECT_ROOT}/build_tarball"

echo "[INFO] Packaging Pipeline + CASA tarball (Version: ${VERSION}, Environment: ${ENV_NAME})..."

# 1. Clean previous build artifacts and build release wheel
rm -rf "${DIST_DIR}" "${BUILD_DIR}"
python -m build --wheel --no-isolation

# 2. Instantiate clean locked environment and install conda-pack
pixi install --environment "${ENV_NAME}" --locked
pixi add --pypi conda-pack --environment "${ENV_NAME}"

# 3. Install release wheel into environment prefix
ENV_PATH="${PROJECT_ROOT}/.pixi/envs/${ENV_NAME}"
"${ENV_PATH}/bin/pip" install --no-deps "${DIST_DIR}"/*.whl

# 4. Pack environment into temporary archive
mkdir -p "${BUILD_DIR}/root"
"${ENV_PATH}/bin/conda-pack" -p "${ENV_PATH}" -o "${BUILD_DIR}/env.tar.gz"

# 5. Extract to staging directory
tar -xzf "${BUILD_DIR}/env.tar.gz" -C "${BUILD_DIR}/root"
rm -f "${BUILD_DIR}/env.tar.gz"

# 6. Inject relocatable wrapper launcher
cat <<'EOF' > "${BUILD_DIR}/root/bin/casa"
#!/usr/bin/env bash
# Dynamically locate the environment root, wherever this directory is moved
ENV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# One-time path relocation fix on initial run (if conda-unpack is present)
if [ -f "${ENV_DIR}/bin/conda-unpack" ]; then
    "${ENV_DIR}/bin/conda-unpack" 2>/dev/null || true
    rm -f "${ENV_DIR}/bin/conda-unpack"
fi

# Environment safety invariants
export PYTHONNOUSERSITE=1
export OMP_PLACES="threads"
export OMP_PROC_BIND="false"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-4}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-4}"
export FI_PROVIDER="${FI_PROVIDER:-^psm3}"

# Prepend environment bin to PATH for subprocesses and MPI utilities
export PATH="${ENV_DIR}/bin:${PATH}"

# Launch casashell directly via python binary (bypasses broken script shebangs)
exec "${ENV_DIR}/bin/python" -m casashell "$@"
EOF
chmod +x "${BUILD_DIR}/root/bin/casa"

# 7. Compress into final distribution archive
FINAL_ARCHIVE="${PROJECT_ROOT}/casa-pipeline-${VERSION}-linux-x86_64.tar.xz"
tar -cf - -C "${BUILD_DIR}/root" . | xz -T0 -3 > "${FINAL_ARCHIVE}"
rm -rf "${BUILD_DIR}"

echo "[SUCCESS] Built operational archive: ${FINAL_ARCHIVE}"
