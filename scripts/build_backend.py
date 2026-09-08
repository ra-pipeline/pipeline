"""In-tree PEP 517 / PEP 660 build backend wrapper.

Wraps setuptools.build_meta to dynamically compute and generate the
Pipeline version on-demand during package building and installation (pip install,
python -m build, uv, etc.) using the NRAO Git versioning logic in
pipeline/infrastructure/version.py.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from setuptools import build_meta as _orig

_ROOT = Path(__file__).resolve().parent.parent
_cached_version: str | None = None


def _ensure_version() -> str:
    """Compute the Git version and write version files before setuptools builds."""
    global _cached_version
    if _cached_version is not None:
        return _cached_version

    ver = None

    # 1. Try computing version from Git via pipeline/infrastructure/version.py
    version_script = _ROOT / 'pipeline' / 'infrastructure' / 'version.py'
    if version_script.is_file():
        try:
            spec = importlib.util.spec_from_file_location('pipeline_version_loader', version_script)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                git_ver = mod.get_version_string_from_git(cwd=str(_ROOT))
                if git_ver and git_ver != 'unknown':
                    ver = git_ver
        except Exception:
            pass

    # 2. If Git metadata is not available (e.g. building from an unpacked sdist tarball),
    # preserve any previously generated version file.
    ver_txt = _ROOT / 'version'
    ver_py = _ROOT / 'pipeline' / '_version.py'

    if not ver and ver_txt.is_file():
        try:
            ver = ver_txt.read_text(encoding='utf-8').strip()
        except Exception:
            pass

    if not ver and ver_py.is_file():
        try:
            # Parse version from existing _version.py
            for line in ver_py.read_text(encoding='utf-8').splitlines():
                if line.startswith('version ='):
                    ver = line.split('=', 1)[1].strip().strip('\'"')
                    break
        except Exception:
            pass

    if not ver:
        ver = '0.0.dev0'

    # Write pipeline/_version.py (for runtime imports by pipeline.environment)
    ver_py.write_text(
        '# File generated on-demand during build/install\n'
        '# do not change, do not track in version control\n'
        f"version = '{ver}'\n",
        encoding='utf-8',
    )

    # Write root version file (read by setuptools dynamic version = { file = "version" })
    ver_txt.write_text(f'{ver}\n', encoding='utf-8')

    _cached_version = ver
    return ver


# ---------------------------------------------------------------------------
# PEP 517 Standard Hooks
# ---------------------------------------------------------------------------


def get_requires_for_build_wheel(config_settings=None):
    _ensure_version()
    return _orig.get_requires_for_build_wheel(config_settings)


def get_requires_for_build_sdist(config_settings=None):
    _ensure_version()
    return _orig.get_requires_for_build_sdist(config_settings)


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    _ensure_version()
    return _orig.prepare_metadata_for_build_wheel(metadata_directory, config_settings)


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    _ensure_version()
    return _orig.build_wheel(wheel_directory, config_settings, metadata_directory)


def build_sdist(sdist_directory, config_settings=None):
    _ensure_version()
    return _orig.build_sdist(sdist_directory, config_settings)


# ---------------------------------------------------------------------------
# PEP 660 Editable Installation Hooks (pip install -e .)
# ---------------------------------------------------------------------------


def get_requires_for_build_editable(config_settings=None):
    _ensure_version()
    return _orig.get_requires_for_build_editable(config_settings)


def prepare_metadata_for_build_editable(metadata_directory, config_settings=None):
    _ensure_version()
    return _orig.prepare_metadata_for_build_editable(metadata_directory, config_settings)


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    _ensure_version()
    return _orig.build_editable(wheel_directory, config_settings, metadata_directory)


# ---------------------------------------------------------------------------
# Fallback / Passthrough
# ---------------------------------------------------------------------------


def __getattr__(name: str):
    """Pass through any unhandled hooks or attributes to setuptools.build_meta."""
    return getattr(_orig, name)
