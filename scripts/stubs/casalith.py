"""Stub casalith module to prevent modular CASA MPI import deadlocks.

See CAS-12799, CAS-14037, PIPE-1669, and CAS-14027.

In modular CASA (wheels), `casalith` is not installed by default. This causes
`casatasks` to start MPI services (`casampi.private.start_mpi`) during its own
`__init__.py`, holding Python's module import lock and deadlocking when worker
ranks attempt to import packages that depend on `casatasks` (like Pipeline).

Providing this stub defers MPI startup to `casashell`'s `init_system.py`, matching
the behavior of monolithic CASA without holding module locks.
"""

from __future__ import annotations

import importlib.metadata


def version() -> list[int]:
    """Return the version list dynamically from casashell, casatools, or metadata."""
    try:
        import casashell

        return list(casashell.version())
    except Exception:
        pass
    try:
        import casatools

        return [int(x) for x in casatools.version()]
    except Exception:
        pass
    try:
        ver = importlib.metadata.version('casashell')
    except Exception:
        try:
            ver = importlib.metadata.version('casatools')
        except Exception:
            ver = '0.0.0'
    return [int(x) for x in ver.split('.')[:4] if x.isdigit()]


def version_string() -> str:
    """Return the version string dynamically from casashell, casatools, or metadata."""
    try:
        import casashell

        return str(casashell.version_string())
    except Exception:
        pass
    try:
        import casatools

        return str(casatools.version_string())
    except Exception:
        pass
    try:
        return importlib.metadata.version('casashell')
    except Exception:
        try:
            return importlib.metadata.version('casatools')
        except Exception:
            return '0.0.0'
