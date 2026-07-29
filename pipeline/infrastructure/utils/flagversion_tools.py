"""Utility functions for remapping CASA flag version tables.

When an MS is transformed (e.g. via mstransform with field/spw selection),
the row order and DATA_DESC_ID numbering can change.  The functions here
allow all flag versions saved against the original MS to be remapped so they
can be directly restored onto the transformed MS.

Algorithm
---------
1. :func:`_build_row_perm` computes an integer array ``perm`` of length
   N_target such that ``perm[i]`` is the row in ms_source whose visibility
   key (DATA_DESC_ID, FIELD_ID, ANTENNA2, ANTENNA1, TIME) matches row *i* of
   ms_target.  When ``remap_ids=True`` the DDID and FIELD_ID values of
   ms_target are first translated back to the original numbering via SPW
   REF_FREQUENCY matching and field PHASE_DIR (phase centre) matching
   respectively.

2. :func:`_remap_flagversion` applies the permutation to a flag version table
   via ``selectrows(perm).copy()``.  This builds the output directly in target
   row order, correctly handling both pure reorder (N_target == N_source) and
   row selection (N_target < N_source) while preserving TiledShapeStMan tile
   geometry and per-row FLAG shapes.

3. :func:`transfer_flagversion` is the public entry point.  It computes
   ``perm`` once and applies it to every ``flags.*`` subdirectory found in
   ``source_flagversions``.
"""
from __future__ import annotations

import os
import shutil

import numpy as np

from pipeline.infrastructure import casa_tools, logging

LOG = logging.get_logger(__name__)

# Tolerance for phase-centre matching in _build_row_perm when remap_ids=True.
# mstransform preserves PHASE_DIR bit-for-bit, so genuine matches have zero
# separation; 1 mas (4.848e-9 rad) admits floating-point noise while
# remaining far below any real inter-field spacing.
_FIELD_MATCH_TOL_RAD = np.deg2rad(1.0 / 3_600_000)  # 1 mas in radians

__all__ = ['transfer_flagversion']


def _build_row_perm(
    ms_source: str,
    ms_target: str,
    remap_ids: bool = False,
) -> np.ndarray:
    """Compute perm[new_row] = orig_row mapping ms_target rows back to ms_source.

    Args:
        ms_source: Path to the original MS.
        ms_target: Path to the transformed MS.
        remap_ids: If True, remap DATA_DESC_ID via SPW REF_FREQUENCY matching
            and FIELD_ID via PHASE_DIR (phase centre) matching before key
            comparison.  Set this when ms_target was produced with
            mstransform's default reindex=True.  When False (default),
            DATA_DESC_ID and FIELD_ID
            values are compared directly, which is correct for reindex=False.

    Returns:
        perm: int64 array of length N_target; perm[i] is the row in ms_source
            whose visibility key matches row i of ms_target.

    Raises:
        ValueError: if any row in ms_target has no exact-key match in ms_source,
            or if two source fields share an identical phase centre (only when
            remap_ids=True).

    Notes:
        Memory management: dominant allocations are ``k_orig`` (~N_source × 24 B),
        ``keys_orig`` struct (~N_source × 24 B), ``idx_orig_sorted``
        (~N_source × 8 B), and ``keys_orig_sorted`` (~N_source × 24 B).  Explicit
        ``del`` statements free each as soon as possible; peak is ~N_source × 56 B
        when ``keys_orig``, ``idx_orig_sorted``, and ``keys_orig_sorted`` all
        overlap during the sort step.  Validation iterates one struct field at a
        time to avoid a full N_target × 24 B matched-row copy; the largest
        per-field temporary is N_target × 8 B (the TIME field).
    """
    # Load key columns from both MSes.
    with casa_tools.TableReader(ms_source) as tb:
        k_orig = {c: tb.getcol(c) for c in ('TIME', 'ANTENNA1', 'ANTENNA2', 'DATA_DESC_ID', 'FIELD_ID')}
    with casa_tools.TableReader(ms_target) as tb:
        k_new = {c: tb.getcol(c) for c in ('TIME', 'ANTENNA1', 'ANTENNA2', 'DATA_DESC_ID', 'FIELD_ID')}
    LOG.debug('_build_row_perm: %d source rows, %d target rows, remap_ids=%s',
              len(k_orig['TIME']), len(k_new['TIME']), remap_ids)

    if remap_ids:
        # Build new_ddid → orig_ddid mapping via SPW REF_FREQUENCY matching.
        # Assumes no frequency regridding so REF_FREQUENCY is preserved.
        with casa_tools.TableReader(os.path.join(ms_source, 'DATA_DESCRIPTION')) as tb:
            orig_dd_spw = tb.getcol('SPECTRAL_WINDOW_ID')   # orig_ddid → orig_spw_id
        with casa_tools.TableReader(os.path.join(ms_source, 'SPECTRAL_WINDOW')) as tb:
            orig_spw_freq = tb.getcol('REF_FREQUENCY')       # orig_spw_id → freq
        with casa_tools.TableReader(os.path.join(ms_target, 'DATA_DESCRIPTION')) as tb:
            new_dd_spw = tb.getcol('SPECTRAL_WINDOW_ID')     # new_ddid → new_spw_id
        with casa_tools.TableReader(os.path.join(ms_target, 'SPECTRAL_WINDOW')) as tb:
            new_spw_freq = tb.getcol('REF_FREQUENCY')        # new_spw_id → freq

        new_spw_to_orig_spw: dict[int, int] = {}
        for new_spw, freq in enumerate(new_spw_freq):
            best = int(np.argmin(np.abs(orig_spw_freq - freq)))
            if abs(orig_spw_freq[best] - freq) > 1.0:
                raise ValueError(
                    f'No matching orig SPW for new SPW {new_spw} (REF_FREQUENCY={freq:.3f} Hz)'
                )
            new_spw_to_orig_spw[new_spw] = best
            LOG.debug('SPW map: new %d (%.3f Hz) -> orig %d (%.3f Hz)',
                      new_spw, freq, best, orig_spw_freq[best])

        orig_spw_to_ddid = {int(spw): int(ddid) for ddid, spw in enumerate(orig_dd_spw)}
        if len(orig_spw_to_ddid) != len(orig_dd_spw):
            raise ValueError(
                'ms_source DATA_DESCRIPTION table has multiple DDIDs sharing the '
                'same SPECTRAL_WINDOW_ID; remap_ids=True requires a unique SPW '
                'per DDID'
            )
        ddid_map = np.array(
            [orig_spw_to_ddid[new_spw_to_orig_spw[int(new_dd_spw[nd])]] for nd in range(len(new_dd_spw))],
            dtype=np.int32,
        )
        orig_ddid_for_new = ddid_map[k_new['DATA_DESC_ID']]  # (N_new,) orig DDID per new row

        # Build new_field_id → orig_field_id mapping via PHASE_DIR (phase centre)
        # matching.  mstransform renumbers field IDs when field selection is
        # applied, so the raw FIELD_ID values in ms_target cannot be used directly.
        # Phase centres are matched rather than field NAMEs to avoid ambiguity when
        # two distinct fields share the same name.
        with casa_tools.TableReader(os.path.join(ms_source, 'FIELD')) as tb:
            orig_phase_dir = tb.getcol('PHASE_DIR')  # shape (2, n_poly, n_orig_fields)
        with casa_tools.TableReader(os.path.join(ms_target, 'FIELD')) as tb:
            new_phase_dir = tb.getcol('PHASE_DIR')  # shape (2, n_poly, n_new_fields)

        # Flatten to (n_fields, 2) arrays of [RA, Dec] in radians using the
        # zeroth-order polynomial term (axis 1, index 0).
        orig_dirs = orig_phase_dir[:, 0, :].T  # (n_orig, 2)
        new_dirs = new_phase_dir[:, 0, :].T  # (n_new, 2)

        # Flat-sky approximation: valid only for near-identical directions, which
        # is guaranteed here since mstransform preserves phase centres bit-for-bit.
        field_map = np.empty(len(new_dirs), dtype=np.int32)
        for new_fid, nd in enumerate(new_dirs):
            sep = np.hypot((orig_dirs[:, 0] - nd[0]) * np.cos(nd[1]), orig_dirs[:, 1] - nd[1])
            best = int(np.argmin(sep))
            if sep[best] > _FIELD_MATCH_TOL_RAD:
                raise ValueError(
                    f'No matching orig field for new field {new_fid} '
                    f'(PHASE_DIR=[{np.degrees(nd[0]):.6f}, {np.degrees(nd[1]):.6f}] deg); '
                    f'closest orig field {best} is {np.degrees(sep[best]) * 3600:.2f} arcsec away'
                )
            if (sep <= _FIELD_MATCH_TOL_RAD).sum() > 1:
                raise ValueError(
                    f'Multiple orig fields within {_FIELD_MATCH_TOL_RAD:.0e} rad of new field '
                    f'{new_fid}; phase-centre matching is ambiguous'
                )
            field_map[new_fid] = best
            LOG.debug('Field map: new %d -> orig %d (sep=%.3e rad)', new_fid, best, sep[best])
        orig_field_for_new = field_map[k_new['FIELD_ID']]  # (N_new,) orig FIELD_ID per new row

    # Build perm[new_row] = orig_row via structured-array exact key matching.
    # Pack (orig_ddid, orig_field, ant2, ant1, TIME_bits) into a structured array,
    # sort ms_source by it, then searchsorted to find each new row's position.
    key_dtype = np.dtype([('d', np.int32), ('f', np.int32),
                          ('a2', np.int32), ('a1', np.int32), ('t', np.int64)])

    keys_orig = np.empty(len(k_orig['TIME']), dtype=key_dtype)
    keys_orig['d'] = k_orig['DATA_DESC_ID']
    keys_orig['f'] = k_orig['FIELD_ID']
    keys_orig['a2'] = k_orig['ANTENNA2']
    keys_orig['a1'] = k_orig['ANTENNA1']
    # np.asarray(..., dtype=np.float64) normalises to native byte order so that
    # the subsequent view(int64) reinterprets the correct bits on every platform.
    keys_orig['t'] = np.asarray(k_orig['TIME'], dtype=np.float64).view(np.int64)
    del k_orig
    idx_orig_sorted = np.argsort(keys_orig, order=('d', 'f', 'a2', 'a1', 't'))
    keys_orig_sorted = keys_orig[idx_orig_sorted]
    del keys_orig

    keys_new = np.empty(len(k_new['TIME']), dtype=key_dtype)
    if remap_ids:
        keys_new['d'] = orig_ddid_for_new
        del orig_ddid_for_new
        keys_new['f'] = orig_field_for_new
        del orig_field_for_new
    else:
        keys_new['d'] = k_new['DATA_DESC_ID']
        keys_new['f'] = k_new['FIELD_ID']
    keys_new['a2'] = k_new['ANTENNA2']
    keys_new['a1'] = k_new['ANTENNA1']
    keys_new['t'] = np.asarray(k_new['TIME'], dtype=np.float64).view(np.int64)
    del k_new

    pos = np.searchsorted(keys_orig_sorted, keys_new)
    # Validate that every target key was found; searchsorted returns an
    # insertion index for missing keys without raising.
    clipped = np.minimum(pos, len(keys_orig_sorted) - 1)
    no_match = pos >= len(keys_orig_sorted)
    # Access one field at a time to avoid materialising a full struct copy of
    # keys_orig_sorted[clipped] (which would be N_target × 24 bytes).
    for fname in keys_new.dtype.names:
        no_match |= (keys_orig_sorted[fname][clipped] != keys_new[fname])
    if no_match.any():
        raise ValueError(
            f'{int(no_match.sum())} row(s) in ms_target have no matching row in '
            'ms_source; verify that ms_target was produced from ms_source without '
            'modifications to TIME, ANTENNA1, ANTENNA2, DATA_DESC_ID, or FIELD_ID'
        )
    perm = idx_orig_sorted[pos]
    del idx_orig_sorted, keys_orig_sorted, keys_new, pos, clipped, no_match
    LOG.debug('_build_row_perm: perm built, %d target rows mapped', len(perm))

    return perm


def _remap_flagversion(
    perm: np.ndarray,
    flagver_source_path: str,
    flagver_target_path: str,
) -> None:
    """Copy flagver_source_path to flagver_target_path with rows remapped via perm.

    Two execution paths:

    1. **Identity** (``perm == arange(n)``): ``shutil.copytree`` only.
    2. **General**: ``selectrows(perm).copy()`` builds the output table directly
       in target row order.  This handles both pure reorder (N_target ==
       N_source) and row selection (N_target < N_source).  Each output row
       inherits its FLAG shape from the corresponding source row, so no
       TiledShapeStMan shape conflicts can arise.

    Args:
        perm: int64 array; perm[i] is the source row for output row i.
        flagver_source_path: Path to the source flag version table.
        flagver_target_path: Path for the output flag version table.
            Removed and re-created if it already exists.
    """
    if os.path.exists(flagver_target_path):
        shutil.rmtree(flagver_target_path)

    n = len(perm)

    # Identity fast path: source and target have the same rows in the same order.
    if np.array_equal(perm, np.arange(n, dtype=perm.dtype)):
        LOG.debug('_remap_flagversion: identity perm (%d rows), using direct copy', n)
        shutil.copytree(flagver_source_path, flagver_target_path)
        return

    # General path: build the output table directly in target row order.
    # Each output row inherits its FLAG shape from the corresponding source
    # row, so no TiledShapeStMan "shape cannot be changed" errors can arise.
    LOG.debug('_remap_flagversion: %d rows, building via selectrows copy', n)
    with casa_tools.TableReader(flagver_source_path) as tb_src:
        sub = tb_src.selectrows(perm.tolist())
        try:
            sub.copy(flagver_target_path, deep=True)
        finally:
            sub.close()
    LOG.debug('_remap_flagversion: complete, %d rows to %s', n, flagver_target_path)


def transfer_flagversion(
    ms_source: str,
    ms_target: str,
    source_flagversions: str | None = None,
    target_flagversions: str | None = None,
    remap_ids: bool = False,
) -> None:
    """Transfer all flag versions under source_flagversions to target_flagversions.

    Iterates over every ``flags.*`` subdirectory in ``source_flagversions``
    and remaps each one so it can be directly restored onto ``ms_target``.
    The row permutation is computed once and reused across all versions.

    Set ``remap_ids=True`` when mstransform was called with its default
    ``reindex=True`` so that renumbered DATA_DESC_ID and FIELD_ID values are
    translated back to the original numbering before row matching.
    When mstransform is called with ``reindex=False`` the IDs are preserved
    and ``remap_ids`` can be left at its default of False.

    When remap_ids=True, SPW matching uses nearest REF_FREQUENCY (1 Hz
    tolerance), which requires no frequency regridding (regridms=False, the
    mstransform default) and no combinespws.  Violating either constraint
    raises ValueError at the SPW-matching step.

    Args:
        ms_source: Path to the original MS the flag versions were saved against.
        ms_target: Path to the transformed MS to produce the flag versions for.
        source_flagversions: Directory containing the ``flags.*`` tables to
            transfer.  Defaults to ``ms_source + '.flagversions'``.
        target_flagversions: Destination directory for the remapped ``flags.*``
            tables.  Created if it does not exist.  Defaults to
            ``ms_target + '.flagversions'``.
        remap_ids: If True, remap DATA_DESC_ID and FIELD_ID before row
            matching.  Required when ms_target was produced by mstransform
            with its default reindex=True.  Defaults to False (correct for
            reindex=False).
    """
    if source_flagversions is None:
        source_flagversions = f'{ms_source}.flagversions'
    if target_flagversions is None:
        target_flagversions = f'{ms_target}.flagversions'

    if not os.path.isdir(source_flagversions):
        raise ValueError(f'source_flagversions does not exist: {source_flagversions}')

    version_names = sorted(
        e for e in os.listdir(source_flagversions)
        if e.startswith('flags.') and os.path.isdir(os.path.join(source_flagversions, e))
    )
    if not version_names:
        LOG.warning('No flag versions found in %s', source_flagversions)
        return

    LOG.info('Transferring %d flag version(s) from %s', len(version_names), source_flagversions)

    perm = _build_row_perm(ms_source, ms_target, remap_ids=remap_ids)

    os.makedirs(target_flagversions, exist_ok=True)

    # Copy the version-list metadata file if present.
    fvl_src = os.path.join(source_flagversions, 'FLAG_VERSION_LIST')
    if os.path.exists(fvl_src):
        shutil.copy2(fvl_src, os.path.join(target_flagversions, 'FLAG_VERSION_LIST'))

    for vname in version_names:
        LOG.info('Transferring flag version %s', vname)
        _remap_flagversion(
            perm,
            os.path.join(source_flagversions, vname),
            os.path.join(target_flagversions, vname),
        )

    LOG.info('All %d flag version(s) transferred to %s', len(version_names), target_flagversions)
