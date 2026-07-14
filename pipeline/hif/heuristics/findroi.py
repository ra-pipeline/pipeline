from __future__ import annotations

import __main__ as _main
import copy
import datetime as dt
import os
import pickle
import re
import shutil
import tarfile
import time
from typing import Any

import numpy as np

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.mpihelpers as mpihelpers
from pipeline.domain import DataType
from pipeline.hif.heuristics import imageparams_factory
from pipeline.infrastructure import casa_tasks, casa_tools
from pipeline.infrastructure.filenamer import PipelineProductNameBuilder
from pipeline.infrastructure.utils import imaging

LOG = infrastructure.get_logger(__name__)

try:
    from pipeline.infrastructure.mpihelpers import TaskQueue
except Exception:
    try:
        import casampi as _casampi
        _COMM = _casampi.MPI.COMM_WORLD
    except Exception:
        try:
            from mpi4py import MPI as _MPI
            _COMM = _MPI.COMM_WORLD
        except Exception:
            _COMM = None

    class TaskQueue:
        def __init__(self, parallel: bool = True, comm: Any | None = None) -> None:
            self.comm = comm if comm is not None else _COMM
            self.parallel = bool(parallel and self.comm is not None)
            self.rank = self.comm.rank if self.parallel else 0
            self.size = self.comm.size if self.parallel else 1
            self._results = None

        def __enter__(self) -> 'TaskQueue':
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
            return False

        def map(self, func: Any, args: list[tuple[Any, ...]]) -> None:
            if not self.parallel:
                self._results = [func(*a) for a in args]
                return
            local = [(i, func(*a)) for i, a in enumerate(args) if (i % self.size) == self.rank]
            gathered = self.comm.gather(local, root=0)
            if self.rank == 0:
                flat = []
                for chunk in gathered:
                    if chunk:
                        flat.extend(chunk)
                flat.sort(key=lambda x: x[0])
                self._results = [v for _, v in flat]
            else:
                self._results = None

        def get_results(self) -> list[Any] | None:
            return self._results


AU_DAY_TO_M_S = 1731.45683633 * 1000.0
_DEFAULT_FINDROI_CONFIG = {
    'timebin_sec': 240.0,
    'min_nchan': 128,
    'npix': 256,
    'fov_pb_mult': 1.5,
    'ref_sigma': 3.0,
    'mom0_thresh_sigma': 5.0,
    'gate_sigma': 1.0,
    'pos_evidence_thr': 5.0,
    'neg_evidence_thr': 7.0,
    'evidence_thr': None,
    'evidence_bin_scales': (1, 2, 3, 4, 5, 6, 8, 10, 20, 40, 60, 80),
    'ref_zero_frac_thr': 0.05,
    'mom0_zero_frac_thr': 0.05,
    'ref_smooth_width': 4,
    'mom0_smooth_width': 4,
    'neg_extent_delta_thr': 5.0,
    'neg_extent_trim_frac': 0.10,
    'acf_edge_trim_frac': 0.10,
    'acf_smooth_frac': 0.20,
    'fwhm_global_fallback_factor': 5.0,
    'fwhm_min_chan': 4,
    'rolling_rms_window': 10,
    'rolling_rms_target_unsmoothed': 0.87,
    'rolling_rms_target_smoothed': 0.66,
    'uv_taper_auto': True,
    'uv_taper_sigma_uv': None,
    'uv_taper_fwhm_cell': 2.0,
    'roi_thresh': 7.0,
    'roi_cont_thresh': 7.0,
    'tmp_overwrite': True,
    'save_moment0': True,
    'save_cube': True,
    'verbose': True,
}

# Optional per-rank profiling logs used to diagnose stage runtime hotspots.
def _profile_path(log_dir: str | None) -> str | None:
    use_dir = log_dir if log_dir else _PROFILE_DEFAULT_DIR
    if not use_dir:
        return None
    use_dir = os.path.join(use_dir, 'logs')
    os.makedirs(use_dir, exist_ok=True)
    rank, _ = _mpi_rank_size()
    return os.path.join(use_dir, f'profile_rank{rank}.txt')


def _profile_log(log_dir: str | None, message: str) -> None:
    path = _profile_path(log_dir)
    if path is None:
        return
    ts = dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(path, 'a', encoding='utf-8') as fh:
        fh.write(f'[{ts}] {message}\n')


def _profile_logf(log_dir: str | None, fmt: str, *args: Any) -> None:
    try:
        msg = fmt % args if args else fmt
    except Exception:
        msg = fmt
    _profile_log(log_dir, msg)


def _set_profile_default_dir(log_dir: str | None) -> None:
    global _PROFILE_DEFAULT_DIR
    _PROFILE_DEFAULT_DIR = log_dir
GridDiag = dict
GridPrecompute = tuple
_PB_IMAGE_CACHE: dict[tuple[int, int, float, float, float], tuple[np.ndarray, np.ndarray]] = {}
_EPHEM_RADVEL_CACHE: dict[tuple[str, int], tuple[str, np.ndarray, np.ndarray]] = {}
_PROFILE_DEFAULT_DIR: str | None = None


def _get_tb() -> Any:
    '''Return the CASA table tool from the interactive namespace.'''
    tb_obj = getattr(_main, 'tb', None)
    if tb_obj is None:
        try:
            from casatools import table as tbtool
        except Exception as exc:
            raise RuntimeError('tb is not defined; run inside CASA with tb available.') from exc
        tb_obj = tbtool()
        setattr(_main, 'tb', tb_obj)
    return tb_obj


def _mpi_rank_size() -> tuple[int, int]:
    '''Return current MPI rank and size if available, otherwise (0, 1).'''
    try:
        import casampi as _casampi
        comm = _casampi.MPI.COMM_WORLD
        return int(comm.rank), int(comm.size)
    except Exception:
        try:
            from mpi4py import MPI as _MPI
            comm = _MPI.COMM_WORLD
            return int(comm.rank), int(comm.size)
        except Exception:
            return 0, 1


def _rank_log(tmp_dir: str | None, msg: str) -> None:
    '''Append a message to a per-rank log file when a tmp_dir is provided.'''
    rank, size = _mpi_rank_size()
    if not tmp_dir:
        return
    try:
        log_dir = os.path.join(tmp_dir, 'logs')
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, f'mpi_rank{rank}.log')
        with open(path, 'a', encoding='ascii') as fh:
            fh.write(msg + '\n')
    except Exception:
        pass


def _rank_logf(tmp_dir: str | None, fmt: str, *args: Any) -> None:
    '''Format and write one message into the per-rank log file.'''
    if args:
        try:
            msg = fmt % args
        except Exception:
            msg = f'{fmt} {args}'
    else:
        msg = fmt
    _rank_log(tmp_dir, msg)


def _rank_diag(tmp_dir: str | None, msg: str) -> None:
    '''Append a message to a per-rank diagnostics text file.'''
    rank, size = _mpi_rank_size()
    if not tmp_dir:
        return
    try:
        diagnostics_dir = os.path.join(tmp_dir, 'diagnostics')
        os.makedirs(diagnostics_dir, exist_ok=True)
        path = os.path.join(diagnostics_dir, f'grid_diagnostics_rank{rank}.txt')
        with open(path, 'a', encoding='ascii') as fh:
            fh.write(msg + '\n')
    except Exception:
        pass


def _rank_diagf(tmp_dir: str | None, fmt: str, *args: Any) -> None:
    '''Format and append one message to a per-rank diagnostics text file.'''
    if args:
        try:
            msg = fmt % args
        except Exception:
            msg = f'{fmt} {args}'
    else:
        msg = fmt
    _rank_diag(tmp_dir, msg)


def _ensure_row_chan_pol(
    arr: np.ndarray,
    nrow_expected: int,
    npol_hint: tuple[int, ...] = (1, 2, 4),
) -> np.ndarray:
    '''Reorder DATA array into (row, chan, pol) format.'''
    arr = np.asarray(arr)
    if arr.ndim != 3:
        raise RuntimeError(f'Expected 3D array, got {arr.shape}')
    sh = arr.shape
    axes = [0, 1, 2]
    row_axes = [ax for ax in axes if sh[ax] == nrow_expected]
    if len(row_axes) != 1:
        raise RuntimeError(
            f'Cannot identify row axis for nrow={nrow_expected} from shape {sh}'
        )
    ax_row = row_axes[0]
    cand_pol = [ax for ax in axes if ax != ax_row and sh[ax] in npol_hint]
    if not cand_pol:
        raise RuntimeError(f'Cannot identify pol axis from shape {sh}')
    ax_pol = min(cand_pol, key=lambda ax: sh[ax])
    ax_chan = [ax for ax in axes if ax not in (ax_row, ax_pol)][0]
    return np.transpose(arr, (ax_row, ax_chan, ax_pol))


def resolve_vis_list(vis: str | list[str] | tuple[str, ...]) -> list[str]:
    '''Resolve a vis input into a list of MS paths.'''
    if isinstance(vis, (list, tuple)):
        return list(vis)
    vis = str(vis)
    if os.path.isdir(vis):
        files = [
            os.path.join(vis, f) for f in os.listdir(vis) if f.endswith('_targets.ms')
        ]
        files = sorted([f for f in files if os.path.isdir(f)])
        if files:
            return files
    return [vis]


def _context_ms_for_vis(context: Any, vis: str) -> Any:
    '''Return the context MeasurementSet matching a vis path or basename.'''
    try:
        return context.observing_run.get_ms(vis)
    except Exception:
        pass
    try:
        return context.observing_run.get_ms(os.path.basename(os.path.normpath(vis)))
    except Exception as exc:
        raise RuntimeError(f'No pipeline MeasurementSet found in context for {vis}.') from exc


def _resolve_pipeline_vis_list(context: Any, vis: Any) -> list[str]:
    '''Resolve vis through pipeline context, falling back to prototype resolution.'''
    if vis not in (None, '', [], ['']):
        return resolve_vis_list(vis)
    datatypes = [
        DataType.SELFCAL_CONTLINE_SCIENCE,
        DataType.REGCAL_CONTLINE_SCIENCE,
        DataType.REGCAL_CONTLINE_ALL,
        DataType.RAW,
    ]
    ms_objects, selected_datatype = context.observing_run.get_measurement_sets_of_type(
        dtypes=datatypes,
        msonly=False,
    )
    if not ms_objects:
        raise RuntimeError('No suitable measurement sets found for hif_findroi.')
    LOG.info('Using data type %s for hif_findroi.', str(selected_datatype).split('.')[-1])
    if selected_datatype == DataType.RAW:
        LOG.warning('Falling back to raw data for hif_findroi.')
    return [ms.name for ms in ms_objects.keys()]


def _findroi_antenna_selections(context: Any, vis_list: list[str], intent: str = 'TARGET') -> dict[str, str]:
    '''Return per-vis CASA antenna selections matching imaging antenna policy.'''
    canonical_vis_list = [_context_ms_for_vis(context, vis).name for vis in vis_list]
    project_structure = getattr(context, 'project_structure', None)
    imagename_prefix = '' if project_structure is None else getattr(project_structure, 'ousstatus_entity_id', '')
    heuristics = imageparams_factory.ImageParamsHeuristicsFactory.getHeuristics(
        vislist=canonical_vis_list,
        spw='',
        observing_run=context.observing_run,
        imagename_prefix=imagename_prefix,
        proj_params=getattr(context, 'project_performance_parameters', None),
        contfile=None,
        linesfile=None,
        imaging_params=getattr(context, 'imaging_parameters', None),
        processing_intents=getattr(context, 'processing_intents', None),
        imaging_mode='ALMA',
    )
    antenna_ids = heuristics.antenna_ids(intent, vislist=canonical_vis_list)
    selections: dict[str, str] = {}
    for vis, canonical_vis in zip(vis_list, canonical_vis_list):
        antenna_id_list = antenna_ids.get(os.path.basename(canonical_vis))
        if not antenna_id_list:
            raise RuntimeError(f'No {intent} antenna selection determined for hif_findroi vis={vis}.')
        selections[vis] = ','.join(map(str, antenna_id_list)) + '&'
    return selections


def _field_task_arg(field: str | int | list[int | str] | tuple[int | str, ...] | None) -> str | int | None:
    '''Normalize explicit field selection into one CASA-style task argument.'''
    if field is None or field in ('', 'target', 'target_groups'):
        return None
    if isinstance(field, (list, tuple, set)):
        return ','.join(str(v) for v in field)
    return field


def _field_ids_from_input(
    vis: str,
    field: str | int | list[int | str] | tuple[int | str, ...] | None,
    all_fields: Any | None = None,
) -> list[int] | None:
    '''Convert explicit field input to field IDs; return None for automatic target selection.'''
    task_arg = _field_task_arg(field)
    if task_arg is None:
        return None
    from pipeline.infrastructure.utils import conversion
    return [int(v) for v in conversion.field_arg_to_id(vis, task_arg, all_fields or [])]


def _context_field_groups_by_source_id(
    context: Any,
    vis: str,
    field: str | int | list[int | str] | tuple[int | str, ...] | None,
) -> dict[str, Any] | None:
    '''Build field/source groups from hifa_importdata context when available.'''
    ms = _context_ms_for_vis(context, vis)
    explicit_fields = _field_ids_from_input(ms.name, field, getattr(ms, 'fields', []))
    target_intents = {'TARGET', 'OBSERVE_TARGET', 'SCIENCE'}
    selected_fields = []
    for field_obj in getattr(ms, 'fields', []):
        if explicit_fields is not None:
            if int(field_obj.id) in explicit_fields:
                selected_fields.append(field_obj)
        elif not set(getattr(field_obj, 'intents', set())).isdisjoint(target_intents):
            selected_fields.append(field_obj)
    if not selected_fields:
        if explicit_fields is not None:
            raise RuntimeError(f'No fields matched hif_findroi field={field!r} for {vis}.')
        return None
    max_field_id = max(int(f.id) for f in getattr(ms, 'fields', []))
    field_names = [''] * (max_field_id + 1)
    source_ids = np.zeros(max_field_id + 1, dtype=int)
    intents_per_field: list[set[str]] = [set() for _ in range(max_field_id + 1)]
    for field_obj in getattr(ms, 'fields', []):
        fid = int(field_obj.id)
        field_names[fid] = str(field_obj.name)
        source_ids[fid] = int(field_obj.source_id)
        intents_per_field[fid] = set(getattr(field_obj, 'intents', set()))

    source_names = {int(src.id): str(src.name) for src in getattr(ms, 'sources', [])}
    groups: dict[int, list[int]] = {}
    for field_obj in selected_fields:
        groups.setdefault(int(field_obj.source_id), []).append(int(field_obj.id))
    return {
        'field_names': field_names,
        'source_ids': source_ids,
        'source_names': source_names,
        'intents_per_field': intents_per_field,
        'groups': {sid: sorted(fids) for sid, fids in groups.items()},
    }


def _spw_ids_from_input(spw: str | int | list[int] | tuple[int, ...] | None) -> set[int] | None:
    '''Convert optional user SPW selection into an integer set.'''
    if spw in (None, '', [], ['']):
        return None
    if isinstance(spw, str):
        return {int(v) for v in spw.split(',') if v.strip()}
    if isinstance(spw, (list, tuple, set)):
        return {int(v) for v in spw}
    return {int(spw)}


def _filter_science_ddids(
    inv: list[dict[str, Any]],
    sci_ddids: list[int],
    spw: str | int | list[int] | tuple[int, ...] | None,
    context: Any | None,
    vis0: str,
) -> list[int]:
    '''Filter selected DDIDs by public virtual SPW IDs when context is available.'''
    selected_spws = _spw_ids_from_input(spw)
    if selected_spws is None:
        return sci_ddids
    ddids = []
    ms0 = _context_ms_for_vis(context, vis0)
    for row in inv:
        ddid = int(row['ddid'])
        if ddid not in sci_ddids:
            continue
        row_spw_id = int(row['spw_id'])
        virtual_spw_id = row_spw_id
        if context is not None and ms0 is not None:
            mapped = context.observing_run.real2virtual_spw_id(row_spw_id, ms0)
            if mapped is not None:
                virtual_spw_id = int(mapped)
        if virtual_spw_id in selected_spws or row_spw_id in selected_spws or ddid in selected_spws:
            ddids.append(ddid)
    return ddids


def _real_spw_ids_by_vis(
    context: Any | None,
    vis_list: list[str],
    virtual_spw_id: int | None,
    fallback_spw_id: int,
) -> dict[str, int]:
    '''Build per-MS real SPW ID mapping for a virtual science SPW.'''
    out: dict[str, int] = {}
    for vis in vis_list:
        real_spw = fallback_spw_id
        ms = _context_ms_for_vis(context, vis)
        if context is not None and ms is not None and virtual_spw_id is not None:
            mapped = context.observing_run.virtual2real_spw_id(int(virtual_spw_id), ms)
            if mapped is not None:
                real_spw = int(mapped)
        out[vis] = int(real_spw)
        out[os.path.basename(os.path.normpath(vis))] = int(real_spw)
    return out


def get_chan_freqs_hz(ms: Any, ddid: int = 0) -> np.ndarray:
    '''Return channel frequencies for an imported pipeline DDID.'''
    dd = ms.get_data_description(id=int(ddid))
    if dd is None or getattr(dd, 'spw', None) is None:
        raise RuntimeError(f'No pipeline data description found for DDID {ddid}.')
    chan_freqs = getattr(getattr(dd.spw, 'channels', None), 'chan_freqs', None)
    if chan_freqs is None:
        freq = np.zeros((0,), dtype=np.float64)
    elif isinstance(chan_freqs, np.ndarray):
        freq = np.asarray(chan_freqs, dtype=np.float64).ravel()
    else:
        freq = np.asarray(list(chan_freqs), dtype=np.float64).ravel()
    if freq.size == 0:
        raise RuntimeError(f'No pipeline channel frequencies found for DDID {ddid}.')
    return freq


def _get_temp_ms_chan_freqs_hz(vis: str, ddid: int = 0) -> np.ndarray:
    '''Return channel frequencies for a temporary regridded MS product.'''
    tb_obj = _get_tb()
    tb_obj.open(vis + '/DATA_DESCRIPTION')
    spw_id = int(np.asarray(tb_obj.getcol('SPECTRAL_WINDOW_ID')).ravel()[ddid])
    tb_obj.close()
    tb_obj.open(vis + '/SPECTRAL_WINDOW')
    freqs = np.asarray(tb_obj.getcell('CHAN_FREQ', int(spw_id)), dtype=np.float64).ravel()
    tb_obj.close()
    return freqs


def get_ddid_spw_inventory(vis: str, ms: Any) -> list[dict[str, Any]]:
    '''Return DDID/SPW inventory from imported pipeline metadata plus MAIN row counts.'''
    dd_rows = []
    for dd in getattr(ms, 'data_descriptions', []):
        spw = getattr(dd, 'spw', None)
        if spw is None:
            continue
        dd_rows.append({
            'ddid': int(dd.id),
            'spw_id': int(spw.id),
            'nchan': int(len(getattr(spw, 'channels', ()))),
            'name': str(getattr(spw, 'name', '')),
        })
    dd_rows.sort(key=lambda row: row['ddid'])
    rows = []
    tb_obj = _get_tb()
    tb_obj.open(vis)
    for row in dd_rows:
        ddid = int(row['ddid'])
        nrows = 0
        try:
            sub = tb_obj.query(f'DATA_DESC_ID=={ddid}')
            nrows = int(sub.nrows())
            sub.close()
        except Exception:
            nrows = 0
        rows.append(dict(row, nrows=int(nrows)))
    tb_obj.close()
    return rows


def select_science_ddids(
    inv: list[dict[str, Any]],
    science_spw_ids: set[int],
    min_nchan: int = 128,
) -> list[int]:
    '''Select science DDIDs using pipeline science SPWs plus local row-count filtering.'''
    out = []
    for r in inv:
        if int(r['spw_id']) not in science_spw_ids:
            continue
        if r['nchan'] < min_nchan:
            continue
        if r.get('nrows', 0) <= 0:
            continue
        out.append(int(r['ddid']))
    return out


def _get_field_ephemeris_info(vis: str, field_id: int, ephem_path: str | None = None) -> tuple[int, str]:
    '''Return (ephemeris_id, ephemeris_table_path) for a field.'''
    key = (os.path.abspath(vis), int(field_id))
    cached = _EPHEM_RADVEL_CACHE.get(key)
    if cached is not None:
        path, _, _ = cached
        base = os.path.basename(path)
        m = re.match(r'EPHEM(\d+)_', base)
        eph_id = int(m.group(1)) if m else 0
        return eph_id, path
    if ephem_path:
        path = str(ephem_path)
        if not os.path.exists(path):
            raise RuntimeError(f'Ephemeris table {path} does not exist for {vis} field {field_id}')
        base = os.path.basename(path)
        m = re.match(r'EPHEM(\d+)_', base)
        eph_id = int(m.group(1)) if m else 0
        return eph_id, path
    raise RuntimeError(f'hif_findroi requires imported ephemeris metadata for {vis} field {field_id}.')


def _get_ephemeris_radvel_series(vis: str, field_id: int, ephem_path: str | None = None) -> tuple[str, np.ndarray, np.ndarray]:
    '''Return (ephem_path, mjd, radvel_m_s) for a field ephemeris table.'''
    key = (os.path.abspath(vis), int(field_id))
    cached = _EPHEM_RADVEL_CACHE.get(key)
    if cached is not None:
        return cached
    _, ephem_path = _get_field_ephemeris_info(vis, field_id, ephem_path=ephem_path)
    tb_obj = _get_tb()
    tb_obj.open(ephem_path)
    try:
        mjd = np.asarray(tb_obj.getcol('MJD'), dtype=np.float64).ravel()
        radvel = np.asarray(tb_obj.getcol('RadVel'), dtype=np.float64).ravel()
    finally:
        tb_obj.close()
    if mjd.size == 0 or radvel.size != mjd.size:
        raise RuntimeError(f'Invalid ephemeris table {ephem_path}: MJD/RadVel mismatch')
    radvel_m_s = radvel * AU_DAY_TO_M_S
    out = (ephem_path, mjd, radvel_m_s)
    _EPHEM_RADVEL_CACHE[key] = out
    return out


def _interp_ephemeris_radvel_to_times(
    vis: str,
    field_id: int,
    times_s: np.ndarray,
    ephem_path: str | None = None,
) -> tuple[str, np.ndarray]:
    '''Interpolate ephemeris RadVel onto row TIME values and return (path, v_rad_m_s).'''
    ephem_path, mjd, radvel_m_s = _get_ephemeris_radvel_series(vis, field_id, ephem_path=ephem_path)
    t = np.asarray(times_s, dtype=np.float64).ravel()
    if t.size == 0:
        return ephem_path, np.zeros((0,), dtype=np.float64)
    mjd_row = t / 86400.0
    pad_s = 60.0
    if mjd.size >= 2:
        spacing_s = float(np.median(np.diff(mjd)) * 86400.0)
        if np.isfinite(spacing_s) and spacing_s > 0.0:
            pad_s = max(60.0, 0.5 * spacing_s)
    lo_lim = float(mjd[0] - pad_s / 86400.0)
    hi_lim = float(mjd[-1] + pad_s / 86400.0)
    if float(np.min(mjd_row)) < lo_lim or float(np.max(mjd_row)) > hi_lim:
        raise RuntimeError(
            f'Ephemeris coverage mismatch for field {field_id}: '
            f'row MJD range [{np.min(mjd_row):.8f}, {np.max(mjd_row):.8f}] outside '
            f'ephemeris [{mjd[0]:.8f}, {mjd[-1]:.8f}] with tolerance {pad_s:.1f}s'
        )
    return ephem_path, np.interp(mjd_row, mjd, radvel_m_s).astype(np.float64, copy=False)


def _ephemeris_geo_to_source_shift_hz(
    ref_freq_hz: float,
    radvel_m_s: np.ndarray,
) -> np.ndarray:
    '''Return additive GEO->SOURCE frequency shift around a reference frequency.'''
    beta = np.asarray(radvel_m_s, dtype=np.float64) / casa_tools.quanta.getvalue(
        casa_tools.quanta.convert(casa_tools.quanta.constants('c'), 'm/s')
    )[0]
    return float(ref_freq_hz) * beta


def _build_ephemeris_source_axis_hz(
    vis: str,
    field_id: int,
    times_s: np.ndarray,
    chan_freqs_geo_hz: np.ndarray,
    ephem_path: str | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    '''Build a common SOURCE axis from the GEO axis using the reference-time RadVel.'''
    geo = np.asarray(chan_freqs_geo_hz, dtype=np.float64).ravel()
    t = np.asarray(times_s, dtype=np.float64).ravel()
    if geo.size == 0:
        raise RuntimeError('Cannot build ephemeris SOURCE axis from an empty GEO axis')
    if t.size == 0:
        raise RuntimeError('Cannot build ephemeris SOURCE axis without row times')
    ephem_path, row_radvel_m_s = _interp_ephemeris_radvel_to_times(vis, field_id, t, ephem_path=ephem_path)
    tref_s = float(np.min(t))
    _, vref = _interp_ephemeris_radvel_to_times(vis, field_id, np.asarray([tref_s], dtype=np.float64), ephem_path=ephem_path)
    ref_freq_hz = float(np.median(geo))
    shift_ref_hz = float(_ephemeris_geo_to_source_shift_hz(ref_freq_hz, vref)[0])
    src = geo + shift_ref_hz
    diag = {
        'ephem_path': ephem_path,
        'reference_time_s': float(tref_s),
        'reference_radvel_m_s': float(vref[0]),
        'reference_shift_hz': shift_ref_hz,
        'reference_freq_hz': ref_freq_hz,
        'row_radvel_m_s_min': float(np.min(row_radvel_m_s)),
        'row_radvel_m_s_max': float(np.max(row_radvel_m_s)),
    }
    return src, diag


def _apply_ephemeris_geo_to_source_correction(
    preloaded: dict[str, np.ndarray],
    vis: str,
    field_id: int,
    spw_id: int,
    chan_freqs_geo_hz: np.ndarray,
    chan_freqs_source_hz: np.ndarray,
    log_dir: str | None = None,
    ephem_path: str | None = None,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    '''Resample GEO-frame visibilities onto a common SOURCE grid using per-time RadVel.'''
    out = dict(preloaded)
    v_in = np.asarray(preloaded['V'], dtype=np.complex64)
    times = np.asarray(preloaded['TIME'], dtype=np.float64).ravel()
    geo = np.asarray(chan_freqs_geo_hz, dtype=np.float64).ravel()
    src = np.asarray(chan_freqs_source_hz, dtype=np.float64).ravel()
    if v_in.ndim != 2:
        raise RuntimeError('Expected preloaded V to be 2D [row, chan] for ephemeris correction')
    if v_in.shape[1] != geo.size or src.size != geo.size:
        raise RuntimeError('Ephemeris spectral axis size mismatch')
    ephem_path, row_radvel_m_s = _interp_ephemeris_radvel_to_times(vis, field_id, times, ephem_path=ephem_path)
    u_times, inv = np.unique(times, return_inverse=True)
    _, idx_first = np.unique(inv, return_index=True)
    group_radvel_m_s = row_radvel_m_s[idx_first]
    ref_freq_hz = float(np.median(geo))
    x_old = geo[::-1] if geo[0] > geo[-1] else geo
    reverse = bool(geo[0] > geo[-1])
    v_out = np.zeros_like(v_in, dtype=np.complex64)
    invalid = np.zeros((src.size,), dtype=bool)
    shifts_hz = _ephemeris_geo_to_source_shift_hz(ref_freq_hz, group_radvel_m_s)
    for group_idx, shift_hz in enumerate(shifts_hz):
        rows = np.where(inv == group_idx)[0]
        geo_needed = src - shift_hz
        in_support = (geo_needed >= np.min(geo)) & (geo_needed <= np.max(geo))
        invalid |= ~in_support
        x_new = geo_needed[::-1] if reverse else geo_needed
        block = v_in[rows]
        for irow, row in enumerate(block):
            y_re = row.real[::-1] if reverse else row.real
            y_im = row.imag[::-1] if reverse else row.imag
            re_new = np.interp(x_new, x_old, y_re, left=0.0, right=0.0)
            im_new = np.interp(x_new, x_old, y_im, left=0.0, right=0.0)
            if reverse:
                re_new = re_new[::-1]
                im_new = im_new[::-1]
            v_out[rows[irow]] = (re_new + 1j * im_new).astype(np.complex64, copy=False)
    if np.any(invalid):
        v_out[:, invalid] = 0.0
    out['V'] = v_out
    diag = {
        'ephem_path': ephem_path,
        'radvel_m_s_min': float(np.min(row_radvel_m_s)),
        'radvel_m_s_max': float(np.max(row_radvel_m_s)),
        'radvel_group_count': int(u_times.size),
        'shift_hz_min': float(np.min(shifts_hz)),
        'shift_hz_max': float(np.max(shifts_hz)),
        'reference_freq_hz': ref_freq_hz,
        'invalid_source_chan_count': int(np.count_nonzero(invalid)),
        'source_axis_size': int(src.size),
    }
    _profile_logf(
        log_dir,
        'ephem_geo_to_source field=%s spw_id=%s rows=%s times=%s rv_min=%.3f rv_max=%.3f invalid_chans=%s',
        field_id,
        spw_id,
        int(v_in.shape[0]),
        int(u_times.size),
        float(np.min(row_radvel_m_s)),
        float(np.max(row_radvel_m_s)),
        int(np.count_nonzero(invalid)),
    )
    return out, diag


def estimate_pb_fwhm_arcsec(ref_freq_hz: float, dish_diameter_m: float) -> float:
    '''Estimate primary-beam FWHM in arcseconds.'''
    wavelength_m = casa_tools.quanta.getvalue(
        casa_tools.quanta.convert(casa_tools.quanta.constants('c'), 'm/s')
    )[0] / ref_freq_hz
    theta_rad = 1.13 * wavelength_m / dish_diameter_m
    return theta_rad * 206265.0


def _wrap_pm_pi(angle_rad: np.ndarray | float) -> np.ndarray | float:
    '''Wrap angles into [-pi, pi).'''
    return (np.asarray(angle_rad) + np.pi) % (2.0 * np.pi) - np.pi


def _reference_center_rad(
    phase_centers_rad: dict[int, tuple[float, float]],
    field_ids: list[int],
) -> tuple[float, float]:
    '''Return a stable spherical-mean reference center for tangent-plane offsets.'''
    xyz = []
    for fid in field_ids:
        ra, dec = phase_centers_rad[int(fid)]
        cosd = np.cos(dec)
        xyz.append([cosd * np.cos(ra), cosd * np.sin(ra), np.sin(dec)])
    vec = np.mean(np.asarray(xyz, dtype=np.float64), axis=0)
    norm = np.linalg.norm(vec)
    if not np.isfinite(norm) or norm <= 0.0:
        ra, dec = phase_centers_rad[int(field_ids[0])]
        return float(ra), float(dec)
    vec /= norm
    ra0 = float(np.arctan2(vec[1], vec[0]))
    dec0 = float(np.arctan2(vec[2], np.hypot(vec[0], vec[1])))
    return ra0, dec0


def _field_offsets_arcsec_from_center(
    phase_centers_rad: dict[int, tuple[float, float]],
    field_ids: list[int],
    center_rad: tuple[float, float],
) -> dict[int, tuple[float, float]]:
    '''Return tangent-plane offsets in arcsec from a common center.'''
    ra0, dec0 = center_rad
    cos_dec0 = np.cos(dec0)
    out = {}
    for fid in field_ids:
        ra, dec = phase_centers_rad[int(fid)]
        dl = float(_wrap_pm_pi(ra - ra0) * cos_dec0) * 206265.0
        dm = float(dec - dec0) * 206265.0
        out[int(fid)] = (dl, dm)
    return out


def _mosaic_bbox_center_rad(
    phase_centers_rad: dict[int, tuple[float, float]],
    field_ids: list[int],
) -> tuple[float, float]:
    '''Return the midpoint of the field bounding box in tangent-plane coordinates.'''
    ref_center = _reference_center_rad(phase_centers_rad, field_ids)
    offsets = _field_offsets_arcsec_from_center(phase_centers_rad, field_ids, ref_center)
    dl = np.asarray([offsets[int(fid)][0] for fid in field_ids], dtype=np.float64)
    dm = np.asarray([offsets[int(fid)][1] for fid in field_ids], dtype=np.float64)
    dl_mid = 0.5 * (np.min(dl) + np.max(dl))
    dm_mid = 0.5 * (np.min(dm) + np.max(dm))
    ra0, dec0 = ref_center
    ra_c = float(ra0 + (dl_mid / 206265.0) / max(np.cos(dec0), 1e-12))
    dec_c = float(dec0 + (dm_mid / 206265.0))
    return ra_c, dec_c


def _pb_cutoff_radius_arcsec(pb_fwhm_arcsec: float, pb_cutoff: float) -> float:
    '''Return the radius where a Gaussian PB falls to pb_cutoff.'''
    cutoff = float(min(max(pb_cutoff, 1e-6), 0.999999))
    sigma_arcsec = float(pb_fwhm_arcsec) / np.sqrt(8.0 * np.log(2.0))
    return float(sigma_arcsec * np.sqrt(-2.0 * np.log(cutoff)))


def _next_casa_friendly_size(n: int) -> int:
    '''Round up to the next CASA-friendly image size with 2/3/5 prime factors only.'''
    n = max(int(n), 1)

    def _is_smooth(k: int) -> bool:
        for p in (2, 3, 5):
            while k % p == 0:
                k //= p
        return k == 1

    k = n
    while not _is_smooth(k):
        k += 1
    return int(k)


def _estimate_field_cell_arcsec(
    ref_freq_hz: float,
    dish_diameter_m: float,
    npix: int,
    fov_pb_mult: float,
) -> float:
    '''Estimate the image cell size implied by the current field-imaging heuristic.'''
    pb_fwhm_arcsec = estimate_pb_fwhm_arcsec(ref_freq_hz, dish_diameter_m)
    fov_arcsec = float(pb_fwhm_arcsec) * float(fov_pb_mult)
    return float(fov_arcsec / max(int(npix), 1))


def _source_common_geometry_plan(
    source_id: int,
    field_ids: list[int],
    science_rows: list[dict[str, Any]],
    phase_centers_rad: dict[int, tuple[float, float]],
    dish_diameter_m: float,
    npix: int,
    fov_pb_mult: float,
    pb_cutoff: float = 0.1,
) -> dict[str, Any]:
    '''Plan one common spatial geometry for a source across all science SPWs.'''
    field_ids_sorted = [int(fid) for fid in sorted(field_ids)]
    if not field_ids_sorted:
        raise RuntimeError(f'Cannot plan geometry for source {source_id} with no fields')
    if not science_rows:
        raise RuntimeError(f'Cannot plan geometry for source {source_id} with no science SPWs')

    per_spw = []
    for row in science_rows:
        ref_freq_hz = float(row['ref_freq_hz'])
        cell_arcsec = _estimate_field_cell_arcsec(ref_freq_hz, dish_diameter_m, npix=npix, fov_pb_mult=fov_pb_mult)
        pb_fwhm_arcsec = estimate_pb_fwhm_arcsec(ref_freq_hz, dish_diameter_m)
        per_spw.append({
            'ddid': int(row['ddid']),
            'spw_id': int(row['spw_id']),
            'ref_freq_hz': ref_freq_hz,
            'cell_arcsec': float(cell_arcsec),
            'pb_fwhm_arcsec': float(pb_fwhm_arcsec),
        })

    common_cell_arcsec = float(min(v['cell_arcsec'] for v in per_spw))
    field_npix_req = max(
        int(np.ceil((float(npix) * float(v['cell_arcsec'])) / common_cell_arcsec))
        for v in per_spw
    )
    field_npix = _next_casa_friendly_size(field_npix_req)

    mosaic_center = _mosaic_bbox_center_rad(phase_centers_rad, field_ids_sorted)
    offsets_arcsec = _field_offsets_arcsec_from_center(phase_centers_rad, field_ids_sorted, mosaic_center)
    field_half_arcsec = 0.5 * (field_npix - 1) * common_cell_arcsec
    mosaic_nx_req = field_npix
    mosaic_ny_req = field_npix
    for v in per_spw:
        cutoff_radius_arcsec = _pb_cutoff_radius_arcsec(v['pb_fwhm_arcsec'], pb_cutoff)
        contrib_half_arcsec = min(field_half_arcsec, cutoff_radius_arcsec)
        max_abs_dx = max(abs(offsets_arcsec[fid][0]) for fid in field_ids_sorted)
        max_abs_dy = max(abs(offsets_arcsec[fid][1]) for fid in field_ids_sorted)
        cand_nx = int(np.ceil((2.0 * (max_abs_dx + contrib_half_arcsec)) / common_cell_arcsec)) + 5
        cand_ny = int(np.ceil((2.0 * (max_abs_dy + contrib_half_arcsec)) / common_cell_arcsec)) + 5
        mosaic_nx_req = max(mosaic_nx_req, cand_nx)
        mosaic_ny_req = max(mosaic_ny_req, cand_ny)

    return {
        'source_id': int(source_id),
        'field_ids': field_ids_sorted,
        'cell_arcsec': float(common_cell_arcsec),
        'field_npix': int(field_npix),
        'mosaic_shape': (
            int(_next_casa_friendly_size(mosaic_ny_req)),
            int(_next_casa_friendly_size(mosaic_nx_req)),
        ),
        'mosaic_center_ra_rad': float(mosaic_center[0]),
        'mosaic_center_dec_rad': float(mosaic_center[1]),
        'field_offsets_arcsec': {int(fid): (float(offsets_arcsec[fid][0]), float(offsets_arcsec[fid][1])) for fid in field_ids_sorted},
        'spw_ids': [int(v['spw_id']) for v in per_spw],
        'ddids': [int(v['ddid']) for v in per_spw],
    }


def _build_pb_images(
    shape: tuple[int, int],
    cell_arcsec: float,
    pb_fwhm_arcsec: float,
    pb_cutoff: float = 0.1,
) -> tuple[np.ndarray, np.ndarray]:
    '''Build PB and PB^2 images with a hard cutoff for stitching.'''
    ny, nx = int(shape[0]), int(shape[1])
    key = (ny, nx, float(cell_arcsec), float(pb_fwhm_arcsec), float(pb_cutoff))
    cached = _PB_IMAGE_CACHE.get(key)
    if cached is not None:
        return cached
    cy = 0.5 * (ny - 1)
    cx = 0.5 * (nx - 1)
    yy, xx = np.indices((ny, nx), dtype=np.float64)
    # Astro convention: RA/east increases to the left, Dec/north increases upward.
    dx_arcsec = -(xx - cx) * float(cell_arcsec)
    dy_arcsec = -(yy - cy) * float(cell_arcsec)
    r2 = dx_arcsec * dx_arcsec + dy_arcsec * dy_arcsec
    sigma_arcsec = float(pb_fwhm_arcsec) / np.sqrt(8.0 * np.log(2.0))
    pb = np.exp(-0.5 * r2 / max(sigma_arcsec * sigma_arcsec, 1e-30))
    pb[pb <= float(pb_cutoff)] = 0.0
    pb = pb.astype(np.float32, copy=False)
    out = (pb, (pb * pb).astype(np.float32, copy=False))
    _PB_IMAGE_CACHE[key] = out
    return out


def _prepare_shift_add_geometry(
    src_shape: tuple[int, int],
    dst_shape: tuple[int, int],
    dx_pix: float,
    dy_pix: float,
) -> list[tuple[slice, slice, slice, slice, float]]:
    '''Precompute bilinear shift-add slice geometry for one source/destination pair.'''
    src_ny, src_nx = int(src_shape[0]), int(src_shape[1])
    dst_ny, dst_nx = int(dst_shape[0]), int(dst_shape[1])
    src_cx = 0.5 * (src_nx - 1)
    src_cy = 0.5 * (src_ny - 1)
    dst_cx = 0.5 * (dst_nx - 1)
    dst_cy = 0.5 * (dst_ny - 1)

    ix = int(np.floor(dx_pix))
    iy = int(np.floor(dy_pix))
    fx = float(dx_pix - ix)
    fy = float(dy_pix - iy)
    terms: list[tuple[slice, slice, slice, slice, float]] = []
    for oy, wy in ((0, 1.0 - fy), (1, fy)):
        if wy <= 0.0:
            continue
        shift_y = int(round(dst_cy - src_cy)) + iy + oy
        dst_y0 = max(0, shift_y)
        dst_y1 = min(dst_ny, shift_y + src_ny)
        if dst_y1 <= dst_y0:
            continue
        src_y0 = max(0, -shift_y)
        src_y1 = src_y0 + (dst_y1 - dst_y0)
        for ox, wx in ((0, 1.0 - fx), (1, fx)):
            if wx <= 0.0:
                continue
            shift_x = int(round(dst_cx - src_cx)) + ix + ox
            dst_x0 = max(0, shift_x)
            dst_x1 = min(dst_nx, shift_x + src_nx)
            if dst_x1 <= dst_x0:
                continue
            src_x0 = max(0, -shift_x)
            src_x1 = src_x0 + (dst_x1 - dst_x0)
            terms.append((
                slice(dst_y0, dst_y1),
                slice(dst_x0, dst_x1),
                slice(src_y0, src_y1),
                slice(src_x0, src_x1),
                float(wx * wy),
            ))
    return terms


def _accumulate_shifted_plane(
    dst_num: np.ndarray,
    dst_den: np.ndarray,
    src: np.ndarray,
    num_weights: np.ndarray,
    den_weights: np.ndarray,
    dx_pix: float,
    dy_pix: float,
    shift_terms: list[tuple[Any, ...]] | None = None,
) -> tuple[float, float]:
    '''Shift-add a 2D or 3D image into a common grid using bilinear interpolation.'''
    src_arr = np.asarray(src, dtype=np.float32)
    w_num = np.asarray(num_weights, dtype=np.float32)
    w_den = np.asarray(den_weights, dtype=np.float32)
    if src_arr.ndim == 2:
        src_arr = src_arr[None, ...]
        squeeze = True
    else:
        squeeze = False

    _, src_ny, src_nx = src_arr.shape
    if shift_terms is None:
        shift_terms = _prepare_shift_add_geometry((src_ny, src_nx), dst_den.shape, dx_pix=dx_pix, dy_pix=dy_pix)
    num_added = 0.0
    den_added = 0.0

    for term in shift_terms:
        if len(term) == 6:
            dst_y, dst_x, src_y, src_x, num_slice, den_slice = term
        else:
            dst_y, dst_x, src_y, src_x, coeff = term
            num_slice = coeff * w_num[src_y, src_x]
            den_slice = coeff * w_den[src_y, src_x]
        if not np.any(den_slice > 0.0):
            continue
        dst_den[dst_y, dst_x] += den_slice
        dst_num[:, dst_y, dst_x] += (src_arr[:, src_y, src_x] * num_slice[None, :, :])
        num_added += float(np.sum(num_slice, dtype=np.float64))
        den_added += float(np.sum(den_slice, dtype=np.float64))

    if squeeze:
        dst_num[:] = dst_num[0]
    return num_added, den_added


def _init_mosaic_stitch_state(
    field_ids: list[int],
    field_phase_centers_rad: dict[int, tuple[float, float]],
    cube_shape: tuple[int, int, int],
    cell_arcsec: float,
    pb_fwhm_arcsec: float,
    pb_cutoff: float = 0.1,
    forced_shape: tuple[int, int] | None = None,
    forced_center_rad: tuple[float, float] | None = None,
) -> dict[str, Any]:
    '''Initialize in-memory stitch accumulators and geometry for one source/SPW.'''
    nchan, field_ny, field_nx = map(int, cube_shape)
    field_ids_sorted = sorted(int(fid) for fid in field_ids)
    mosaic_center = forced_center_rad if forced_center_rad is not None else _mosaic_bbox_center_rad(field_phase_centers_rad, field_ids_sorted)
    offsets_arcsec = _field_offsets_arcsec_from_center(field_phase_centers_rad, field_ids_sorted, mosaic_center)
    cutoff_radius_arcsec = _pb_cutoff_radius_arcsec(pb_fwhm_arcsec, pb_cutoff)
    half_width_x_arcsec = 0.5 * (field_nx - 1) * float(cell_arcsec)
    half_width_y_arcsec = 0.5 * (field_ny - 1) * float(cell_arcsec)
    contrib_half_x_arcsec = min(half_width_x_arcsec, cutoff_radius_arcsec)
    contrib_half_y_arcsec = min(half_width_y_arcsec, cutoff_radius_arcsec)
    max_abs_dx = max(abs(offsets_arcsec[fid][0]) for fid in field_ids_sorted)
    max_abs_dy = max(abs(offsets_arcsec[fid][1]) for fid in field_ids_sorted)
    if forced_shape is not None:
        mosaic_ny, mosaic_nx = int(forced_shape[0]), int(forced_shape[1])
    else:
        mosaic_nx = int(np.ceil((2.0 * (max_abs_dx + contrib_half_x_arcsec)) / float(cell_arcsec))) + 5
        mosaic_ny = int(np.ceil((2.0 * (max_abs_dy + contrib_half_y_arcsec)) / float(cell_arcsec))) + 5
        mosaic_nx = max(mosaic_nx, field_nx)
        mosaic_ny = max(mosaic_ny, field_ny)

    pb_img, pb2_img = _build_pb_images((field_ny, field_nx), cell_arcsec, pb_fwhm_arcsec, pb_cutoff=pb_cutoff)
    dst_shape = (mosaic_ny, mosaic_nx)
    shift_terms_by_field = {}
    for fid in field_ids_sorted:
        dx_pix = float(offsets_arcsec[fid][0] / float(cell_arcsec))
        dy_pix = float(offsets_arcsec[fid][1] / float(cell_arcsec))
        raw_terms = _prepare_shift_add_geometry((field_ny, field_nx), dst_shape, dx_pix, dy_pix)
        weighted_terms = []
        for dst_y, dst_x, src_y, src_x, coeff in raw_terms:
            num_slice = (coeff * pb_img[src_y, src_x]).astype(np.float32, copy=False)
            den_slice = (coeff * pb2_img[src_y, src_x]).astype(np.float32, copy=False)
            weighted_terms.append((dst_y, dst_x, src_y, src_x, num_slice, den_slice))
        shift_terms_by_field[int(fid)] = weighted_terms
    return {
        'num': np.zeros((nchan, mosaic_ny, mosaic_nx), dtype=np.float32),
        'den': np.zeros((mosaic_ny, mosaic_nx), dtype=np.float32),
        'pb_img': pb_img,
        'pb2_img': pb2_img,
        'shape': (int(mosaic_ny), int(mosaic_nx)),
        'cell_arcsec': float(cell_arcsec),
        'pb_fwhm_arcsec': float(pb_fwhm_arcsec),
        'pb_cutoff': float(pb_cutoff),
        'mosaic_center_ra_rad': float(mosaic_center[0]),
        'mosaic_center_dec_rad': float(mosaic_center[1]),
        'field_offsets_arcsec': {int(fid): (float(offsets_arcsec[fid][0]), float(offsets_arcsec[fid][1])) for fid in field_ids_sorted},
        'field_num_weight_sum': {},
        'field_den_weight_sum': {},
        'shift_terms_by_field': shift_terms_by_field,
    }


def _accumulate_field_cube_to_stitch(
    stitch_state: dict[str, Any],
    field_id: int,
    cube: np.ndarray,
) -> None:
    '''Accumulate one field cube into an in-memory stitch state.'''
    num_sum, den_sum = _accumulate_shifted_plane(
        stitch_state['num'],
        stitch_state['den'],
        cube,
        stitch_state['pb_img'],
        stitch_state['pb2_img'],
        dx_pix=0.0,
        dy_pix=0.0,
        shift_terms=stitch_state['shift_terms_by_field'][int(field_id)],
    )
    stitch_state['field_num_weight_sum'][int(field_id)] = float(num_sum)
    stitch_state['field_den_weight_sum'][int(field_id)] = float(den_sum)


def _finalize_mosaic_stitch_state(stitch_state: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    '''Finalize one in-memory stitch state into a mosaic cube and metadata.'''
    num = np.asarray(stitch_state['num'], dtype=np.float32)
    den = np.asarray(stitch_state['den'], dtype=np.float32)
    mosaic_cube = np.zeros_like(num, dtype=np.float32)
    good = den > 0.0
    if np.any(good):
        mosaic_cube[:, good] = num[:, good] / np.sqrt(den[good])
    meta = {
        'shape': tuple(int(v) for v in stitch_state['shape']),
        'cell_arcsec': float(stitch_state['cell_arcsec']),
        'pb_fwhm_arcsec': float(stitch_state['pb_fwhm_arcsec']),
        'pb_cutoff': float(stitch_state['pb_cutoff']),
        'mosaic_center_ra_rad': float(stitch_state['mosaic_center_ra_rad']),
        'mosaic_center_dec_rad': float(stitch_state['mosaic_center_dec_rad']),
        'field_offsets_arcsec': copy.deepcopy(stitch_state['field_offsets_arcsec']),
        'field_num_weight_sum': copy.deepcopy(stitch_state['field_num_weight_sum']),
        'field_den_weight_sum': copy.deepcopy(stitch_state['field_den_weight_sum']),
        'weight_sum': den.astype(np.float32, copy=False),
    }
    return mosaic_cube, meta


def _stitch_field_cubes_to_mosaic(
    field_cube_paths: dict[int, str],
    field_phase_centers_rad: dict[int, tuple[float, float]],
    cell_arcsec: float,
    pb_fwhm_arcsec: float,
    pb_cutoff: float = 0.1,
) -> tuple[np.ndarray, dict[str, Any]]:
    '''Stitch per-field cubes into a detection-optimized mosaic statistic.'''
    field_ids = sorted(int(fid) for fid in field_cube_paths.keys())
    if not field_ids:
        raise RuntimeError('No field cubes available for mosaic stitching.')

    first_cube = np.load(field_cube_paths[field_ids[0]], mmap_mode='r')
    if first_cube.ndim != 3:
        raise RuntimeError('Expected per-field cube with shape (nchan, ny, nx).')
    cube_shape = tuple(int(v) for v in first_cube.shape)
    del first_cube
    stitch_state = _init_mosaic_stitch_state(
        field_ids,
        field_phase_centers_rad,
        cube_shape=cube_shape,
        cell_arcsec=cell_arcsec,
        pb_fwhm_arcsec=pb_fwhm_arcsec,
        pb_cutoff=pb_cutoff,
    )

    for fid in field_ids:
        cube = np.load(field_cube_paths[fid], mmap_mode='r')
        _accumulate_field_cube_to_stitch(stitch_state, fid, cube)
    return _finalize_mosaic_stitch_state(stitch_state)


def _precompute_grid_indices(
    u_m: np.ndarray,
    v_m: np.ndarray,
    lam: float,
    wrow: np.ndarray,
    npix: int = 256,
    fov_pb_mult: float = 1.0,
    pb_fwhm_arcsec: float = 20.0,
    uv_taper_auto: bool = False,
    uv_taper_sigma_uv: float | None = None,
    uv_taper_fwhm_cell: float = 2.0,
    cell_arcsec_override: float | None = None,
) -> GridPrecompute:
    '''Precompute grid indices and weights for nearest-neighbor gridding.'''
    # Record gridding precompute timing when profiling is enabled.
    t_profile_total = time.perf_counter()
    if cell_arcsec_override is None:
        fov_rad = (pb_fwhm_arcsec * fov_pb_mult) / 206265.0
    else:
        fov_rad = (float(cell_arcsec_override) / 206265.0) * max(int(npix), 1)
    du = 1.0 / max(fov_rad, 1e-12)
    u = u_m / lam
    v = v_m / lam
    center = npix // 2
    cell_rad = fov_rad / max(npix, 1)

    sigma_uv = uv_taper_sigma_uv
    if sigma_uv is None and uv_taper_auto:
        theta_fwhm = max(float(uv_taper_fwhm_cell), 1.0e-6) * cell_rad
        sigma_uv = float(np.sqrt(2.0 * np.log(2.0)) / (np.pi * theta_fwhm))
    taper = None
    if sigma_uv is not None and np.isfinite(sigma_uv) and sigma_uv > 0.0:
        r2 = u * u + v * v
        taper = np.exp(-0.5 * r2 / (float(sigma_uv) ** 2))

    ui = np.rint(u / du).astype(np.int64) + center
    vi = np.rint(v / du).astype(np.int64) + center
    inb = (ui >= 0) & (ui < npix) & (vi >= 0) & (vi < npix) & (wrow != 0.0)
    idx = (vi[inb] * npix + ui[inb]).astype(np.int64)
    if taper is None:
        w = wrow[inb].astype(np.float64, copy=False)
    else:
        w = (wrow[inb] * taper[inb]).astype(np.float64, copy=False)

    ui2 = np.rint((-u) / du).astype(np.int64) + center
    vi2 = np.rint((-v) / du).astype(np.int64) + center
    inb2 = (ui2 >= 0) & (ui2 < npix) & (vi2 >= 0) & (vi2 < npix) & (wrow != 0.0)
    idx2 = (vi2[inb2] * npix + ui2[inb2]).astype(np.int64)
    if taper is None:
        w2 = wrow[inb2].astype(np.float64, copy=False)
    else:
        w2 = (wrow[inb2] * taper[inb2]).astype(np.float64, copy=False)

    diag = {
        'fov_rad': float(fov_rad),
        'cell_rad': float(fov_rad / max(npix, 1)),
        'cell_arcsec': float((fov_rad / max(npix, 1)) * 206265.0),
        'npix': int(npix),
        'nrow': int(wrow.size),
        'nrow_nonzero_w': int(np.count_nonzero(wrow)),
        'nrow_inbounds': int(np.count_nonzero(inb)),
        'nrow_dropped': int(np.count_nonzero(wrow) - np.count_nonzero(inb)),
        'drop_frac': float(
            0.0
            if np.count_nonzero(wrow) == 0
            else (np.count_nonzero(wrow) - np.count_nonzero(inb)) / np.count_nonzero(wrow)
        ),
        'grid_weight_sum': float(np.sum(w, dtype=np.float64)),
        'grid_weight_sum_conj': float(np.sum(w2, dtype=np.float64)),
        'uv_taper_applied': bool(taper is not None),
        'uv_taper_auto': bool(uv_taper_auto),
        'uv_taper_sigma_uv': float(sigma_uv) if sigma_uv is not None else 0.0,
        'uv_taper_fwhm_cell': float(uv_taper_fwhm_cell),
    }

    diag['profile_dt_total'] = float(time.perf_counter() - t_profile_total)
    return idx, w, inb, idx2, w2, inb2, diag


def _image_from_vis_precomputed(
    vrow: np.ndarray,
    npix: int,
    idx: np.ndarray,
    w: np.ndarray,
    inb: np.ndarray,
    idx2: np.ndarray,
    w2: np.ndarray,
    inb2: np.ndarray,
    return_timing: bool = False,
) -> tuple[np.ndarray, float, float] | np.ndarray:
    '''Grid visibilities and return an astro-convention image with optional timing.'''
    grid = np.zeros((npix * npix,), dtype=np.complex128)
    t0 = time.perf_counter()
    np.add.at(grid, idx, w * vrow[inb])
    np.add.at(grid, idx2, w2 * np.conj(vrow[inb2]))
    t_grid = time.perf_counter() - t0
    t1 = time.perf_counter()
    img = np.fft.fftshift(np.fft.ifft2(np.fft.ifftshift(grid.reshape((npix, npix)))))
    # Convert from internal FFT array ordering to astro display convention:
    # RA increases to the left, Dec increases upward.
    img = np.flip(np.flip(img, axis=0), axis=1)
    t_fft = time.perf_counter() - t1
    if return_timing:
        return np.real(img), t_grid, t_fft
    return np.real(img)


def _compute_cube_products(
    cube: np.ndarray,
    ref_sigma: float = 3.0,
    mom0_thresh_sigma: float = 5.0,
    gate_sigma: float = 1.0,
    ref_zero_frac_thr: float = 0.05,
    mom0_zero_frac_thr: float = 0.05,
    ref_smooth_width: int = 4,
    mom0_smooth_width: int = 4,
    neg_extent_delta_thr: float = 5.0,
    neg_extent_trim_frac: float = 0.10,
    snr_dilate_width: int = 5,
    spatial_mask: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    '''Compute cube products and derived spectra/evidence.'''
    # Record cube-product timings when profiling is enabled.
    t_profile_total = time.perf_counter()
    nchan = int(cube.shape[0])
    sigmas = np.zeros((nchan,), dtype=np.float64)
    mask2d = None if spatial_mask is None else np.asarray(spatial_mask, dtype=bool)
    if mask2d is not None and (mask2d.shape != cube.shape[1:] or not np.any(mask2d)):
        mask2d = None
    cube_use = cube.reshape(nchan, -1) if mask2d is None else cube[:, mask2d]
    t_sigma = time.perf_counter()
    for ch in range(nchan):
        sig = _robust_sigma(cube_use[ch])
        sigmas[ch] = sig if np.isfinite(sig) and sig > 0 else 0.0
    dt_sigma = time.perf_counter() - t_sigma

    t_ref = time.perf_counter()
    spectrum_raw = _compute_reference_spectrum(cube, sigmas, ref_sigma=ref_sigma, spatial_mask=mask2d)
    dt_ref = time.perf_counter() - t_ref
    t_mom0 = time.perf_counter()
    moment0 = _compute_moment0(cube, sigmas, mom0_thresh_sigma=mom0_thresh_sigma, spatial_mask=mask2d)
    dt_mom0 = time.perf_counter() - t_mom0
    t_mw = time.perf_counter()
    moment0_weighted_raw = _compute_mom0_weighted_spectrum(
        cube,
        sigmas,
        moment0,
        gate_sigma=gate_sigma,
        spatial_mask=mask2d,
    )
    dt_mw = time.perf_counter() - t_mw
    used_full_mask_fallback = False
    fallback_mask = None
    if (not np.any(np.abs(spectrum_raw) > 0.0)) and (not np.any(np.abs(moment0_weighted_raw) > 0.0)):
        if mask2d is not None and np.any(mask2d):
            fallback_mask = mask2d
        else:
            fallback_mask = np.ones(cube.shape[1:], dtype=bool)
    if fallback_mask is not None:
        # If the normal sigma-gated extraction finds nothing at all, fall back
        # to summing all valid pixels. For mosaics this uses the valid coverage
        # mask; for single-field images it uses the full image.
        used_full_mask_fallback = True
        vals = cube[:, fallback_mask]
        spectrum_raw = np.sum(vals, axis=1, dtype=np.float64)
        moment0 = np.zeros(cube.shape[1:], dtype=np.float32)
        moment0[fallback_mask] = np.sum(vals, axis=0, dtype=np.float64).astype(np.float32, copy=False)
        w = np.abs(moment0).astype(np.float32, copy=False)
        moment0_weighted_raw = np.zeros(nchan, dtype=np.float64)
        if np.any(w[fallback_mask] > 0.0):
            w1 = w[fallback_mask].astype(np.float64, copy=False)
            moment0_weighted_raw = np.sum(vals * w1[None, :], axis=1, dtype=np.float64)
    t_snr = time.perf_counter()
    spec_out = _raw_spectra_to_snr_evidence(
        spectrum_raw,
        moment0_weighted_raw,
        ref_zero_frac_thr=ref_zero_frac_thr,
        mom0_zero_frac_thr=mom0_zero_frac_thr,
        ref_smooth_width=ref_smooth_width,
        mom0_smooth_width=mom0_smooth_width,
        neg_extent_delta_thr=neg_extent_delta_thr,
        neg_extent_trim_frac=neg_extent_trim_frac,
        snr_dilate_width=snr_dilate_width,
    )
    dt_snr = time.perf_counter() - t_snr
    _profile_logf(None, 'compute_cube_products nchan=%s npix=%sx%s sigma=%.3f ref=%.3f mom0=%.3f mom0w=%.3f snr=%.3f total=%.3f', nchan, cube.shape[2], cube.shape[1], dt_sigma, dt_ref, dt_mom0, dt_mw, dt_snr, (time.perf_counter() - t_profile_total))
    return {
        'sigma': sigmas.astype(np.float32, copy=False),
        'reference_sum_raw': spectrum_raw.astype(np.float32, copy=False),
        'moment0': moment0.astype(np.float32, copy=False),
        'moment0_weighted_sum_raw': moment0_weighted_raw.astype(np.float32, copy=False),
        'reference_sum_raw_processed': spec_out['reference_sum_raw_processed'].astype(np.float32, copy=False),
        'moment0_weighted_sum_raw_processed': spec_out['moment0_weighted_sum_raw_processed'].astype(np.float32, copy=False),
        'reference_sum_snr': spec_out['reference_sum_snr'].astype(np.float32, copy=False),
        'moment0_weighted_sum_snr': spec_out['moment0_weighted_sum_snr'].astype(np.float32, copy=False),
        'evidence': spec_out['evidence'].astype(np.float32, copy=False),
        'spectra_qc': {
            **spec_out['diagnostics'],
            'used_full_mask_fallback': bool(used_full_mask_fallback),
        },
        'reference_sum_noise_mask': spec_out['reference_noise_mask'],
        'moment0_weighted_sum_noise_mask': spec_out['moment0_noise_mask'],
    }


def _raw_spectra_to_snr_evidence(
    reference_sum_raw: np.ndarray,
    moment0_weighted_sum_raw: np.ndarray,
    ref_zero_frac_thr: float = 0.05,
    mom0_zero_frac_thr: float = 0.05,
    ref_smooth_width: int = 4,
    mom0_smooth_width: int = 4,
    neg_extent_delta_thr: float = 5.0,
    neg_extent_trim_frac: float = 0.10,
    snr_dilate_width: int = 5,
) -> dict[str, Any]:
    '''Convert raw spectra into conditioned SNR spectra and preliminary evidence.'''
    spec_raw = np.asarray(reference_sum_raw, dtype=np.float64)
    mw_raw = np.asarray(moment0_weighted_sum_raw, dtype=np.float64)
    nchan = min(spec_raw.size, mw_raw.size)
    if nchan <= 0:
        return {
            'reference_sum_raw_processed': np.asarray([], dtype=np.float64),
            'moment0_weighted_sum_raw_processed': np.asarray([], dtype=np.float64),
            'reference_sum_snr': np.asarray([], dtype=np.float64),
            'moment0_weighted_sum_snr': np.asarray([], dtype=np.float64),
            'evidence': np.asarray([], dtype=np.float64),
            'reference_noise_mask': np.asarray([], dtype=bool),
            'moment0_noise_mask': np.asarray([], dtype=bool),
            'diagnostics': {
                'reference_zero_fraction': 1.0,
                'moment0_zero_fraction': 1.0,
                'reference_smoothed': False,
                'moment0_smoothed': False,
                'moment0_rejected_zero_fraction': True,
                'moment0_rejected_negative_extent': False,
                'moment0_rejected_final': True,
                'negative_extent_delta_sigma': 0.0,
                'reference_noise_median_rms': np.nan,
                'moment0_noise_median_rms': np.nan,
                'reference_noise_rms_target': np.nan,
                'moment0_noise_rms_target': np.nan,
                'renorm_ratio_reference': 1.0,
                'renorm_ratio_moment0': 1.0,
            },
        }
    spec_raw = spec_raw[:nchan]
    mw_raw = mw_raw[:nchan]

    ref_zf = _zero_fraction_excluding_edge_runs(spec_raw)
    mw_zf = _zero_fraction_excluding_edge_runs(mw_raw)

    ref_smoothed = bool(ref_zf > float(ref_zero_frac_thr))
    mw_reject_zero = bool(mw_zf > float(mom0_zero_frac_thr))
    mw_smoothed = bool((not mw_reject_zero) and (mw_zf > 0.0))

    ref_proc = _smooth_tophat(spec_raw, width=ref_smooth_width) if ref_smoothed else np.asarray(spec_raw, dtype=np.float64)
    mw_proc = _smooth_tophat(mw_raw, width=mom0_smooth_width) if mw_smoothed else np.asarray(mw_raw, dtype=np.float64)

    spec_snr, ref_mask = _snr_from_spectrum(ref_proc, dilate_width=snr_dilate_width, return_mask=True)
    mw_snr, mw_mask = _snr_from_spectrum(mw_proc, dilate_width=snr_dilate_width, return_mask=True)
    if ref_mask is None:
        ref_mask = np.isfinite(spec_snr)
    if mw_mask is None:
        mw_mask = np.isfinite(mw_snr)

    neg_delta = _negative_extent_delta_trimmed(spec_snr, mw_snr, trim_frac=neg_extent_trim_frac)
    mw_reject_neg = bool((not mw_reject_zero) and (neg_delta > float(neg_extent_delta_thr)))
    mw_reject_final = bool(mw_reject_zero or mw_reject_neg)

    if mw_reject_final:
        evid = np.asarray(spec_snr, dtype=np.float64)
    else:
        evid = np.nanmax(np.vstack([spec_snr, mw_snr]), axis=0)

    return {
        'reference_sum_raw_processed': np.asarray(ref_proc, dtype=np.float64),
        'moment0_weighted_sum_raw_processed': np.asarray(mw_proc, dtype=np.float64),
        'reference_sum_snr': np.asarray(spec_snr, dtype=np.float64),
        'moment0_weighted_sum_snr': np.asarray(mw_snr, dtype=np.float64),
        'evidence': np.asarray(evid, dtype=np.float64),
        'reference_noise_mask': np.asarray(ref_mask, dtype=bool),
        'moment0_noise_mask': np.asarray(mw_mask, dtype=bool),
        'diagnostics': {
            'reference_zero_fraction': float(ref_zf),
            'moment0_zero_fraction': float(mw_zf),
            'reference_smoothed': bool(ref_smoothed),
            'moment0_smoothed': bool(mw_smoothed),
            'moment0_rejected_zero_fraction': bool(mw_reject_zero),
            'moment0_rejected_negative_extent': bool(mw_reject_neg),
            'moment0_rejected_final': bool(mw_reject_final),
            'mom0_usage_mode': 'rejected_zero_fraction' if mw_reject_zero else (
                'rejected_negative_extent' if mw_reject_neg else 'used'
            ),
            'negative_extent_delta_sigma': float(neg_delta),
            'reference_noise_median_rms': np.nan,
            'moment0_noise_median_rms': np.nan,
            'reference_noise_rms_target': np.nan,
            'moment0_noise_rms_target': np.nan,
            'renorm_ratio_reference': 1.0,
            'renorm_ratio_moment0': 1.0,
        },
    }


def _trim_edge_zeros(arr: np.ndarray) -> np.ndarray:
    '''Trim only contiguous leading/trailing zero runs from a 1D array.'''
    x = np.asarray(arr, dtype=np.float64).ravel()
    n = x.size
    if n == 0:
        return x
    lo = 0
    while lo < n and x[lo] == 0.0:
        lo += 1
    hi = n - 1
    while hi >= lo and x[hi] == 0.0:
        hi -= 1
    if hi < lo:
        return np.asarray([], dtype=np.float64)
    return x[lo:hi + 1]


def _zero_fraction_excluding_edge_runs(arr: np.ndarray) -> float:
    '''Return zero fraction after excluding contiguous edge-zero runs.'''
    core = _trim_edge_zeros(arr)
    if core.size == 0:
        return 1.0
    finite = np.isfinite(core)
    if not np.any(finite):
        return 1.0
    return float(np.mean(core[finite] == 0.0))


def _smooth_tophat(arr: np.ndarray, width: int = 4) -> np.ndarray:
    '''Top-hat smooth a 1D array while preserving NaN positions.'''
    x = np.asarray(arr, dtype=np.float64)
    w = int(max(width, 1))
    if x.size < 2 or w <= 1:
        return x.copy()
    k = np.ones((w,), dtype=np.float64) / float(w)
    y = np.convolve(np.nan_to_num(x, nan=0.0), k, mode='same')
    y[~np.isfinite(x)] = np.nan
    return y


def _negative_extent_delta_trimmed(
    reference_snr: np.ndarray,
    moment0_snr: np.ndarray,
    trim_frac: float = 0.10,
) -> float:
    '''Measure how much deeper the moment0 SNR negative tail is vs reference SNR.'''
    ref = np.asarray(reference_snr, dtype=np.float64).ravel()
    mw = np.asarray(moment0_snr, dtype=np.float64).ravel()
    n = min(ref.size, mw.size)
    if n < 20:
        return 0.0
    trim = float(min(max(trim_frac, 0.0), 0.45))
    lo = int(np.floor(trim * n))
    hi = int(np.ceil((1.0 - trim) * n))
    if hi <= lo + 5:
        return 0.0
    ref_mid = ref[lo:hi]
    mw_mid = mw[lo:hi]
    good = np.isfinite(ref_mid) & np.isfinite(mw_mid)
    if np.count_nonzero(good) < 8:
        return 0.0
    return float(np.nanmin(ref_mid[good]) - np.nanmin(mw_mid[good]))


def _rolling_rms_median_excluding_ranges(
    snr: np.ndarray,
    exclude_ranges: list[tuple[int, int]],
    window: int = 10,
) -> float:
    '''Return the median rolling RMS, excluding ROI ranges from the median statistic.'''
    x = np.asarray(snr, dtype=np.float64).ravel()
    n = x.size
    if n == 0:
        return float('nan')
    w = int(max(window, 1))
    if w <= 1:
        rms = np.abs(x)
    else:
        k = np.ones((w,), dtype=np.float64) / float(w)
        mu = np.convolve(np.nan_to_num(x, nan=0.0), k, mode='same')
        mu2 = np.convolve(np.nan_to_num(x * x, nan=0.0), k, mode='same')
        var = np.maximum(mu2 - mu * mu, 0.0)
        rms = np.sqrt(var)
    keep = np.isfinite(rms)
    for lo, hi in exclude_ranges:
        a = max(0, min(int(lo), n - 1))
        b = max(0, min(int(hi), n - 1))
        if b < a:
            a, b = b, a
        keep[a:b + 1] = False
    if np.count_nonzero(keep) < 8:
        return float('nan')
    return float(np.nanmedian(rms[keep]))


def _rolling_rms_spectrum(snr: np.ndarray, window: int = 10) -> np.ndarray:
    '''Return per-channel rolling RMS spectrum for a 1D SNR track.'''
    x = np.asarray(snr, dtype=np.float64).ravel()
    if x.size == 0:
        return np.asarray([], dtype=np.float64)
    w = int(max(window, 1))
    if w <= 1:
        rms = np.abs(x)
    else:
        k = np.ones((w,), dtype=np.float64) / float(w)
        mu = np.convolve(np.nan_to_num(x, nan=0.0), k, mode='same')
        mu2 = np.convolve(np.nan_to_num(x * x, nan=0.0), k, mode='same')
        var = np.maximum(mu2 - mu * mu, 0.0)
        rms = np.sqrt(var)
    rms[~np.isfinite(x)] = np.nan
    return rms


def _adaptive_noise_stats(
    spec: np.ndarray,
    center: str = 'median',
    clip_sigma: float = 5.0,
    n_iter: int = 4,
    dilate_width: int = 5,
    k_exceed: float = 4.0,
) -> tuple[float, float, np.ndarray | None, str]:
    '''Estimate adaptive robust center/sigma and a retained-noise mask.'''
    x = np.asarray(spec, dtype=np.float64)
    if x.size == 0:
        return float('nan'), float('nan'), None, 'empty'
    finite = np.isfinite(x)
    if not np.any(finite):
        return float('nan'), float('nan'), None, 'empty'

    def _center(vals: np.ndarray) -> float:
        return float(np.median(vals)) if center == 'median' else float(np.mean(vals))

    def _sigma_mad(vals: np.ndarray) -> float:
        c = float(np.median(vals))
        mad = float(np.median(np.abs(vals - c)))
        return float(1.4826 * mad)

    def _sigma_neg_tail(vals: np.ndarray) -> float:
        c = float(np.median(vals))
        r = vals - c
        q16 = float(np.percentile(r, 16.0))
        return float(-q16)

    def _sigma_pos_tail(vals: np.ndarray) -> float:
        c = float(np.median(vals))
        r = vals - c
        q84 = float(np.percentile(r, 84.0))
        return float(q84)

    def _tail_metrics(vals: np.ndarray) -> tuple[float, float, float, float]:
        c = float(np.median(vals))
        r = vals - c
        q01, q25, q50, q75, q99 = np.percentile(r, [1.0, 25.0, 50.0, 75.0, 99.0])
        iqr = float(q75 - q25)
        asym = float((q99 + q01) / (q99 - q01)) if (q99 - q01) != 0 else np.nan
        hpos = float(q99 / iqr) if iqr > 0 else np.nan
        hneg = float((-q01) / iqr) if iqr > 0 else np.nan
        bowley = float((q75 + q25 - 2 * q50) / (q75 - q25)) if (q75 - q25) != 0 else np.nan
        return asym, hpos, hneg, bowley

    def _exceed(vals: np.ndarray, sig: float, kval: float) -> tuple[float, float]:
        if (not np.isfinite(sig)) or sig <= 0:
            return np.nan, np.nan
        c = float(np.median(vals))
        r = vals - c
        return float(np.mean(r > kval * sig)), float(np.mean(r < -kval * sig))

    vals0 = x[finite]
    asym, hpos, hneg, _ = _tail_metrics(vals0)
    sig_mad0 = _sigma_mad(vals0)
    p_pos, p_neg = _exceed(vals0, sig_mad0, float(k_exceed))
    if np.isfinite(hpos) and np.isfinite(hneg) and np.isfinite(asym) and np.isfinite(p_pos) and np.isfinite(p_neg):
        if hpos < 2.2 and hneg < 2.2 and abs(asym) < 0.2 and p_pos < 0.01 and p_neg < 0.01:
            regime = 'noise_dominated'
        elif (hpos > 3.0 or p_pos > 0.02 or asym > 0.3) and hneg < 2.5:
            regime = 'emission_dominated'
        elif (hneg > 3.0 or p_neg > 0.02 or asym < -0.3) and hpos < 2.5:
            regime = 'absorption_dominated'
        elif hpos > 3.0 and hneg > 3.0:
            regime = 'both_tails_strong'
        else:
            regime = 'ambiguous'
    else:
        regime = 'ambiguous'

    k = np.ones(int(max(dilate_width, 1)), dtype=np.int8)
    mask = finite.copy()
    for _ in range(int(max(n_iter, 1))):
        if not np.any(mask):
            break
        vals = x[mask]
        if regime == 'emission_dominated':
            c = float(np.median(vals))
            sig = _sigma_neg_tail(vals)
            excl = (x - c) > clip_sigma * sig
        elif regime == 'absorption_dominated':
            c = float(np.median(vals))
            sig = _sigma_pos_tail(vals)
            excl = (x - c) < -clip_sigma * sig
        else:
            c = float(np.median(vals))
            sig = _sigma_mad(vals)
            excl = np.abs(x - c) > clip_sigma * sig
        if (not np.isfinite(sig)) or sig <= 0:
            break
        excl = np.convolve(excl.astype(np.int8), k, mode='same') > 0
        mask = mask & (~excl)

    if not np.any(mask):
        return float('nan'), float('nan'), None, regime

    vals = x[mask]
    mu = _center(vals)
    if regime == 'emission_dominated':
        sig = _sigma_neg_tail(vals)
    elif regime == 'absorption_dominated':
        sig = _sigma_pos_tail(vals)
    else:
        sig = _sigma_mad(vals)
    if (not np.isfinite(sig)) or sig <= 0:
        return float('nan'), float('nan'), None, regime
    return float(mu), float(sig), np.asarray(mask, dtype=bool), regime


def _robust_sigma(img: np.ndarray) -> float:
    '''Return a robust sigma estimate using adaptive tail-aware clipping on flattened pixels.'''
    vals = np.asarray(img, dtype=np.float64).ravel()
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return 0.0
    # Approximate image sigma from a bounded pixel sample. This
    # keeps the spatial-noise logic close to the spectral path while cutting the
    # per-channel cost on large stitched mosaics.
    max_sample = 4096
    if vals.size > max_sample:
        step = int(np.ceil(vals.size / float(max_sample)))
        vals = vals[::step]
    _, sig, _, _ = _adaptive_noise_stats(vals, dilate_width=2)
    if not np.isfinite(sig) or sig <= 0:
        return 0.0
    return float(sig)


def _compute_reference_spectrum(
    cube: np.ndarray,
    sig_k: np.ndarray,
    ref_sigma: float = 3.0,
    spatial_mask: np.ndarray | None = None,
) -> np.ndarray:
    '''Compute reference spectrum by summing high-sigma pixels per channel.'''
    mask2d = None if spatial_mask is None else np.asarray(spatial_mask, dtype=bool)
    cube_use = cube.reshape(cube.shape[0], -1) if mask2d is None else cube[:, mask2d]
    sig = np.asarray(sig_k, dtype=np.float64).reshape(-1, 1)
    valid = sig[:, 0] > 0.0
    gate = np.abs(cube_use) >= (ref_sigma * sig)
    return np.sum(np.where(gate & valid[:, None], cube_use, 0.0), axis=1, dtype=np.float64)


def _compute_moment0(
    cube: np.ndarray,
    sig_k: np.ndarray,
    mom0_thresh_sigma: float = 5.0,
    spatial_mask: np.ndarray | None = None,
) -> np.ndarray:
    '''Compute moment-0 map by summing pixels above a sigma threshold.'''
    nchan, ny, nx = cube.shape
    mask2d = None if spatial_mask is None else np.asarray(spatial_mask, dtype=bool)
    cube_use = cube.reshape(nchan, -1) if mask2d is None else cube[:, mask2d]
    sig = np.asarray(sig_k, dtype=np.float64).reshape(-1, 1)
    valid = sig[:, 0] > 0.0
    gate = np.abs(cube_use) > (mom0_thresh_sigma * sig)
    mom0_vec = np.sum(np.where(gate & valid[:, None], cube_use, 0.0), axis=0, dtype=np.float64).astype(np.float32, copy=False)
    mom0 = np.zeros((ny, nx), dtype=np.float32)
    if mask2d is None:
        mom0[:] = mom0_vec.reshape((ny, nx))
    else:
        mom0[mask2d] = mom0_vec
    return mom0


def _compute_mom0_weighted_spectrum(
    cube: np.ndarray,
    sig_k: np.ndarray,
    moment0: np.ndarray,
    gate_sigma: float = 1.0,
    spatial_mask: np.ndarray | None = None,
) -> np.ndarray:
    '''Compute spectrum weighted by moment-0 amplitudes and a per-channel gate.'''
    mask2d = None if spatial_mask is None else np.asarray(spatial_mask, dtype=bool)
    cube_use = cube.reshape(cube.shape[0], -1) if mask2d is None else cube[:, mask2d]
    w = np.abs(moment0).astype(np.float32, copy=False)
    w_use = w.ravel() if mask2d is None else w[mask2d]
    if not np.any(w_use > 0):
        return np.zeros(cube.shape[0], dtype=np.float64)
    sig = np.asarray(sig_k, dtype=np.float64).reshape(-1, 1)
    valid = sig[:, 0] > 0.0
    gate = (np.abs(cube_use) >= (gate_sigma * sig)) & (w_use[None, :] > 0.0) & valid[:, None]
    return np.sum(np.where(gate, cube_use * w_use[None, :], 0.0), axis=1, dtype=np.float64)


def _snr_from_spectrum(
    spec: np.ndarray,
    center: str = 'median',
    clip_sigma: float = 5.0,
    n_iter: int = 4,
    dilate_width: int = 5,
    k_exceed: float = 4.0,
    return_mask: bool = False,
) -> tuple[np.ndarray, np.ndarray | None] | np.ndarray:
    '''Normalize a spectrum using adaptive tail-aware clipping.'''
    x = np.asarray(spec, dtype=np.float64)
    snr = np.full_like(x, np.nan, dtype=np.float64)
    if x.size == 0:
        return (snr, None) if return_mask else snr
    mu, sig, mask, _ = _adaptive_noise_stats(
        x,
        center=center,
        clip_sigma=clip_sigma,
        n_iter=n_iter,
        dilate_width=dilate_width,
        k_exceed=k_exceed,
    )
    if mask is None or (not np.isfinite(sig)) or sig <= 0:
        return (snr, None) if return_mask else snr

    snr = (x - mu) / sig
    return (snr, mask) if return_mask else snr


def _estimate_noise_autocorr(
    snr: np.ndarray,
    noise_mask: np.ndarray | None,
    maxlag: int = 64,
) -> np.ndarray:
    '''Estimate noise autocorrelation coefficients from SNR and a noise mask.'''
    x = np.asarray(snr, dtype=np.float64).ravel()
    n = x.size
    if n == 0:
        return np.ones((1,), dtype=np.float64)
    if noise_mask is None:
        m = np.isfinite(x)
    else:
        m = np.asarray(noise_mask, dtype=bool).ravel()
        if m.size != n:
            m = np.resize(m, n)
        m = m & np.isfinite(x)
    if np.count_nonzero(m) < 16:
        return np.ones((1,), dtype=np.float64)

    x0 = x.copy()
    x0[~m] = 0.0
    if np.any(m):
        med = float(np.nanmedian(x[m]))
        x0[m] = x[m] - med

    max_lag_i = int(min(max(maxlag, 1), n - 1))
    rho = np.zeros((max_lag_i + 1,), dtype=np.float64)
    rho[0] = 1.0
    var0 = float(np.nanvar(x[m]))
    if (not np.isfinite(var0)) or var0 <= 0.0:
        return rho

    for lag in range(1, max_lag_i + 1):
        valid = m[:-lag] & m[lag:]
        count = int(np.count_nonzero(valid))
        if count < 8:
            break
        a = x[:-lag][valid]
        b = x[lag:][valid]
        va = float(np.nanvar(a))
        vb = float(np.nanvar(b))
        if va <= 0.0 or vb <= 0.0:
            continue
        cov = float(np.nanmean((a - np.nanmean(a)) * (b - np.nanmean(b))))
        r = cov / np.sqrt(va * vb)
        if np.isfinite(r):
            rho[lag] = float(np.clip(r, -0.95, 0.95))
    return rho


def _effective_nbin_from_rho(nbin: int, rho: np.ndarray) -> float:
    '''Compute the effective sample count for one top-hat scale from autocorrelation.'''
    n = int(max(nbin, 1))
    rho1 = np.asarray(rho, dtype=np.float64).ravel()
    if rho1.size <= 1:
        return float(n)
    m = int(min(n - 1, rho1.size - 1))
    if m <= 0:
        return float(n)
    k = np.arange(1, m + 1, dtype=np.float64)
    denom = float(n + 2.0 * np.sum((n - k) * rho1[1:m + 1]))
    if (not np.isfinite(denom)) or denom <= 0.0:
        return float(n)
    n_eff = float((n * n) / denom)
    if not np.isfinite(n_eff):
        return float(n)
    return float(max(1.0, min(float(n), n_eff)))


def cube_threshold_spectrum(
    vis: str,
    dish_diameter_m: float,
    ddid: int = 0,
    spw_name: str | None = None,
    field: int | None = None,
    timebin_sec: float = 240,
    npix: int = 256,
    fov_pb_mult: float = 1.0,
    ref_sigma: float = 3.0,
    mom0_thresh_sigma: float = 5.0,
    gate_sigma: float = 1.0,
    ref_zero_frac_thr: float = 0.05,
    mom0_zero_frac_thr: float = 0.05,
    ref_smooth_width: int = 4,
    mom0_smooth_width: int = 4,
    neg_extent_delta_thr: float = 5.0,
    neg_extent_trim_frac: float = 0.10,
    verbose: bool = True,
    save_cube_path: str | None = None,
    save_moment0_path: str | None = None,
    compute_moment0_weighted_spectrum: bool = True,
    compute_products: bool = True,
    preloaded: dict[str, np.ndarray] | None = None,
    uv_taper_auto: bool = False,
    uv_taper_sigma_uv: float | None = None,
    uv_taper_fwhm_cell: float = 2.0,
    cell_arcsec_override: float | None = None,
    return_cube: bool = False,
    log_dir: str | None = None,
) -> dict[str, Any]:
    '''Generate a cube and spectra using preloaded visibilities.'''
    if preloaded is None:
        raise RuntimeError('cube_threshold_spectrum requires preloaded data in MPI mode.')
    v = preloaded['V']
    wrow = preloaded['W']
    u_m = preloaded['U_m']
    v_m = preloaded['V_m']
    lam = preloaded['lam']
    nchan = v.shape[1]
    pb = estimate_pb_fwhm_arcsec(preloaded['ref_freq_hz'], dish_diameter_m)
    t_cube = time.perf_counter()
    t_gridprep = time.perf_counter()
    idx, w, inb, idx2, w2, inb2, diag = _precompute_grid_indices(
        u_m,
        v_m,
        lam,
        wrow,
        npix=npix,
        fov_pb_mult=fov_pb_mult,
        pb_fwhm_arcsec=pb,
        uv_taper_auto=uv_taper_auto,
        uv_taper_sigma_uv=uv_taper_sigma_uv,
        uv_taper_fwhm_cell=uv_taper_fwhm_cell,
        cell_arcsec_override=cell_arcsec_override,
    )
    dt_gridprep = time.perf_counter() - t_gridprep
    _profile_logf(log_dir, 'cube_threshold_spectrum grid_precompute spw=%s field=%s nchan=%s dt=%.3f profile_dt=%.3f', str(spw_name), str(field), nchan, dt_gridprep, float(diag.get('profile_dt_total', 0.0)))
    if verbose:
        _rank_logf(
            log_dir,
            '[grid] fov_rad=%.3e cell=%.4f" npix=%s',
            diag['fov_rad'],
            diag['cell_arcsec'],
            diag['npix'],
        )
        _rank_logf(
            log_dir,
            '[grid] rows=%s nonzero_w=%s inbounds=%s dropped=%s drop_frac=%.3f',
            diag['nrow'],
            diag['nrow_nonzero_w'],
            diag['nrow_inbounds'],
            diag['nrow_dropped'],
            diag['drop_frac'],
        )
        if diag.get('uv_taper_applied'):
            _rank_logf(
                log_dir,
                '[grid] uv_taper sigma_uv=%.3g auto=%s fwhm_cell=%.3g',
                diag['uv_taper_sigma_uv'],
                diag['uv_taper_auto'],
                diag['uv_taper_fwhm_cell'],
            )

    t_makecube = time.perf_counter()
    cube = np.zeros((nchan, npix, npix), dtype=np.float32)
    for ch in range(nchan):
        img, _, _ = _image_from_vis_precomputed(
            v[:, ch], npix, idx, w, inb, idx2, w2, inb2, return_timing=True
        )
        cube[ch] = img.astype(np.float32, copy=False)
    dt_makecube = time.perf_counter() - t_makecube
    _profile_logf(log_dir, 'cube_threshold_spectrum makecube spw=%s field=%s nchan=%s dt=%.3f', str(spw_name), str(field), nchan, dt_makecube)

    if save_cube_path is not None:
        np.save(save_cube_path, cube)
        if verbose:
            _rank_logf(log_dir, '[cube] saved %s', save_cube_path)
    products = None
    dt_products = 0.0
    if compute_products:
        t_products = time.perf_counter()
        products = _compute_cube_products(
            cube,
            ref_sigma=ref_sigma,
            mom0_thresh_sigma=mom0_thresh_sigma,
            gate_sigma=gate_sigma,
            ref_zero_frac_thr=ref_zero_frac_thr,
            mom0_zero_frac_thr=mom0_zero_frac_thr,
            ref_smooth_width=ref_smooth_width,
            mom0_smooth_width=mom0_smooth_width,
            neg_extent_delta_thr=neg_extent_delta_thr,
            neg_extent_trim_frac=neg_extent_trim_frac,
        )
        if not compute_moment0_weighted_spectrum:
            products['moment0_weighted_sum_raw'] = np.zeros((nchan,), dtype=np.float32)
            products['moment0_weighted_sum_snr'] = np.zeros((nchan,), dtype=np.float32)
            products['evidence'] = products['reference_sum_snr'].copy()
        dt_products = time.perf_counter() - t_products
        _profile_logf(log_dir, 'cube_threshold_spectrum products spw=%s field=%s dt=%.3f', str(spw_name), str(field), dt_products)

        if save_moment0_path is not None:
            np.save(save_moment0_path, products['moment0'].astype(np.float32, copy=False))
            if verbose:
                _rank_logf(log_dir, '[cube] saved moment0 %s', save_moment0_path)

    total_dt = time.perf_counter() - t_cube
    if verbose:
        _rank_logf(log_dir, '[cube] total dt=%.2fs', total_dt)

    out = {
        'nchan': nchan,
        'pb_fwhm_arcsec': float(pb),
        'cube_path': save_cube_path,
        'moment0_path': save_moment0_path,
        'uv_taper_applied': bool(diag.get('uv_taper_applied', False)),
        'uv_taper_sigma_uv': float(diag.get('uv_taper_sigma_uv', 0.0)),
        'grid_meta': {
            'npix': int(diag.get('npix', npix)),
            'cell_arcsec': float(diag.get('cell_arcsec', np.nan)),
            'fov_rad': float(diag.get('fov_rad', np.nan)),
            'drop_frac': float(diag.get('drop_frac', np.nan)),
            'grid_weight_sum': float(diag.get('grid_weight_sum', np.nan)),
            'grid_weight_sum_conj': float(diag.get('grid_weight_sum_conj', np.nan)),
        },
        'spectra_qc': copy.deepcopy(products.get('spectra_qc', {})) if products is not None else {},
        'reference_sum_noise_mask': products.get('reference_sum_noise_mask') if products is not None else None,
        'moment0_weighted_sum_noise_mask': products.get('moment0_weighted_sum_noise_mask') if products is not None else None,
        'timing': {
            'grid_precompute_s': float(dt_gridprep),
            'cube_imaging_s': float(dt_makecube),
            'product_compute_s': float(dt_products),
            'total_s': float(total_dt),
        },
    }
    if products is not None:
        out.update({
            'spectrum': products['reference_sum_raw'],
            'moment0': products['moment0'],
            'moment0_weighted_spectrum': products['moment0_weighted_sum_raw'],
            'reference_sum_raw_processed': products['reference_sum_raw_processed'],
            'moment0_weighted_sum_raw_processed': products['moment0_weighted_sum_raw_processed'],
            'sigma': products['sigma'],
            'reference_sum_snr': products['reference_sum_snr'],
            'moment0_weighted_sum_snr': products['moment0_weighted_sum_snr'],
            'evidence': products['evidence'],
        })
    if return_cube:
        out['cube'] = cube
    return out


def _acf_hwhm_fwhm(
    spec: np.ndarray,
    smooth: int = 61,
    maxlag: int = 200,
    smooth_frac: float | None = None,
    edge_trim_frac: float = 0.0,
) -> tuple[int, int]:
    '''Estimate half-width and full-width from the autocorrelation.'''
    y = np.asarray(spec, dtype=np.float64)
    y = y[np.isfinite(y)]
    if y.size < 8:
        return 1, 2

    trim = float(min(max(edge_trim_frac, 0.0), 0.45))
    if trim > 0.0:
        lo = int(np.floor(trim * y.size))
        hi = int(np.ceil((1.0 - trim) * y.size))
        if hi > lo + 5:
            y = y[lo:hi]

    smooth_i = int(max(smooth, 1))
    if smooth_frac is not None and np.isfinite(float(smooth_frac)):
        smooth_i = int(max(1, round(float(smooth_frac) * y.size)))

    if smooth_i > 3:
        kern = np.ones((smooth_i,), dtype=np.float64) / float(smooth_i)
        baseline = np.convolve(y, kern, mode='same')
    else:
        baseline = np.median(y)
    yhp = y - baseline
    ac = np.correlate(yhp, yhp, mode='full')
    ac = ac[ac.size // 2:]
    if ac.size == 0:
        return 1, 2
    ac /= ac[0] if ac[0] != 0 else 1.0
    if maxlag is not None:
        ac = ac[:max(2, int(maxlag) + 1)]
    hwhm = None
    lag_stop = ac.size if maxlag is None else min(int(maxlag), ac.size)
    for lag in range(1, lag_stop):
        if ac[lag] < 0.5:
            hwhm = lag
            break
    if hwhm is None:
        hwhm = max(1, lag_stop - 1)
    fwhm = 2 * hwhm
    return hwhm, fwhm


def _mask_to_ranges(mask: np.ndarray) -> list[tuple[int, int]]:
    '''Convert a boolean mask into contiguous index ranges.'''
    idx = np.where(mask)[0]
    if idx.size == 0:
        return []
    cuts = np.where(np.diff(idx) > 1)[0] + 1
    blocks = np.split(idx, cuts)
    return [(int(b[0]), int(b[-1])) for b in blocks]


def _now_utc_iso() -> str:
    '''Return current UTC timestamp in ISO-8601 Z format.'''
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _source_name_for_id(source_names: dict[int, str], source_id: int) -> str:
    '''Return a stable source name for a source_id.'''
    name = source_names.get(int(source_id))
    if name:
        return str(name)
    return f'source_{int(source_id)}'


def _sanitize_token(text: str) -> str:
    '''Return a filename-safe token from arbitrary text.'''
    return re.sub(r'[^A-Za-z0-9._-]+', '_', str(text)).strip('_')


def _field_name_for_id(field_names: list[str], field_id: int) -> str:
    '''Return a stable field name for a field_id.'''
    if 0 <= int(field_id) < len(field_names):
        return str(field_names[int(field_id)])
    return f'field_{int(field_id)}'


def _chan_ranges_to_frame_freq_ranges_ghz(
    chan_ranges: list[tuple[int, int]],
    chan_freqs_hz: np.ndarray | None,
) -> list[tuple[float, float]]:
    '''Convert channel ranges into output-frame frequency ranges in GHz.'''
    return imaging.chan_ranges_to_freq_ranges_ghz(chan_ranges, chan_freqs_hz)


def _fmt_frame_freq_ranges(
    freq_ranges_ghz: list[tuple[float, float]],
    outframe: str,
) -> list[str]:
    '''Format GHz ranges to cont.dat-like lines.'''
    return [f'{lo:.10f}~{hi:.10f}GHz {str(outframe)}' for lo, hi in freq_ranges_ghz]


def _roi_detected_from_raw(
    mini: dict[str, Any] | None,
    chan_freqs_hz: np.ndarray | None = None,
    outframe: str = 'LSRK',
) -> dict[str, Any] | None:
    '''Strip internal ROI detection fields from an ROI detection result.'''
    if mini is None:
        nchan = int(np.asarray(chan_freqs_hz, dtype=np.float64).size) if chan_freqs_hz is not None else 0
        cont_ranges = [(0, nchan - 1)] if nchan > 0 else []
        cont_freq_ranges_ghz = _chan_ranges_to_frame_freq_ranges_ghz(cont_ranges, chan_freqs_hz)
        out = {
            'outframe': str(outframe),
            'threshold_snr': float('nan'),
            'neg_threshold_snr': float('nan'),
            'bin_scales': (),
            'fwhm_chan': 4,
            'fwhm_kms': float('nan'),
            'acf_fwhm_kms_spw': float('nan'),
            'dv_kms': float('nan'),
            'line_ranges': [],
            'line_range_peakSNR': [],
            'neg_line_ranges': [],
            'neg_line_range_peakSNR': [],
            'cont_ranges': cont_ranges,
            'line_freq_ranges_ghz': [],
            'neg_line_freq_ranges_ghz': [],
            'cont_freq_ranges_ghz': cont_freq_ranges_ghz,
            'line_freq_ranges': [],
            'neg_line_freq_ranges': [],
            'cont_freq_ranges': _fmt_frame_freq_ranges(cont_freq_ranges_ghz, outframe),
            'reference_zero_fraction': float('nan'),
            'moment0_zero_fraction': float('nan'),
            'reference_smoothed': False,
            'moment0_smoothed': False,
            'moment0_rejected_zero_fraction': False,
            'moment0_rejected_negative_extent': False,
            'mom0_usage_mode': 'used',
            'negative_extent_delta_sigma': float('nan'),
            'renorm_ratio_reference': 1.0,
            'renorm_ratio_moment0': 1.0,
            'fwhm_selection_mode': 'default_4chan',
            'linewidth_fallback_level': 'default_4chan',
            'fwhm_global_fallback_triggered': False,
            'snr_failed_reference': False,
            'snr_failed_moment0': False,
            'snr_failed_both': False,
            'evidence_valid_fraction': 0.0,
            'roi_skipped_reason': 'missing_mini_input',
            'decision_trace': {},
        }
        out['line_freq_ranges_lsrk_ghz'] = out['line_freq_ranges_ghz']
        out['neg_line_freq_ranges_lsrk_ghz'] = out['neg_line_freq_ranges_ghz']
        out['cont_freq_ranges_lsrk_ghz'] = out['cont_freq_ranges_ghz']
        out['line_freq_ranges_lsrk'] = out['line_freq_ranges']
        out['neg_line_freq_ranges_lsrk'] = out['neg_line_freq_ranges']
        out['cont_freq_ranges_lsrk'] = out['cont_freq_ranges']
        return out
    line_ranges = [(int(a), int(b)) for a, b in mini.get('line_ranges', [])]
    neg_line_ranges = [(int(a), int(b)) for a, b in mini.get('neg_line_ranges', [])]
    cont_ranges = [(int(a), int(b)) for a, b in mini.get('cont_ranges', [])]
    line_freq_ranges_ghz = _chan_ranges_to_frame_freq_ranges_ghz(line_ranges, chan_freqs_hz)
    neg_line_freq_ranges_ghz = _chan_ranges_to_frame_freq_ranges_ghz(neg_line_ranges, chan_freqs_hz)
    cont_freq_ranges_ghz = _chan_ranges_to_frame_freq_ranges_ghz(cont_ranges, chan_freqs_hz)
    out = {
        'outframe': str(outframe),
        'threshold_snr': float(mini['thr']),
        'neg_threshold_snr': float(mini.get('neg_threshold_snr', np.nan)),
        'bin_scales': tuple(int(v) for v in mini.get('bin_scales', ())),
        'fwhm_chan': int(mini['fwhm_chan']),
        'fwhm_kms': float(mini['fwhm_kms']),
        'acf_fwhm_kms_spw': float(mini.get('acf_fwhm_kms_spw', np.nan)),
        'dv_kms': float(mini['dv_kms']),
        'line_ranges': line_ranges,
        'line_range_peakSNR': [float(v) for v in mini.get('line_range_peakSNR', [])],
        'neg_line_ranges': neg_line_ranges,
        'neg_line_range_peakSNR': [float(v) for v in mini.get('neg_line_range_peakSNR', [])],
        'cont_ranges': cont_ranges,
        'line_freq_ranges_ghz': line_freq_ranges_ghz,
        'neg_line_freq_ranges_ghz': neg_line_freq_ranges_ghz,
        'cont_freq_ranges_ghz': cont_freq_ranges_ghz,
        'line_freq_ranges': _fmt_frame_freq_ranges(line_freq_ranges_ghz, outframe),
        'neg_line_freq_ranges': _fmt_frame_freq_ranges(neg_line_freq_ranges_ghz, outframe),
        'cont_freq_ranges': _fmt_frame_freq_ranges(cont_freq_ranges_ghz, outframe),
        'reference_zero_fraction': float(mini.get('reference_zero_fraction', np.nan)),
        'moment0_zero_fraction': float(mini.get('moment0_zero_fraction', np.nan)),
        'reference_smoothed': bool(mini.get('reference_smoothed', False)),
        'moment0_smoothed': bool(mini.get('moment0_smoothed', False)),
        'moment0_rejected_zero_fraction': bool(mini.get('moment0_rejected_zero_fraction', False)),
        'moment0_rejected_negative_extent': bool(mini.get('moment0_rejected_negative_extent', False)),
        'mom0_usage_mode': str(mini.get('mom0_usage_mode', 'used')),
        'negative_extent_delta_sigma': float(mini.get('negative_extent_delta_sigma', np.nan)),
        'renorm_ratio_reference': float(mini.get('renorm_ratio_reference', 1.0)),
        'renorm_ratio_moment0': float(mini.get('renorm_ratio_moment0', 1.0)),
        'fwhm_selection_mode': str(mini.get('fwhm_selection_mode', 'global')),
        'linewidth_fallback_level': str(mini.get('linewidth_fallback_level', mini.get('fwhm_selection_mode', 'global'))),
        'fwhm_global_fallback_triggered': bool(mini.get('fwhm_global_fallback_triggered', False)),
        'snr_failed_reference': bool(mini.get('snr_failed_reference', False)),
        'snr_failed_moment0': bool(mini.get('snr_failed_moment0', False)),
        'snr_failed_both': bool(mini.get('snr_failed_both', False)),
        'evidence_valid_fraction': float(mini.get('evidence_valid_fraction', np.nan)),
        'roi_skipped_reason': str(mini.get('roi_skipped_reason', 'none')),
        'decision_trace': copy.deepcopy(mini.get('decision_trace', {})),
    }
    out['line_freq_ranges_lsrk_ghz'] = out['line_freq_ranges_ghz']
    out['neg_line_freq_ranges_lsrk_ghz'] = out['neg_line_freq_ranges_ghz']
    out['cont_freq_ranges_lsrk_ghz'] = out['cont_freq_ranges_ghz']
    out['line_freq_ranges_lsrk'] = out['line_freq_ranges']
    out['neg_line_freq_ranges_lsrk'] = out['neg_line_freq_ranges']
    out['cont_freq_ranges_lsrk'] = out['cont_freq_ranges']
    return out


def _spectra_block_from_raw(s: dict[str, Any]) -> dict[str, Any]:
    '''Build a spectra block from an internal spectra result.'''
    return {
        'reference_sum_raw': s['reference_sum_raw'],
        'moment0_weighted_sum_raw': s['moment0_weighted_sum_raw'],
        'reference_sum_raw_processed': s.get('reference_sum_raw_processed'),
        'moment0_weighted_sum_raw_processed': s.get('moment0_weighted_sum_raw_processed'),
        'reference_sum_snr': s['reference_sum_snr'],
        'moment0_weighted_sum_snr': s['moment0_weighted_sum_snr'],
        'evidence': s['evidence'],
        'evidence_negative': s.get('evidence_negative'),
        'reference_rms_spectrum': s.get('reference_rms_spectrum'),
        'moment0_rms_spectrum': s.get('moment0_rms_spectrum'),
        'roi_union_mask': s.get('roi_union_mask'),
    }


def _artifact_block_from_raw(s: dict[str, Any]) -> dict[str, Any]:
    '''Build an artifact block from an internal spectra result.'''
    return {
        'cube_path': s.get('cube_path'),
        'moment0_path': s.get('moment0_path'),
        'mosaic_weights_path': s.get('mosaic_weights_path'),
    }


def _source_spw_identity_block(
    source_id: int,
    source_name: str,
    spw_id: int,
    spw_name: str,
    ddid: int,
    outframe: str,
) -> dict[str, Any]:
    '''Build source-aggregate identity metadata for one source/SPW block.'''
    return {
        'source_id': int(source_id),
        'source_name': str(source_name),
        'field_id': None,
        'field_name': None,
        'field_role': 'source_level',
        'spw_id': int(spw_id),
        'spw_name': str(spw_name),
        'ddid': int(ddid),
        'outframe': str(outframe),
    }


def _field_identity_block(
    source_id: int,
    source_name: str,
    field_id: int,
    field_name: str,
    spw_id: int,
    spw_name: str,
    ddid: int,
    is_mosaic: bool,
    outframe: str,
) -> dict[str, Any]:
    '''Build per-field identity metadata for one source/SPW block.'''
    return {
        'source_id': int(source_id),
        'source_name': str(source_name),
        'field_id': int(field_id),
        'field_name': str(field_name),
        'field_role': 'pointing' if is_mosaic else 'single_field',
        'spw_id': int(spw_id),
        'spw_name': str(spw_name),
        'ddid': int(ddid),
        'outframe': str(outframe),
    }


def _build_findroi_stage_product(
    *,
    input_vis_arg: str | list[str],
    vis_list: list[str],
    tmp_dir: str,
    prefix: str,
    field_selection: str | int | list[int] | None,
    config: dict[str, Any],
    inv: list[dict[str, Any]],
    sci_ddids: list[int],
    science_spws: dict[str, dict[str, Any]],
    field_info: dict[str, Any],
    spw_results: list[dict[str, Any]],
    findroi_blocks: list[dict[str, Any]],
    source_fwhm_kms_by_id: dict[int, float],
    source_fwhm_mode_by_id: dict[int, str],
    common_geometry_plan: dict[int, dict[str, Any]] | None,
    run_timing: dict[str, Any],
    save_results_path: str | None,
) -> dict[str, Any]:
    '''Build the canonical findROI stage product schema.'''
    selected_ddids = {int(v) for v in sci_ddids}
    source_names_by_id = {int(k): str(v) for k, v in field_info.get('source_names', {}).items()}
    field_names = [str(v) for v in field_info.get('field_names', [])]

    findroi_by_spw_id = {int(r['spw_id']): r for r in findroi_blocks}

    inventory_sources: dict[str, dict[str, Any]] = {}
    for source_id, field_ids in field_info.get('groups', {}).items():
        source_name = _source_name_for_id(source_names_by_id, int(source_id))
        inventory_sources[source_name] = {
            'source_id': int(source_id),
            'source_name': source_name,
            'is_mosaic': len(field_ids) > 1,
            'fields': {
                int(fid): {
                    'field_id': int(fid),
                    'field_name': _field_name_for_id(field_names, int(fid)),
                }
                for fid in sorted(field_ids)
            },
        }

    linewidth_summary: dict[str, dict[str, Any]] = {}
    contributor_counts: dict[str, int] = {}
    for source_name, src_meta in inventory_sources.items():
        sid = int(src_meta['source_id'])
        if sid in source_fwhm_kms_by_id:
            linewidth_summary[source_name] = {
                'source_id': sid,
                'source_name': source_name,
                'fwhm_kms_global': float(source_fwhm_kms_by_id[sid]),
                'weighting': '(1/dv_kms)^0.5 * max(evidence)',
                'fwhm_selection_mode': str(source_fwhm_mode_by_id.get(sid, 'global')),
                'n_contributors': 0,
            }

    for spw_res in spw_results:
        for source_id, fields in spw_res.get('sources', {}).items():
            source_name = _source_name_for_id(source_names_by_id, int(source_id))
            if source_name not in linewidth_summary:
                continue
            for field_id, s in fields.items():
                if isinstance(field_id, str):
                    continue
                if s.get('chan_width_hz') is not None and s.get('ref_freq_hz') is not None:
                    contributor_counts[source_name] = contributor_counts.get(source_name, 0) + 1
    for source_name, count in contributor_counts.items():
        linewidth_summary[source_name]['n_contributors'] = int(count)

    products_fields: dict[str, dict[str, Any]] = {}
    for spw_res in spw_results:
        spw_id = int(spw_res['spw_id'])
        spw_key = str(spw_id)
        spw_name = str(spw_res['spw_name'])
        findroi_block = findroi_by_spw_id.get(spw_id, {'sources': {}})
        ddid = None
        if spw_key in science_spws:
            ddid = int(science_spws[spw_key]['ddid'])
        else:
            for row in inv:
                if int(row['spw_id']) == spw_id and int(row['ddid']) in selected_ddids:
                    ddid = int(row['ddid'])
                    break
        if ddid is None:
            continue

        for source_id, field_results in spw_res.get('sources', {}).items():
            source_id = int(source_id)
            source_name = _source_name_for_id(source_names_by_id, source_id)
            field_ids = sorted([int(fid) for fid in field_results.keys() if not isinstance(fid, str)])
            is_mosaic = ('mosaic' in field_results) or (len(field_ids) > 1)
            products_fields.setdefault(source_name, {})
            src_spw_block = {
                'is_mosaic': bool(is_mosaic),
                'source_aggregate': {},
                'per_field': {},
            }

            # Per-field blocks
            for field_id in field_ids:
                raw_field = field_results[field_id]
                mini_raw = findroi_block.get('sources', {}).get(source_id, {}).get(field_id)
                outframe = str(raw_field.get('outframe', 'LSRK'))
                chan_freqs_hz = raw_field.get('chan_freqs_hz')
                field_block = {
                    'identity': _field_identity_block(
                        source_id=source_id,
                        source_name=source_name,
                        field_id=field_id,
                        field_name=_field_name_for_id(field_names, field_id),
                        spw_id=spw_id,
                        spw_name=spw_name,
                        ddid=ddid,
                        is_mosaic=is_mosaic,
                        outframe=outframe,
                    ),
                    'spectra': _spectra_block_from_raw(raw_field),
                    'roi_detected': _roi_detected_from_raw(mini_raw, chan_freqs_hz=chan_freqs_hz, outframe=outframe),
                    'timing': copy.deepcopy(raw_field.get('timing', {})),
                    'artifacts': _artifact_block_from_raw(raw_field),
                    'channel_axis': {
                        'ref_freq_hz': raw_field.get('ref_freq_hz'),
                        'chan_width_hz': raw_field.get('chan_width_hz'),
                        'chan_freqs_hz': chan_freqs_hz,
                        'outframe': outframe,
                    },
                }
                src_spw_block['per_field'][field_id] = field_block

            # Source aggregate block
            if is_mosaic and 'mosaic' in field_results:
                raw_src = field_results['mosaic']
                mini_src = findroi_block.get('sources', {}).get(source_id, {}).get('mosaic')
                outframe = str(raw_src.get('outframe', 'LSRK'))
                chan_freqs_hz = raw_src.get('chan_freqs_hz')
                src_spw_block['source_aggregate'] = {
                    'identity': _source_spw_identity_block(
                        source_id=source_id,
                        source_name=source_name,
                        spw_id=spw_id,
                        spw_name=spw_name,
                        ddid=ddid,
                        outframe=outframe,
                    ),
                    'spectra': _spectra_block_from_raw(raw_src),
                    'roi_detected': _roi_detected_from_raw(mini_src, chan_freqs_hz=chan_freqs_hz, outframe=outframe),
                    'timing': copy.deepcopy(raw_src.get('timing', {})),
                    'artifacts': _artifact_block_from_raw(raw_src),
                    'channel_axis': {
                        'ref_freq_hz': raw_src.get('ref_freq_hz'),
                        'chan_width_hz': raw_src.get('chan_width_hz'),
                        'chan_freqs_hz': chan_freqs_hz,
                        'outframe': outframe,
                    },
                }
            elif len(src_spw_block['per_field']) == 1:
                only_field_id = next(iter(src_spw_block['per_field']))
                src_block = copy.deepcopy(src_spw_block['per_field'][only_field_id])
                outframe = str(src_block.get('identity', {}).get('outframe', 'LSRK'))
                src_block['identity'] = _source_spw_identity_block(
                    source_id=source_id,
                    source_name=source_name,
                    spw_id=spw_id,
                    spw_name=spw_name,
                    ddid=ddid,
                    outframe=outframe,
                )
                src_spw_block['source_aggregate'] = src_block
            else:
                src_spw_block['source_aggregate'] = {}

            products_fields[source_name][spw_key] = src_spw_block

    return {
        'metadata': {
            'mous_uid': prefix,
            'created_utc': _now_utc_iso(),
            'inputs': {
                'input_vis_arg': input_vis_arg,
                'vis_list': list(vis_list),
                'tmp_dir': tmp_dir,
            },
            'config': dict(config),
            'common_geometry_plan': copy.deepcopy(common_geometry_plan or {}),
            'timing': copy.deepcopy(run_timing),
            'artifacts': {
                'results_pickle': save_results_path,
            },
        },
        'inventory': {
            'science_spws': science_spws,
            'sources': inventory_sources,
        },
        'products': {
            'source_linewidth_summary': linewidth_summary,
            'fields': products_fields,
        },
    }


def _science_spw_metadata_from_inventory(
    vis: str,
    ms: Any,
    inv: list[dict[str, Any]],
    sci_ddids: list[int],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    '''Build canonical science-SPW metadata from context-backed inventory/MS state.'''
    selected_ddids = {int(v) for v in sci_ddids}
    science_spws: dict[str, dict[str, Any]] = {}
    science_rows: list[dict[str, Any]] = []
    c_kms = casa_tools.quanta.getvalue(
        casa_tools.quanta.convert(casa_tools.quanta.constants('c'), 'km/s')
    )[0]
    for row in inv:
        if int(row['ddid']) not in selected_ddids:
            continue
        spw_id = int(row['spw_id'])
        ref_freq_hz = None
        chan_width_hz = None
        chan_width_kms = None
        try:
            chan_freqs_hz = np.asarray(get_chan_freqs_hz(ms, ddid=int(row['ddid'])), dtype=np.float64).ravel()
            if chan_freqs_hz.size > 0:
                ref_freq_hz = float(np.median(chan_freqs_hz))
            if chan_freqs_hz.size > 1:
                chan_diffs_hz = np.diff(chan_freqs_hz)
                finite_diffs = chan_diffs_hz[np.isfinite(chan_diffs_hz)]
                if finite_diffs.size > 0:
                    chan_width_hz = float(np.median(finite_diffs))
            if ref_freq_hz and chan_width_hz:
                chan_width_kms = float((chan_width_hz / ref_freq_hz) * c_kms)
        except Exception as exc:
            LOG.warning(
                'Failed to derive canonical channel-axis metadata for hif_findroi ddid=%s spw=%s vis=%s: %s',
                row['ddid'],
                spw_id,
                vis,
                exc,
            )
        if ref_freq_hz is not None:
            row_use = dict(row)
            row_use['ref_freq_hz'] = ref_freq_hz
            science_rows.append(row_use)
        science_spws[str(spw_id)] = {
            'ddid': int(row['ddid']),
            'spw_id': spw_id,
            'spw_name': str(row['name']),
            'nchan': int(row['nchan']),
            'channel_axis': {
                'ref_freq_hz': ref_freq_hz,
                'chan_width_hz': chan_width_hz,
                'chan_width_kms': chan_width_kms,
            },
        }
    return science_spws, science_rows


def _save_default_summary_plots(
    results: dict[str, Any],
    products_dir: str,
) -> dict[str, dict[str, str]]:
    '''Generate and save per-source summary plots; return artifact paths.'''
    import matplotlib.pyplot as plt
    from pipeline.hif.tasks.findroi import plots as fplots
    plt.ioff()

    os.makedirs(products_dir, exist_ok=True)
    out: dict[str, dict[str, str]] = {}
    cfg = results.get('metadata', {}).get('config', {})
    pos_thr = float(cfg.get('pos_evidence_thr', cfg.get('evidence_thr', 7.0)))
    neg_thr = float(cfg.get('neg_evidence_thr', 7.0))
    source_names = sorted(results.get('products', {}).get('fields', {}).keys())
    for source_name in source_names:
        token = _sanitize_token(source_name)
        per_source: dict[str, str] = {}
        try:
            fplots.plot_spectra_by_spw(results, source_name=source_name, field_id=None, use_snr=True)
            fig = plt.gcf()
            p_spectra = os.path.join(products_dir, f'findroi_source-{token}_spectra.png')
            fig.savefig(p_spectra, dpi=160, bbox_inches='tight')
            plt.close(fig)
            per_source['spectra_png'] = p_spectra

            fplots.plot_moment0_by_spw(results, source_name=source_name, field_id=None)
            fig = plt.gcf()
            p_mom0 = os.path.join(products_dir, f'findroi_source-{token}_moment0.png')
            fig.savefig(p_mom0, dpi=160, bbox_inches='tight')
            plt.close(fig)
            per_source['moment0_png'] = p_mom0

            fplots.plot_evidence_with_lines(
                results,
                source_name=source_name,
                field_id=None,
                min_region_snr=pos_thr,
                min_neg_region_snr=neg_thr,
            )
            fig = plt.gcf()
            p_evidence = os.path.join(products_dir, f'findroi_source-{token}_evidence.png')
            fig.savefig(p_evidence, dpi=160, bbox_inches='tight')
            plt.close(fig)
            per_source['evidence_png'] = p_evidence

            out[source_name] = per_source
        except Exception as exc:
            LOG.warning('Failed to generate default hif_findroi summary plots for source %s: %s', source_name, exc)
            plt.close('all')
    return out


def _merge_channel_ranges(ranges: list[tuple[int, int]], nchan: int) -> list[tuple[int, int]]:
    '''Merge overlapping channel ranges after clipping to channel bounds.'''
    if nchan <= 0:
        return []
    clipped: list[tuple[int, int]] = []
    for lo, hi in ranges:
        a = max(0, min(int(lo), nchan - 1))
        b = max(0, min(int(hi), nchan - 1))
        if b < a:
            a, b = b, a
        clipped.append((a, b))
    if not clipped:
        return []
    clipped.sort(key=lambda x: x[0])
    merged: list[tuple[int, int]] = [clipped[0]]
    for lo, hi in clipped[1:]:
        mlo, mhi = merged[-1]
        if lo <= (mhi + 1):
            merged[-1] = (mlo, max(mhi, hi))
        else:
            merged.append((lo, hi))
    return merged


def _complement_channel_ranges(excluded: list[tuple[int, int]], nchan: int) -> list[tuple[int, int]]:
    '''Return complement channel ranges for [0, nchan-1] after excluding merged ranges.'''
    if nchan <= 0:
        return []
    merged = _merge_channel_ranges(excluded, nchan)
    if not merged:
        return [(0, nchan - 1)]
    out: list[tuple[int, int]] = []
    cursor = 0
    for lo, hi in merged:
        if cursor < lo:
            out.append((cursor, lo - 1))
        cursor = hi + 1
    if cursor <= (nchan - 1):
        out.append((cursor, nchan - 1))
    return out


def _write_roi_dat_files(
    results: dict[str, Any],
    products_dir: str,
    roi_thresh: float,
    roi_cont_thresh: float,
) -> dict[str, str]:
    '''Write ROI.dat and ROIcont.dat in cont.dat-like format from source-aggregate products.'''
    os.makedirs(products_dir, exist_ok=True)
    roi_path = os.path.join(products_dir, 'ROI.dat')
    roi_cont_path = os.path.join(products_dir, 'ROIcont.dat')

    fields = results.get('products', {}).get('fields', {})
    inv_spw = results.get('inventory', {}).get('science_spws', {})

    with open(roi_path, 'w', encoding='ascii') as f_roi, open(roi_cont_path, 'w', encoding='ascii') as f_cont:
        for source_name in sorted(fields.keys()):
            spw_map = fields[source_name]
            wrote_source_roi = False
            wrote_source_cont = False

            roi_lines: list[tuple[int, list[str]]] = []
            cont_lines: list[tuple[int, list[str]]] = []

            for spw_key in sorted(spw_map.keys(), key=lambda x: int(x)):
                src_agg = spw_map[spw_key].get('source_aggregate', {})
                roi = src_agg.get('roi_detected') or {}
                identity = src_agg.get('identity') or {}
                spw_id = int(identity.get('spw_id', int(spw_key)))
                nchan = 0
                spectra = src_agg.get('spectra') or {}
                evidence = spectra.get('evidence')
                if evidence is not None:
                    nchan = int(np.asarray(evidence).size)

                if nchan <= 0:
                    continue
                pos_ranges = [(int(a), int(b)) for a, b in roi.get('line_ranges', [])]
                pos_peaks = [float(v) for v in roi.get('line_range_peakSNR', [])]
                neg_ranges = [(int(a), int(b)) for a, b in roi.get('neg_line_ranges', [])]
                neg_peaks = [float(v) for v in roi.get('neg_line_range_peakSNR', [])]

                roi_union_ranges: list[tuple[int, int]] = []
                for i in range(min(len(pos_ranges), len(pos_peaks))):
                    if abs(float(pos_peaks[i])) > float(roi_thresh):
                        roi_union_ranges.append(pos_ranges[i])
                for i in range(min(len(neg_ranges), len(neg_peaks))):
                    if abs(float(neg_peaks[i])) > float(roi_thresh):
                        roi_union_ranges.append(neg_ranges[i])

                cont_excluded_ranges: list[tuple[int, int]] = []
                for i in range(min(len(pos_ranges), len(pos_peaks))):
                    if abs(float(pos_peaks[i])) > float(roi_cont_thresh):
                        cont_excluded_ranges.append(pos_ranges[i])
                for i in range(min(len(neg_ranges), len(neg_peaks))):
                    if abs(float(neg_peaks[i])) > float(roi_cont_thresh):
                        cont_excluded_ranges.append(neg_ranges[i])

                channel_axis = src_agg.get('channel_axis') or {}
                outframe = str((src_agg.get('identity') or {}).get('outframe', channel_axis.get('outframe', 'LSRK')))
                chan_freqs_hz = channel_axis.get('chan_freqs_hz')
                if chan_freqs_hz is None:
                    if str(outframe).upper() != 'LSRK':
                        continue
                    spw_meta = inv_spw.get(str(spw_id), {})
                    ref_freq_hz = spw_meta.get('channel_axis', {}).get('ref_freq_hz')
                    chan_width_hz = spw_meta.get('channel_axis', {}).get('chan_width_hz')
                    if ref_freq_hz is None or chan_width_hz is None:
                        continue
                    idx = np.arange(nchan, dtype=np.float64)
                    chan_freqs_hz = float(ref_freq_hz) + (idx - 0.5 * (nchan - 1)) * float(chan_width_hz)
                else:
                    chan_freqs_hz = np.asarray(chan_freqs_hz, dtype=np.float64).ravel()
                if chan_freqs_hz.size != nchan:
                    continue

                keep_line_lines: list[str] = []
                if roi_union_ranges:
                    merged_roi = _merge_channel_ranges(roi_union_ranges, nchan=nchan)
                    roi_freq_ghz = _chan_ranges_to_frame_freq_ranges_ghz(merged_roi, chan_freqs_hz)
                    keep_line_lines = _fmt_frame_freq_ranges(roi_freq_ghz, outframe)
                if keep_line_lines:
                    roi_lines.append((spw_id, keep_line_lines))
                else:
                    roi_lines.append((spw_id, ['NONE']))

                if cont_excluded_ranges:
                    merged_excluded = _merge_channel_ranges(cont_excluded_ranges, nchan=nchan)
                else:
                    merged_excluded = []
                cont_ranges = _complement_channel_ranges(merged_excluded, nchan)
                cont_freq_ghz = _chan_ranges_to_frame_freq_ranges_ghz(cont_ranges, chan_freqs_hz)
                cont_freq_lines = _fmt_frame_freq_ranges(cont_freq_ghz, outframe)
                if cont_freq_lines:
                    cont_lines.append((spw_id, cont_freq_lines))

            if roi_lines:
                f_roi.write(f'Field: {source_name}\n\n')
                for spw_id, lines in roi_lines:
                    f_roi.write(f'SpectralWindow: {spw_id}\n')
                    for line in lines:
                        f_roi.write(f'{line}\n')
                    f_roi.write('\n')
                wrote_source_roi = True

            if cont_lines:
                f_cont.write(f'Field: {source_name}\n\n')
                for spw_id, lines in cont_lines:
                    f_cont.write(f'SpectralWindow: {spw_id}\n')
                    for line in lines:
                        f_cont.write(f'{line}\n')
                    f_cont.write('\n')
                wrote_source_cont = True

            if wrote_source_roi:
                f_roi.write('\n')
            if wrote_source_cont:
                f_cont.write('\n')

    return {
        'roi_dat': roi_path,
        'roi_cont_dat': roi_cont_path,
    }


def _prepare_regridded_ms(
    vis: str,
    spw_id: int,
    outframe: str,
    timebin_sec: float | None,
    tmp_root: str,
    tag: str,
    antenna: str | None = None,
    executor: Any | None = None,
    overwrite: bool = True,
) -> tuple[str, str, float, float]:
    '''Create outframe-regridded MS files.'''
    t_profile_total = time.perf_counter()
    is_ephem = str(outframe).upper() == 'SOURCE'
    bin_ms = os.path.join(tmp_root, f'tmp_{tag}_bin.ms')
    frame_token = 'geo' if is_ephem else str(outframe).lower()
    regridded_ms = os.path.join(tmp_root, f'tmp_{tag}_{frame_token}.ms')
    if overwrite:
        if os.path.exists(bin_ms):
            shutil.rmtree(bin_ms)
        if os.path.exists(regridded_ms):
            shutil.rmtree(regridded_ms)
    t0 = time.perf_counter()
    if is_ephem:
        job = casa_tasks.mstransform(
            vis=vis,
            outputvis=bin_ms,
            datacolumn='DATA',
            timeaverage=True,
            timebin='10.0s',
            spw=str(spw_id),
            antenna=antenna,
            keepflags=False,
        )
        if executor is None:
            job.execute()
        else:
            executor.execute(job)
        bin_source = bin_ms
        bin_ms_out = bin_ms
        t1 = time.perf_counter()
        job = casa_tasks.mstransform(
            vis=bin_source,
            outputvis=regridded_ms,
            datacolumn='DATA',
            regridms=True,
            outframe='GEO',
            keepflags=False,
        )
        if executor is None:
            job.execute()
        else:
            executor.execute(job)
    else:
        if timebin_sec is None:
            bin_source = vis
            bin_ms_out = vis
            t1 = t0
        else:
            job = casa_tasks.mstransform(
                vis=vis,
                outputvis=bin_ms,
                datacolumn='DATA',
                timeaverage=True,
                timebin=f'{float(timebin_sec)}s',
                spw=str(spw_id),
                antenna=antenna,
                keepflags=False,
            )
            if executor is None:
                job.execute()
            else:
                executor.execute(job)
            bin_source = bin_ms
            bin_ms_out = bin_ms
            t1 = time.perf_counter()
        kwargs = dict(
            vis=bin_source,
            outputvis=regridded_ms,
            datacolumn='DATA',
            regridms=True,
            outframe=str(outframe),
            keepflags=False,
        )
        if timebin_sec is None:
            kwargs['spw'] = str(spw_id)
            kwargs['antenna'] = antenna
        job = casa_tasks.mstransform(**kwargs)
        if executor is None:
            job.execute()
        else:
            executor.execute(job)
    t2 = time.perf_counter()
    _profile_logf(tmp_root, 'prepare_regridded_ms tag=%s spw_id=%s outframe=%s timebin=%s dt_bin=%.3f dt_regrid=%.3f dt_total=%.3f', tag, spw_id, outframe, str(timebin_sec), (t1 - t0), (t2 - t1), (t2 - t_profile_total))
    return bin_ms_out, regridded_ms, (t1 - t0), (t2 - t1)


def _read_regridded_field(
    regridded_ms: str,
    field_id: int,
    datacolumn: str = 'DATA',
) -> dict[str, np.ndarray] | None:
    '''Read a single field from a regridded MS and return visibility blocks.'''
    out = _read_regridded_fields(regridded_ms, [field_id], datacolumn=datacolumn)
    return out.get(int(field_id))


def _read_regridded_fields(
    regridded_ms: str,
    field_ids: list[int],
    datacolumn: str = 'DATA',
) -> dict[int, dict[str, np.ndarray]]:
    '''Read multiple fields from one regridded MS in a single table query.'''
    # Record bulk table-read timings when profiling is enabled.
    t_profile_total = time.perf_counter()
    want = sorted({int(v) for v in field_ids})
    if not want:
        return {}
    tb_obj = _get_tb()
    tb_obj.open(regridded_ms)
    field_expr = ' || '.join(f'FIELD_ID=={fid}' for fid in want)
    sub = tb_obj.query(f'DATA_DESC_ID==0 && ({field_expr})')
    nrows = sub.nrows()
    if nrows == 0:
        sub.close()
        tb_obj.close()
        return {}

    data = sub.getcol(datacolumn)
    data = _ensure_row_chan_pol(data, nrows)
    v = np.mean(data, axis=2).astype(np.complex64, copy=False)

    colnames = sub.colnames()
    if 'SIGMA' in colnames:
        sig = np.asarray(sub.getcol('SIGMA'))
        if sig.ndim == 2 and sig.shape[0] != nrows and sig.shape[1] == nrows:
            sig = sig.T
        sig_r = np.mean(sig, axis=1)
        w_r = (1.0 / np.maximum(sig_r, 1e-30) ** 2).astype(np.float64)
    elif 'WEIGHT' in colnames:
        wt = np.asarray(sub.getcol('WEIGHT'))
        if wt.ndim == 2 and wt.shape[0] != nrows and wt.shape[1] == nrows:
            wt = wt.T
        w_r = np.maximum(np.mean(wt, axis=1), 0.0).astype(np.float64)
    else:
        w_r = np.ones((nrows,), dtype=np.float64)

    uvw = np.asarray(sub.getcol('UVW'), dtype=np.float64)
    if uvw.shape == (3, nrows):
        uvw = uvw.T
    u_m = uvw[:, 0]
    v_m = uvw[:, 1]
    times = np.asarray(sub.getcol('TIME'), dtype=np.float64).ravel()
    field_col = np.asarray(sub.getcol('FIELD_ID'), dtype=np.int64).ravel()

    sub.close()
    tb_obj.close()

    good = w_r > 0
    v = v[good]
    w_r = w_r[good]
    u_m = u_m[good]
    v_m = v_m[good]
    times = times[good]
    field_col = field_col[good]

    out: dict[int, dict[str, np.ndarray]] = {}
    for fid in want:
        m = field_col == int(fid)
        if not np.any(m):
            continue
        out[int(fid)] = {
            'V': v[m],
            'W': w_r[m],
            'U_m': u_m[m],
            'V_m': v_m[m],
            'TIME': times[m],
        }
    _profile_logf(os.path.dirname(regridded_ms), 'read_regridded_fields ms=%s n_fields=%s nrows=%s dt_total=%.3f', os.path.basename(regridded_ms), len(out), int(v.shape[0]), (time.perf_counter() - t_profile_total))
    return out


def _concat_preloaded(chunks: list[dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    '''Concatenate preloaded visibility chunks.'''
    # Record concatenation timing when profiling is enabled.
    t_profile_total = time.perf_counter()
    v = np.concatenate([c['V'] for c in chunks], axis=0)
    w = np.concatenate([c['W'] for c in chunks], axis=0)
    u_m = np.concatenate([c['U_m'] for c in chunks], axis=0)
    v_m = np.concatenate([c['V_m'] for c in chunks], axis=0)
    t = np.concatenate([c['TIME'] for c in chunks], axis=0)
    out = {'V': v, 'W': w, 'U_m': u_m, 'V_m': v_m, 'TIME': t}
    _profile_logf(None, 'concat_preloaded nchunks=%s nrows=%s dt_total=%.3f', len(chunks), int(v.shape[0]), (time.perf_counter() - t_profile_total))
    return out


def _mini_findcont_with_fwhm(
    evid: np.ndarray,
    fwhm_chan: int,
    thr: float = 5.0,
    bin_scales: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 8, 10),
    direction: str = 'positive',
    noise_mask: np.ndarray | None = None,
    use_neff_scaling: bool = True,
    n_eff_maxlag: int = 64,
) -> dict[str, Any]:
    '''Compute line and continuum ranges using multi-scale evidence thresholds.'''
    evid = np.asarray(evid, dtype=np.float64)
    nchan = evid.size
    fwhm = max(int(round(fwhm_chan)), 1)
    dilation_half_width = max(2 * fwhm, 1)
    direction_norm = str(direction).strip().lower()
    if direction_norm not in ('positive', 'negative'):
        direction_norm = 'positive'
    evidence_use = evid if direction_norm == 'positive' else -evid
    rho = _estimate_noise_autocorr(evidence_use, noise_mask=noise_mask, maxlag=n_eff_maxlag)

    seed = np.zeros(nchan, dtype=bool)
    peak_snr = np.full(nchan, -np.inf, dtype=np.float64)
    used_bin_scales: list[int] = []
    used_n_eff: list[float] = []
    for nbin in bin_scales:
        nbin = int(nbin)
        if nbin < 1:
            continue
        # Do not smooth on scales broader than the inferred linewidth.
        if nbin > fwhm:
            continue
        used_bin_scales.append(nbin)
        kernel = np.ones(nbin, dtype=np.float64) / float(nbin)
        conv = np.convolve(evidence_use, kernel, mode='same')
        n_eff = float(nbin)
        if use_neff_scaling:
            n_eff = _effective_nbin_from_rho(nbin, rho)
        used_n_eff.append(float(n_eff))
        conv *= np.sqrt(max(1.0, float(n_eff)))
        peak_snr = np.maximum(peak_snr, conv)
        peaks = np.where(conv > thr)[0]
        seed[peaks] = True

    line_mask = np.zeros(nchan, dtype=bool)
    for i in np.where(seed)[0]:
        lo = max(0, i - dilation_half_width)
        hi = min(nchan - 1, i + dilation_half_width)
        line_mask[lo:hi + 1] = True

    cont_mask = ~line_mask
    cont_ranges = _mask_to_ranges(cont_mask)
    for a, b in cont_ranges:
        if (b - a + 1) < fwhm:
            line_mask[a:b + 1] = True
    cont_mask = ~line_mask

    line_ranges = _mask_to_ranges(line_mask)
    line_peak_snr = []
    for a, b in line_ranges:
        seg = peak_snr[a:b + 1]
        line_peak_snr.append(float(np.nanmax(seg)) if seg.size else float('nan'))

    return {
        'thr': float(thr),
        'bin_scales': tuple(int(v) for v in used_bin_scales),
        'n_eff_per_scale': tuple(float(v) for v in used_n_eff),
        'direction': direction_norm,
        'fwhm_chan': int(fwhm),
        'seed_count': int(np.sum(seed)),
        'line_mask': line_mask,
        'cont_mask': cont_mask,
        'line_ranges': line_ranges,
        'line_range_peakSNR': line_peak_snr,
        'cont_ranges': _mask_to_ranges(cont_mask),
    }


def _evidence_noise_mask(
    ref_mask: np.ndarray | None,
    mw_mask: np.ndarray | None,
    use_mw: bool,
    nchan: int,
) -> np.ndarray:
    '''Build one evidence-noise mask from reference and moment0 noise masks.'''
    if ref_mask is None:
        ref_use = np.ones((nchan,), dtype=bool)
    else:
        ref_use = np.asarray(ref_mask, dtype=bool).ravel()[:nchan]
        if ref_use.size != nchan:
            ref_use = np.resize(ref_use, nchan)
    if not use_mw:
        return ref_use
    if mw_mask is None:
        mw_use = np.ones((nchan,), dtype=bool)
    else:
        mw_use = np.asarray(mw_mask, dtype=bool).ravel()[:nchan]
        if mw_use.size != nchan:
            mw_use = np.resize(mw_use, nchan)
    both = ref_use & mw_use
    if np.count_nonzero(both) >= 16:
        return both
    either = ref_use | mw_use
    if np.count_nonzero(either) >= 16:
        return either
    return ref_use


def _combine_evidence_safely(
    ref_snr: np.ndarray,
    mw_snr: np.ndarray,
    use_mw: bool,
    negative: bool = False,
) -> np.ndarray:
    '''Combine spectra into a finite evidence array.'''
    ref = np.asarray(ref_snr, dtype=np.float64)
    mw = np.asarray(mw_snr, dtype=np.float64)
    a = -ref if negative else ref
    b = -mw if negative else mw
    if use_mw:
        out = np.nanmax(np.vstack([a, b]), axis=0)
    else:
        out = np.asarray(a, dtype=np.float64)
    out = np.asarray(out, dtype=np.float64)
    out[~np.isfinite(out)] = 0.0
    return out


def _empty_mini_with_continuum(
    nchan: int,
    thr: float,
    neg_thr: float,
    fwhm_chan: int,
    fwhm_kms: float,
    dv_kms: float,
    reason: str,
) -> dict[str, Any]:
    '''Build an empty ROI result that still preserves full continuum coverage.'''
    cont_ranges = [(0, int(nchan) - 1)] if int(nchan) > 0 else []
    return {
        'thr': float(thr),
        'neg_threshold_snr': float(neg_thr),
        'bin_scales': (),
        'fwhm_chan': int(max(1, fwhm_chan)),
        'fwhm_kms': float(fwhm_kms) if np.isfinite(fwhm_kms) else float('nan'),
        'dv_kms': float(dv_kms) if np.isfinite(dv_kms) else float('nan'),
        'line_ranges': [],
        'line_range_peakSNR': [],
        'neg_line_ranges': [],
        'neg_line_range_peakSNR': [],
        'cont_ranges': cont_ranges,
        'reference_zero_fraction': float('nan'),
        'moment0_zero_fraction': float('nan'),
        'reference_smoothed': False,
        'moment0_smoothed': False,
        'moment0_rejected_zero_fraction': False,
        'moment0_rejected_negative_extent': False,
        'mom0_usage_mode': 'used',
        'negative_extent_delta_sigma': float('nan'),
        'renorm_ratio_reference': 1.0,
        'renorm_ratio_moment0': 1.0,
        'fwhm_selection_mode': 'default_4chan',
        'linewidth_fallback_level': 'default_4chan',
        'fwhm_global_fallback_triggered': False,
        'snr_failed_reference': False,
        'snr_failed_moment0': False,
        'snr_failed_both': False,
        'evidence_valid_fraction': 0.0,
        'roi_skipped_reason': str(reason),
        'decision_trace': {'roi_skipped': True, 'reason': str(reason)},
    }


def _run_final_roi_detection(
    ref_snr: np.ndarray,
    mw_snr: np.ndarray,
    ref_noise_mask: np.ndarray | None,
    mw_noise_mask: np.ndarray | None,
    diag: dict[str, Any],
    fwhm_chan: int,
    pos_thr: float,
    neg_thr: float,
    bin_scales: tuple[int, ...],
    rolling_rms_window: int,
    rolling_rms_target_unsmoothed: float,
    rolling_rms_target_smoothed: float,
    neg_extent_delta_thr: float,
    neg_extent_trim_frac: float,
) -> dict[str, Any]:
    '''Run two-pass ROI detection with ratio renormalization and final ROI products.'''
    # Record ROI-pass timing when profiling is enabled.
    t_profile_total = time.perf_counter()
    ref_snr_use = np.asarray(ref_snr, dtype=np.float64)
    mw_snr_use = np.asarray(mw_snr, dtype=np.float64)
    nchan = min(ref_snr_use.size, mw_snr_use.size)
    ref_snr_use = ref_snr_use[:nchan]
    mw_snr_use = mw_snr_use[:nchan]
    snr_failed_reference = bool(np.count_nonzero(np.isfinite(ref_snr_use)) == 0)
    snr_failed_moment0 = bool(np.count_nonzero(np.isfinite(mw_snr_use)) == 0)
    snr_failed_both = bool(snr_failed_reference and snr_failed_moment0)
    ref_snr_use = np.nan_to_num(ref_snr_use, nan=0.0, posinf=0.0, neginf=0.0)
    mw_snr_use = np.nan_to_num(mw_snr_use, nan=0.0, posinf=0.0, neginf=0.0)

    drop_zero = bool(diag.get('moment0_rejected_zero_fraction', False))
    use_mw_neg = not bool(drop_zero)

    t_neg1 = time.perf_counter()
    mask_neg_pass1 = _evidence_noise_mask(ref_noise_mask, mw_noise_mask, use_mw=use_mw_neg, nchan=nchan)
    evidence_neg_pass1 = _combine_evidence_safely(ref_snr_use, mw_snr_use, use_mw=use_mw_neg, negative=True)
    neg_mini_p1 = _mini_findcont_with_fwhm(
        evidence_neg_pass1,
        fwhm_chan=fwhm_chan,
        thr=neg_thr,
        bin_scales=bin_scales,
        direction='positive',
        noise_mask=mask_neg_pass1,
        use_neff_scaling=True,
    )

    dt_neg1 = time.perf_counter() - t_neg1
    neg_delta = _negative_extent_delta_trimmed(ref_snr_use, mw_snr_use, trim_frac=neg_extent_trim_frac)
    drop_neg = bool((not drop_zero) and (neg_delta > float(neg_extent_delta_thr)))
    use_mw_pos = not bool(drop_zero or drop_neg)

    t_pos1 = time.perf_counter()
    mask_pos_pass1 = _evidence_noise_mask(ref_noise_mask, mw_noise_mask, use_mw=use_mw_pos, nchan=nchan)
    evidence_pos_pass1 = _combine_evidence_safely(ref_snr_use, mw_snr_use, use_mw=use_mw_pos, negative=False)
    pos_mini_p1 = _mini_findcont_with_fwhm(
        evidence_pos_pass1,
        fwhm_chan=fwhm_chan,
        thr=pos_thr,
        bin_scales=bin_scales,
        direction='positive',
        noise_mask=mask_pos_pass1,
        use_neff_scaling=True,
    )

    dt_pos1 = time.perf_counter() - t_pos1
    t_renorm = time.perf_counter()
    excluded = _merge_channel_ranges(
        list(pos_mini_p1.get('line_ranges', [])) + list(neg_mini_p1.get('line_ranges', [])),
        nchan=nchan,
    )
    ref_rms_spec = _rolling_rms_spectrum(ref_snr_use, window=rolling_rms_window)
    mw_rms_spec = _rolling_rms_spectrum(mw_snr_use, window=rolling_rms_window)
    ref_rms_med = _rolling_rms_median_excluding_ranges(ref_snr_use, excluded, window=rolling_rms_window)
    mw_rms_med = _rolling_rms_median_excluding_ranges(mw_snr_use, excluded, window=rolling_rms_window)

    ref_target = float(rolling_rms_target_smoothed if diag.get('reference_smoothed') else rolling_rms_target_unsmoothed)
    mw_target = float(rolling_rms_target_smoothed if diag.get('moment0_smoothed') else rolling_rms_target_unsmoothed)
    if (not np.isfinite(ref_target)) or ref_target <= 0.0:
        ref_target = 1.0
    if (not np.isfinite(mw_target)) or mw_target <= 0.0:
        mw_target = 1.0
    ref_ratio = float(ref_rms_med / ref_target) if np.isfinite(ref_rms_med) and ref_rms_med > 0.0 else 1.0
    mw_ratio = float(mw_rms_med / mw_target) if np.isfinite(mw_rms_med) and mw_rms_med > 0.0 else 1.0
    ref_ratio = float(max(ref_ratio, 1.0e-6))
    mw_ratio = float(max(mw_ratio, 1.0e-6))

    ref_snr_final = ref_snr_use / ref_ratio
    mw_snr_final = mw_snr_use / mw_ratio
    ref_snr_final = np.nan_to_num(ref_snr_final, nan=0.0, posinf=0.0, neginf=0.0)
    mw_snr_final = np.nan_to_num(mw_snr_final, nan=0.0, posinf=0.0, neginf=0.0)

    dt_renorm = time.perf_counter() - t_renorm
    use_mw_neg_final = not bool(drop_zero)

    t_neg2 = time.perf_counter()
    mask_neg_pass2 = _evidence_noise_mask(ref_noise_mask, mw_noise_mask, use_mw=use_mw_neg_final, nchan=nchan)
    evidence_neg_final = _combine_evidence_safely(ref_snr_final, mw_snr_final, use_mw=use_mw_neg_final, negative=True)
    neg_mini = _mini_findcont_with_fwhm(
        evidence_neg_final,
        fwhm_chan=fwhm_chan,
        thr=neg_thr,
        bin_scales=bin_scales,
        direction='positive',
        noise_mask=mask_neg_pass2,
        use_neff_scaling=True,
    )

    dt_neg2 = time.perf_counter() - t_neg2
    neg_delta_final = _negative_extent_delta_trimmed(ref_snr_final, mw_snr_final, trim_frac=neg_extent_trim_frac)
    drop_neg_final = bool((not drop_zero) and (neg_delta_final > float(neg_extent_delta_thr)))
    use_mw_pos_final = not bool(drop_zero or drop_neg_final)

    t_pos2 = time.perf_counter()
    mask_pos_pass2 = _evidence_noise_mask(ref_noise_mask, mw_noise_mask, use_mw=use_mw_pos_final, nchan=nchan)
    evidence_pos_final = _combine_evidence_safely(ref_snr_final, mw_snr_final, use_mw=use_mw_pos_final, negative=False)
    pos_mini = _mini_findcont_with_fwhm(
        evidence_pos_final,
        fwhm_chan=fwhm_chan,
        thr=pos_thr,
        bin_scales=bin_scales,
        direction='positive',
        noise_mask=mask_pos_pass2,
        use_neff_scaling=True,
    )
    union_final = _merge_channel_ranges(
        list(pos_mini.get('line_ranges', [])) + list(neg_mini.get('line_ranges', [])),
        nchan=nchan,
    )
    union_mask = np.zeros((nchan,), dtype=bool)
    for lo, hi in union_final:
        a = max(0, min(int(lo), nchan - 1))
        b = max(0, min(int(hi), nchan - 1))
        if b < a:
            a, b = b, a
        union_mask[a:b + 1] = True

    dt_pos2 = time.perf_counter() - t_pos2
    _profile_logf(None, 'run_final_roi_detection nchan=%s neg1=%.3f pos1=%.3f renorm=%.3f neg2=%.3f pos2=%.3f total=%.3f', nchan, dt_neg1, dt_pos1, dt_renorm, dt_neg2, dt_pos2, (time.perf_counter() - t_profile_total))
    return {
        'reference_sum_snr': ref_snr_final,
        'moment0_weighted_sum_snr': mw_snr_final,
        'evidence': evidence_pos_final,
        'evidence_negative': evidence_neg_final,
        'reference_rms_spectrum': ref_rms_spec,
        'moment0_rms_spectrum': mw_rms_spec,
        'roi_union_mask': union_mask,
        'mini_pos': pos_mini,
        'mini_neg': neg_mini,
        'diagnostics': {
            'reference_noise_median_rms': float(ref_rms_med) if np.isfinite(ref_rms_med) else np.nan,
            'moment0_noise_median_rms': float(mw_rms_med) if np.isfinite(mw_rms_med) else np.nan,
            'reference_noise_rms_target': float(ref_target),
            'moment0_noise_rms_target': float(mw_target),
            'renorm_ratio_reference': float(ref_ratio),
            'renorm_ratio_moment0': float(mw_ratio),
            'moment0_rejected_negative_extent': bool(drop_neg_final),
            'moment0_rejected_final': bool(drop_zero or drop_neg_final),
            'negative_extent_delta_sigma': float(neg_delta_final),
            'moment0_rejected_zero_fraction': bool(drop_zero),
            'snr_failed_reference': bool(snr_failed_reference),
            'snr_failed_moment0': bool(snr_failed_moment0),
            'snr_failed_both': bool(snr_failed_both),
            'evidence_valid_fraction': float(np.mean(np.isfinite(evidence_pos_final))) if nchan > 0 else 0.0,
            'roi_skipped_reason': 'none',
            'mom0_usage_mode': 'rejected_zero_fraction' if drop_zero else (
                'rejected_negative_extent' if drop_neg_final else 'used'
            ),
            'decision_trace': {
                'zero_fraction_rejection': bool(drop_zero),
                'negative_roi_computed': True,
                'negative_extent_qc_rejection': bool(drop_neg_final),
                'positive_roi_computed': True,
                'ratio_renormalization_applied': True,
            },
        },
    }


def _process_spw(
    vis_list: list[str],
    ddid: int,
    spw_name: str,
    spw_ids_by_vis: dict[str, int] | None,
    fallback_spw_id: int,
    field_groups: dict[int, list[int]],
    antenna_selections_by_vis: dict[str, str] | None = None,
    source_names_by_id: dict[int, str] | None = None,
    field_names_by_id: dict[int, str] | None = None,
    common_geometry_plan: dict[int, dict[str, Any]] | None = None,
    source_outframe: dict[int, str] | None = None,
    field_phase_centers: dict[int, tuple[float, float]] | None = None,
    field_ephemeris_paths: dict[int, str] | None = None,
    products_dir: str | None = None,
    dish_diameter_m: float = 12.0,
    timebin_sec: float = 240,
    npix: int = 256,
    fov_pb_mult: float = 1.5,
    ref_sigma: float = 3.0,
    mom0_thresh_sigma: float = 5.0,
    gate_sigma: float = 1.0,
    ref_zero_frac_thr: float = 0.05,
    mom0_zero_frac_thr: float = 0.05,
    ref_smooth_width: int = 4,
    mom0_smooth_width: int = 4,
    neg_extent_delta_thr: float = 5.0,
    neg_extent_trim_frac: float = 0.10,
    tmp_dir: str = 'tmp_findroi',
    tmp_overwrite: bool = True,
    verbose: bool = True,
    save_moment0: bool = True,
    save_cube: bool = False,
    uv_taper_auto: bool = True,
    uv_taper_sigma_uv: float | None = None,
    uv_taper_fwhm_cell: float = 2.0,
    executor: Any | None = None,
) -> dict[str, Any]:
    '''Process one SPW and return per-field spectra and evidence.'''
    t_all = time.perf_counter()
    rank, size = _mpi_rank_size()
    _set_profile_default_dir(tmp_dir)
    _rank_logf(tmp_dir, '[rank %s/%s] start spw=%s ddid=%s', rank, size, spw_name, ddid)
    vis0 = vis_list[0]
    spw_id = int(spw_ids_by_vis.get(vis0, spw_ids_by_vis.get(os.path.basename(os.path.normpath(vis0)), fallback_spw_id))) if spw_ids_by_vis else int(fallback_spw_id)
    tag = f'spw{spw_id}'

    # Record one full SPW-processing timing bundle when profiling is enabled.
    _profile_logf(tmp_dir, 'process_spw start spw=%s ddid=%s n_vis=%s n_sources=%s', spw_name, ddid, len(vis_list), len(field_groups))
    spectra_by_source = {sid: {} for sid in field_groups.keys()}
    source_is_mosaic = {int(source_id): (len(field_ids) > 1) for source_id, field_ids in field_groups.items()}
    source_outframe = {int(k): str(v) for k, v in (source_outframe or {}).items()}
    if not source_outframe:
        raise RuntimeError('hif_findroi requires source outframe metadata from pipeline context.')
    field_phase_centers = dict(field_phase_centers or {})
    if not field_phase_centers:
        raise RuntimeError('hif_findroi requires field phase-center metadata from pipeline context.')
    source_names_by_id = {int(k): str(v) for k, v in (source_names_by_id or {}).items()}
    field_names_by_id = {int(k): str(v) for k, v in (field_names_by_id or {}).items()}
    field_ephemeris_paths = {int(k): str(v) for k, v in (field_ephemeris_paths or {}).items()}
    source_stitch_meta: dict[int, dict[str, Any]] = {}
    source_stitch_states: dict[int, dict[str, Any]] = {}
    source_regridded_ms_paths: dict[int, list[str]] = {int(source_id): [] for source_id in field_groups.keys()}
    common_geometry_plan = {int(k): dict(v) for k, v in (common_geometry_plan or {}).items()}
    mstransform_bin_s = 0.0
    mstransform_regrid_s = 0.0
    mstransform_calls = 0
    antenna_selections_by_vis = dict(antenna_selections_by_vis or {})

    for eb_idx, vis in enumerate(vis_list):
        ms_cache: dict[tuple[str, int | None], tuple[str, float, float]] = {}
        real_spw_id = int(spw_ids_by_vis.get(vis, spw_ids_by_vis.get(os.path.basename(os.path.normpath(vis)), spw_id))) if spw_ids_by_vis else int(spw_id)
        antenna_selection = antenna_selections_by_vis.get(vis)
        if antenna_selection is None:
            raise RuntimeError(f'No antenna selection found for hif_findroi vis={vis}.')
        for source_id, fids in field_groups.items():
            outframe = str(source_outframe.get(int(source_id), 'LSRK'))
            cache_key = (outframe, None if outframe == 'LSRK' else int(source_id))
            if cache_key not in ms_cache:
                frame_tag = f'{tag}_eb{eb_idx}' if outframe == 'LSRK' else f'{tag}_src{int(source_id)}_eb{eb_idx}'
                _, regridded_ms, dt_bin, dt_regrid = _prepare_regridded_ms(
                    vis,
                    real_spw_id,
                    outframe,
                    timebin_sec,
                    tmp_dir,
                    frame_tag,
                    antenna=antenna_selection,
                    executor=executor,
                    overwrite=tmp_overwrite,
                )
                ms_cache[cache_key] = (regridded_ms, float(dt_bin), float(dt_regrid))
                source_regridded_ms_paths.setdefault(int(source_id), []).append(str(regridded_ms))
                if verbose:
                    _rank_logf(
                        tmp_dir,
                        '[mstransform] spw=%s eb=%s source=%s outframe=%s bin_dt=%.2fs regrid_dt=%.2fs',
                        spw_name,
                        eb_idx,
                        source_id,
                        ('GEO' if outframe == 'SOURCE' else outframe),
                        dt_bin,
                        dt_regrid,
                    )
                mstransform_bin_s += float(dt_bin)
                mstransform_regrid_s += float(dt_regrid)
                mstransform_calls += 1
            else:
                regridded_ms, _, _ = ms_cache[cache_key]
                source_regridded_ms_paths.setdefault(int(source_id), []).append(str(regridded_ms))
            t_read_fields = time.perf_counter()
            chunks_by_field = _read_regridded_fields(regridded_ms, fids)
            _profile_logf(tmp_dir, 'process_spw bulk_read spw=%s eb=%s source=%s n_fields=%s dt=%.3f', spw_name, eb_idx, source_id, len(fids), (time.perf_counter() - t_read_fields))
            for field_id, chunk in chunks_by_field.items():
                spectra_by_source[source_id].setdefault(field_id, []).append(chunk)

    results = {'spw_id': spw_id, 'spw_name': spw_name, 'sources': {}}

    for source_id, field_chunks in spectra_by_source.items():
        results['sources'].setdefault(source_id, {})
        outframe = str(source_outframe.get(int(source_id), 'LSRK'))
        regrid_outframe = 'GEO' if outframe == 'SOURCE' else outframe
        frame_tag = f'{tag}_eb0' if outframe == 'LSRK' else f'{tag}_src{int(source_id)}_eb0'
        frame_token = regrid_outframe.lower()
        geometry_plan = common_geometry_plan.get(int(source_id), {})
        chan_freqs_hz = None
        chan_freqs_geo_hz = None
        ref_freq_hz = None
        chan_width_hz = None
        axis_field_id = int(sorted(field_chunks.keys())[0]) if field_chunks else None
        source_axis_diag = None
        try:
            freqs = _get_temp_ms_chan_freqs_hz(os.path.join(tmp_dir, f'tmp_{frame_tag}_{frame_token}.ms'), ddid=0)
            chan_freqs_geo_hz = np.asarray(freqs, dtype=np.float64).ravel()
            if outframe == 'SOURCE':
                if axis_field_id is None:
                    raise RuntimeError('No field available to build ephemeris SOURCE axis')
                axis_preloaded = _concat_preloaded(field_chunks[axis_field_id])
                chan_freqs_hz, source_axis_diag = _build_ephemeris_source_axis_hz(
                    vis0,
                    axis_field_id,
                    axis_preloaded['TIME'],
                    chan_freqs_geo_hz,
                    ephem_path=field_ephemeris_paths.get(int(axis_field_id)),
                )
            else:
                chan_freqs_hz = chan_freqs_geo_hz.copy()
            ref_freq_hz = float(np.median(chan_freqs_hz))
            df = np.diff(chan_freqs_hz)
            chan_width_hz = float(np.median(df)) if df.size else None
        except Exception as exc:
            _rank_logf(tmp_dir, '[warn] failed to build output-frame channel metadata for spw=%s ddid=%s source=%s: %s', spw_name, ddid, source_id, exc)
            chan_freqs_hz = None
            chan_freqs_geo_hz = None
            ref_freq_hz = None
            chan_width_hz = None
        is_mosaic_source = bool(source_is_mosaic.get(int(source_id), False))
        template_artifacts: dict[str, str] = {}
        for field_id, chunks in field_chunks.items():
            t_field = time.perf_counter()
            t_concat = time.perf_counter()
            d_preload = _concat_preloaded(chunks)
            _profile_logf(tmp_dir, 'process_spw concat spw=%s source=%s field=%s n_chunks=%s nrows=%s dt=%.3f', spw_name, source_id, field_id, len(chunks), int(d_preload['V'].shape[0]), (time.perf_counter() - t_concat))
            if ref_freq_hz is None or chan_width_hz is None:
                _rank_logf(
                    tmp_dir,
                    '[warn] missing output-frame channel metadata for spw=%s ddid=%s; skipping source=%s field=%s',
                    spw_name,
                    ddid,
                    source_id,
                    field_id,
                )
                continue
            ephem_diag = None
            if outframe == 'SOURCE':
                d_preload, ephem_diag = _apply_ephemeris_geo_to_source_correction(
                    d_preload,
                    vis0,
                    int(field_id),
                    int(spw_id),
                    chan_freqs_geo_hz,
                    chan_freqs_hz,
                    log_dir=tmp_dir,
                    ephem_path=field_ephemeris_paths.get(int(field_id)),
                )
            d_preload['ref_freq_hz'] = ref_freq_hz
            d_preload['lam'] = casa_tools.quanta.getvalue(
                casa_tools.quanta.convert(casa_tools.quanta.constants('c'), 'm/s')
            )[0] / ref_freq_hz
            source_label = source_names_by_id.get(int(source_id), f'source_{int(source_id)}')
            source_token = _sanitize_token(source_label)
            field_label = field_names_by_id.get(int(field_id), f'field_{int(field_id)}')
            field_token = _sanitize_token(field_label)

            save_moment0_path = None
            if save_moment0 and (not is_mosaic_source):
                base = f'moment0_source-{source_token}_field-{field_token}_spw-{spw_id}.npy'
                save_moment0_path = os.path.join(products_dir if products_dir else (tmp_dir if tmp_dir else '.'), base)

            save_cube_path = None
            if save_cube and (not is_mosaic_source):
                base = f'cube_source-{source_token}_field-{field_token}_spw-{spw_id}.npy'
                save_cube_path = os.path.join(products_dir if products_dir else (tmp_dir if tmp_dir else '.'), base)

            res = cube_threshold_spectrum(
                vis0,
                dish_diameter_m=dish_diameter_m,
                ddid=ddid,
                spw_name=spw_name,
                field=field_id,
                timebin_sec=timebin_sec,
                npix=int(geometry_plan.get('field_npix', npix)),
                fov_pb_mult=fov_pb_mult,
                ref_sigma=ref_sigma,
                mom0_thresh_sigma=mom0_thresh_sigma,
                gate_sigma=gate_sigma,
                ref_zero_frac_thr=ref_zero_frac_thr,
                mom0_zero_frac_thr=mom0_zero_frac_thr,
                ref_smooth_width=ref_smooth_width,
                mom0_smooth_width=mom0_smooth_width,
                neg_extent_delta_thr=neg_extent_delta_thr,
                neg_extent_trim_frac=neg_extent_trim_frac,
                verbose=False,
                save_cube_path=save_cube_path,
                save_moment0_path=save_moment0_path,
                compute_moment0_weighted_spectrum=True,
                compute_products=(not is_mosaic_source),
                preloaded=d_preload,
                uv_taper_auto=uv_taper_auto,
                uv_taper_sigma_uv=uv_taper_sigma_uv,
                uv_taper_fwhm_cell=uv_taper_fwhm_cell,
                cell_arcsec_override=float(geometry_plan.get('cell_arcsec')) if geometry_plan else None,
                return_cube=is_mosaic_source,
                log_dir=tmp_dir,
            )

            field_total_s = time.perf_counter() - t_field
            timing = res.get('timing', {})
            imaging_s = float(timing.get('grid_precompute_s', 0.0)) + float(timing.get('cube_imaging_s', 0.0))
            processing_s = float(timing.get('product_compute_s', 0.0))

            if verbose:
                _rank_logf(
                    tmp_dir,
                    '[field] spw=%s source=%s field=%s imaging=%.2fs processing=%.2fs total=%.2fs',
                    spw_name,
                    source_id,
                    field_id,
                    imaging_s,
                    processing_s,
                    field_total_s,
                )
            field_grid_meta = copy.deepcopy(res.get('grid_meta', {}))
            _rank_diagf(
                tmp_dir,
                'field spw=%s source=%s field=%s drop_frac=%.6f grid_weight_sum=%.6e grid_weight_sum_conj=%.6e',
                spw_name,
                source_id,
                field_id,
                float(field_grid_meta.get('drop_frac', np.nan)),
                float(field_grid_meta.get('grid_weight_sum', np.nan)),
                float(field_grid_meta.get('grid_weight_sum_conj', np.nan)),
            )

            if not is_mosaic_source:
                results['sources'][source_id][field_id] = {
                    'reference_sum_raw': res['spectrum'].astype(np.float32, copy=False),
                    'moment0': res['moment0'].astype(np.float32, copy=False),
                    'moment0_weighted_sum_raw': res['moment0_weighted_spectrum'].astype(np.float32, copy=False),
                    'reference_sum_raw_processed': res['reference_sum_raw_processed'].astype(np.float32, copy=False),
                    'moment0_weighted_sum_raw_processed': res['moment0_weighted_sum_raw_processed'].astype(np.float32, copy=False),
                    'reference_sum_snr': res['reference_sum_snr'].astype(np.float32, copy=False),
                    'moment0_weighted_sum_snr': res['moment0_weighted_sum_snr'].astype(np.float32, copy=False),
                    'evidence': res['evidence'].astype(np.float32, copy=False),
                    'sigma': res['sigma'].astype(np.float32, copy=False),
                    'outframe': outframe,
                    'chan_freqs_hz': chan_freqs_hz,
                    'ref_freq_hz': float(ref_freq_hz),
                    'chan_width_hz': float(chan_width_hz) if chan_width_hz is not None else None,
                    'pb_fwhm_arcsec': float(res.get('pb_fwhm_arcsec', np.nan)),
                    'grid_meta': field_grid_meta,
                    'spectra_qc': copy.deepcopy(res.get('spectra_qc', {})),
                    'ephemeris_meta': {
                        'correction': copy.deepcopy(ephem_diag) if ephem_diag is not None else None,
                        'source_axis': copy.deepcopy(source_axis_diag) if source_axis_diag is not None else None,
                    } if (ephem_diag is not None or source_axis_diag is not None) else None,
                    'reference_sum_noise_mask': res.get('reference_sum_noise_mask'),
                    'moment0_weighted_sum_noise_mask': res.get('moment0_weighted_sum_noise_mask'),
                    'cube_path': save_cube_path,
                    'moment0_path': save_moment0_path,
                    'mosaic_weights_path': None,
                    'timing': {
                        'imaging_s': imaging_s,
                        'processing_s': processing_s,
                        'substeps': timing,
                        'total_field_time_s': float(field_total_s),
                    },
                }
            else:
                source_stitch_meta.setdefault(
                    int(source_id),
                    {
                        'ref_freq_hz': float(ref_freq_hz) if ref_freq_hz is not None else None,
                        'chan_width_hz': float(chan_width_hz) if chan_width_hz is not None else None,
                        'chan_freqs_hz': chan_freqs_hz,
                        'chan_freqs_geo_hz': chan_freqs_geo_hz,
                        'grid_meta': field_grid_meta,
                        'pb_fwhm_arcsec': float(res.get('pb_fwhm_arcsec', np.nan)),
                        'outframe': outframe,
                        'ephemeris_meta': {
                            'correction': copy.deepcopy(ephem_diag) if ephem_diag is not None else None,
                            'source_axis': copy.deepcopy(source_axis_diag) if source_axis_diag is not None else None,
                        } if (ephem_diag is not None or source_axis_diag is not None) else None,
                    },
                )
                cube_field = res.get('cube')
                if cube_field is not None:
                    if int(source_id) not in source_stitch_states:
                        t_stitch_init = time.perf_counter()
                        source_stitch_states[int(source_id)] = _init_mosaic_stitch_state(
                            sorted(int(fid) for fid in field_chunks.keys()),
                            field_phase_centers,
                            cube_shape=tuple(int(v) for v in cube_field.shape),
                            cell_arcsec=float(field_grid_meta.get('cell_arcsec', np.nan)),
                            pb_fwhm_arcsec=float(res.get('pb_fwhm_arcsec', np.nan)),
                            pb_cutoff=0.1,
                            forced_shape=tuple(int(v) for v in geometry_plan.get('mosaic_shape', ())) if geometry_plan.get('mosaic_shape') else None,
                            forced_center_rad=(
                                float(geometry_plan.get('mosaic_center_ra_rad')),
                                float(geometry_plan.get('mosaic_center_dec_rad')),
                            ) if geometry_plan else None,
                        )
                        source_stitch_states[int(source_id)]['stitch_accumulate_s'] = 0.0
                        _profile_logf(tmp_dir, 'process_spw stitch_init spw=%s source=%s field_count=%s dt=%.3f', spw_name, source_id, len(field_chunks), (time.perf_counter() - t_stitch_init))
                    t_stitch_add = time.perf_counter()
                    _accumulate_field_cube_to_stitch(source_stitch_states[int(source_id)], int(field_id), cube_field)
                    dt_stitch_add = float(time.perf_counter() - t_stitch_add)
                    source_stitch_states[int(source_id)]['stitch_accumulate_s'] += dt_stitch_add
                    _profile_logf(tmp_dir, 'process_spw stitch_accumulate spw=%s source=%s field=%s cube_shape=%s dt=%.3f', spw_name, source_id, field_id, tuple(int(v) for v in cube_field.shape), dt_stitch_add)

        if not is_mosaic_source:
            continue

        first_field = source_stitch_meta.get(int(source_id), {})
        stitch_state = source_stitch_states.get(int(source_id))
        if stitch_state is None:
            continue
        ref_freq_hz = first_field.get('ref_freq_hz')
        chan_width_hz = first_field.get('chan_width_hz')
        chan_freqs_hz = first_field.get('chan_freqs_hz')
        outframe = str(first_field.get('outframe', source_outframe.get(int(source_id), 'LSRK')))
        grid_meta = first_field.get('grid_meta', {})
        cell_arcsec = float(grid_meta.get('cell_arcsec', np.nan))
        pb_fwhm_arcsec = float(first_field.get('pb_fwhm_arcsec', np.nan))
        if (not np.isfinite(cell_arcsec)) or cell_arcsec <= 0.0 or (not np.isfinite(pb_fwhm_arcsec)) or pb_fwhm_arcsec <= 0.0:
            _rank_logf(
                tmp_dir,
                '[warn] missing field grid metadata for stitch spw=%s source=%s',
                spw_name,
                source_id,
            )
            continue

        save_mosaic_cube_path = None
        source_label = source_names_by_id.get(int(source_id), f'source_{int(source_id)}')
        source_token = _sanitize_token(source_label)
        if save_cube:
            base = f'cube_source-{source_token}_mosaic_spw-{spw_id}.npy'
            save_mosaic_cube_path = os.path.join(products_dir if products_dir else (tmp_dir if tmp_dir else '.'), base)
        save_mosaic_moment0_path = None
        if save_moment0:
            base = f'moment0_source-{source_token}_mosaic_spw-{spw_id}.npy'
            save_mosaic_moment0_path = os.path.join(products_dir if products_dir else (tmp_dir if tmp_dir else '.'), base)

        t_src_agg = time.perf_counter()
        t_stitch_finalize = time.perf_counter()
        mosaic_cube, mosaic_meta = _finalize_mosaic_stitch_state(stitch_state)
        dt_stitch_finalize = float(time.perf_counter() - t_stitch_finalize)
        dt_stitch = float(stitch_state.get('stitch_accumulate_s', 0.0)) + dt_stitch_finalize
        _profile_logf(tmp_dir, 'process_spw stitch_finalize spw=%s source=%s accumulate=%.3f finalize=%.3f total=%.3f shape=%s', spw_name, source_id, float(stitch_state.get('stitch_accumulate_s', 0.0)), dt_stitch_finalize, dt_stitch, tuple(int(v) for v in mosaic_meta['shape']))
        weight_sum = np.asarray(mosaic_meta['weight_sum'], dtype=np.float32)
        max_weight = float(np.nanmax(weight_sum)) if weight_sum.size else 0.0
        coverage_mask = None
        coverage_frac = 0.0
        if np.isfinite(max_weight) and max_weight > 0.0:
            coverage_mask = weight_sum >= (0.25 * max_weight)
            coverage_frac = float(np.mean(coverage_mask))
        if verbose:
            _rank_logf(
                tmp_dir,
                '[stitch] spw=%s source=%s fields=%s shape=%sx%s cell=%.4f" pb=%.2f" cutoff=%.2f cov_thr=0.25 cov_frac=%.3f dt=%.2fs',
                spw_name,
                source_id,
                len(field_chunks),
                mosaic_meta['shape'][1],
                mosaic_meta['shape'][0],
                mosaic_meta['cell_arcsec'],
                mosaic_meta['pb_fwhm_arcsec'],
                mosaic_meta['pb_cutoff'],
                coverage_frac,
                dt_stitch,
            )
        _rank_diagf(
            tmp_dir,
            'mosaic spw=%s source=%s total_weight_sum=%.6e coverage_frac=%.6f',
            spw_name,
            source_id,
            float(np.sum(mosaic_meta['weight_sum'], dtype=np.float64)),
            coverage_frac,
        )
        for fid in sorted(int(v) for v in field_chunks.keys()):
            _rank_diagf(
                tmp_dir,
                'mosaic_field spw=%s source=%s field=%s num_weight_sum=%.6e den_weight_sum=%.6e',
                spw_name,
                source_id,
                fid,
                float(mosaic_meta.get('field_num_weight_sum', {}).get(fid, np.nan)),
                float(mosaic_meta.get('field_den_weight_sum', {}).get(fid, np.nan)),
            )
        if save_mosaic_cube_path is not None:
            np.save(save_mosaic_cube_path, mosaic_cube.astype(np.float32, copy=False))

        t_products = time.perf_counter()
        products = _compute_cube_products(
            mosaic_cube,
            ref_sigma=ref_sigma,
            mom0_thresh_sigma=mom0_thresh_sigma,
            gate_sigma=gate_sigma,
            ref_zero_frac_thr=ref_zero_frac_thr,
            mom0_zero_frac_thr=mom0_zero_frac_thr,
            ref_smooth_width=ref_smooth_width,
            mom0_smooth_width=mom0_smooth_width,
            neg_extent_delta_thr=neg_extent_delta_thr,
            neg_extent_trim_frac=neg_extent_trim_frac,
            spatial_mask=coverage_mask,
        )
        dt_products = time.perf_counter() - t_products
        _profile_logf(tmp_dir, 'process_spw mosaic_products spw=%s source=%s dt=%.3f', spw_name, source_id, dt_products)
        if save_mosaic_moment0_path is not None:
            np.save(save_mosaic_moment0_path, products['moment0'].astype(np.float32, copy=False))

        mosaic_entry = {
            'reference_sum_raw': products['reference_sum_raw'].astype(np.float32, copy=False),
            'moment0': products['moment0'].astype(np.float32, copy=False),
            'moment0_weighted_sum_raw': products['moment0_weighted_sum_raw'].astype(np.float32, copy=False),
            'reference_sum_raw_processed': products['reference_sum_raw_processed'].astype(np.float32, copy=False),
            'moment0_weighted_sum_raw_processed': products['moment0_weighted_sum_raw_processed'].astype(np.float32, copy=False),
            'reference_sum_snr': products['reference_sum_snr'].astype(np.float32, copy=False),
            'moment0_weighted_sum_snr': products['moment0_weighted_sum_snr'].astype(np.float32, copy=False),
            'evidence': products['evidence'].astype(np.float32, copy=False),
            'sigma': products['sigma'].astype(np.float32, copy=False),
            'outframe': outframe,
            'chan_freqs_hz': chan_freqs_hz,
            'ref_freq_hz': float(ref_freq_hz) if ref_freq_hz is not None else None,
            'chan_width_hz': float(chan_width_hz) if chan_width_hz is not None else None,
            'grid_meta': {
                'shape': tuple(int(v) for v in mosaic_meta['shape']),
                'cell_arcsec': float(mosaic_meta['cell_arcsec']),
                'pb_fwhm_arcsec': float(mosaic_meta['pb_fwhm_arcsec']),
                'pb_cutoff': float(mosaic_meta['pb_cutoff']),
                'coverage_threshold_frac': 0.25,
                'coverage_fraction_kept': float(coverage_frac),
                'mosaic_center_ra_rad': float(mosaic_meta['mosaic_center_ra_rad']),
                'mosaic_center_dec_rad': float(mosaic_meta['mosaic_center_dec_rad']),
                'field_offsets_arcsec': copy.deepcopy(mosaic_meta['field_offsets_arcsec']),
                'field_num_weight_sum': copy.deepcopy(mosaic_meta.get('field_num_weight_sum', {})),
                'field_den_weight_sum': copy.deepcopy(mosaic_meta.get('field_den_weight_sum', {})),
            },
            'mosaic_weights_path': None,
            'spectra_qc': copy.deepcopy(products.get('spectra_qc', {})),
            'reference_sum_noise_mask': products.get('reference_sum_noise_mask'),
            'moment0_weighted_sum_noise_mask': products.get('moment0_weighted_sum_noise_mask'),
            'cube_path': save_mosaic_cube_path,
            'moment0_path': save_mosaic_moment0_path,
            'timing': {
                'imaging_s': float(dt_stitch),
                'processing_s': float(dt_products),
                'substeps': {
                    'stitch_cube_s': float(dt_stitch),
                    'product_compute_s': float(dt_products),
                    'total_s': float(dt_stitch + dt_products),
                },
                'total_source_aggregate_s': float(time.perf_counter() - t_src_agg),
            },
        }
        if save_moment0:
            weight_sum_path = os.path.join(
                products_dir if products_dir else (tmp_dir if tmp_dir else '.'),
                f'mosaic_weights_source-{source_token}_spw-{spw_id}.npy',
            )
            np.save(weight_sum_path, mosaic_meta['weight_sum'].astype(np.float32, copy=False))
            mosaic_entry['mosaic_weights_path'] = weight_sum_path
        results['sources'][source_id]['mosaic'] = mosaic_entry

    _rank_logf(
        tmp_dir,
        '[rank %s/%s] done spw=%s ddid=%s dt=%.2fs',
        rank,
        size,
        spw_name,
        ddid,
        time.perf_counter() - t_all,
    )
    _profile_logf(tmp_dir, 'process_spw done spw=%s ddid=%s total=%.3f mstransform_bin=%.3f mstransform_regrid=%.3f', spw_name, ddid, (time.perf_counter() - t_all), float(mstransform_bin_s), float(mstransform_regrid_s))
    results['timing'] = {
        'mstransform_bin_s': float(mstransform_bin_s),
        'mstransform_regrid_s': float(mstransform_regrid_s),
        'mstransform_lsrk_s': float(mstransform_regrid_s),
        'mstransform_calls': int(mstransform_calls),
        'total_spw_s': float(time.perf_counter() - t_all),
    }
    return results

def run_findroi_mpi(
    vis: str | list[str],
    context: Any | None = None,
    executor: Any | None = None,
    field: str | int | list[int] | None = 'target',
    spw: str | int | list[int] | None = None,
    tmp_dir: str = 'tmp_findroi',
    parallel: str | bool = 'automatic',
) -> dict[str, Any] | None:
    '''Run MPI-parallel findROI processing and return the stage product.'''
    cfg = copy.deepcopy(_DEFAULT_FINDROI_CONFIG)
    timebin_sec = float(cfg['timebin_sec'])
    min_nchan = int(cfg['min_nchan'])
    npix = int(cfg['npix'])
    fov_pb_mult = float(cfg['fov_pb_mult'])
    ref_sigma = float(cfg['ref_sigma'])
    mom0_thresh_sigma = float(cfg['mom0_thresh_sigma'])
    gate_sigma = float(cfg['gate_sigma'])
    pos_evidence_thr = float(cfg['pos_evidence_thr'])
    neg_evidence_thr = float(cfg['neg_evidence_thr'])
    evidence_thr = cfg['evidence_thr']
    evidence_bin_scales = tuple(int(v) for v in cfg['evidence_bin_scales'])
    ref_zero_frac_thr = float(cfg['ref_zero_frac_thr'])
    mom0_zero_frac_thr = float(cfg['mom0_zero_frac_thr'])
    ref_smooth_width = int(cfg['ref_smooth_width'])
    mom0_smooth_width = int(cfg['mom0_smooth_width'])
    neg_extent_delta_thr = float(cfg['neg_extent_delta_thr'])
    neg_extent_trim_frac = float(cfg['neg_extent_trim_frac'])
    acf_edge_trim_frac = float(cfg['acf_edge_trim_frac'])
    acf_smooth_frac = float(cfg['acf_smooth_frac'])
    fwhm_global_fallback_factor = float(cfg['fwhm_global_fallback_factor'])
    fwhm_min_chan = int(cfg['fwhm_min_chan'])
    rolling_rms_window = int(cfg['rolling_rms_window'])
    rolling_rms_target_unsmoothed = float(cfg['rolling_rms_target_unsmoothed'])
    rolling_rms_target_smoothed = float(cfg['rolling_rms_target_smoothed'])
    uv_taper_auto = bool(cfg['uv_taper_auto'])
    uv_taper_sigma_uv = cfg['uv_taper_sigma_uv']
    uv_taper_fwhm_cell = float(cfg['uv_taper_fwhm_cell'])
    roi_thresh = float(cfg['roi_thresh'])
    roi_cont_thresh = float(cfg['roi_cont_thresh'])
    tmp_overwrite = bool(cfg['tmp_overwrite'])
    save_moment0 = bool(cfg['save_moment0'])
    save_cube = bool(cfg['save_cube'])
    save_results_path = None
    verbose = bool(cfg['verbose'])
    if context is None:
        raise RuntimeError('hif_findroi requires pipeline context from importdata.')
    t_run = time.perf_counter()
    if evidence_thr is not None:
        pos_evidence_thr = float(evidence_thr)
    if tmp_dir:
        tmp_dir = os.path.abspath(tmp_dir)
        if tmp_overwrite and os.path.isdir(tmp_dir):
            shutil.rmtree(tmp_dir)
        os.makedirs(tmp_dir, exist_ok=True)
    products_dir = os.path.join(tmp_dir, 'findroi_products') if tmp_dir else 'findroi_products'
    logs_dir = os.path.join(tmp_dir, 'logs') if tmp_dir else 'logs'
    diagnostics_dir = os.path.join(tmp_dir, 'diagnostics') if tmp_dir else 'diagnostics'
    os.makedirs(products_dir, exist_ok=True)
    os.makedirs(logs_dir, exist_ok=True)
    os.makedirs(diagnostics_dir, exist_ok=True)
    _rank_logf(tmp_dir, '[run] start findroi')

    t_inv = time.perf_counter()
    vis_list = _resolve_pipeline_vis_list(context, vis)
    ms0 = _context_ms_for_vis(context, vis_list[0])
    if ms0 is None:
        raise RuntimeError(f'No pipeline MeasurementSet found in context for {vis_list[0]}.')
    project_structure = getattr(context, 'project_structure', None)
    oussid = None if project_structure is None else getattr(project_structure, 'ousstatus_entity_id', None)
    if oussid in (None, '', 'unknown'):
        oussid = 'oussid'
    prefix = re.sub(r'[^A-Za-z0-9_]+', '_', str(oussid).replace('uid://', 'uid___')).strip('_')
    products_tar_path = PipelineProductNameBuilder.auxiliary_products(
        'findroi_products.tar',
        ousstatus_entity_id=prefix,
        output_dir=tmp_dir,
    )

    # Temporary hard switch for 7m/12m-specific heuristics.
    # Keep this simple so it can later be replaced by pipeline Context.
    diameters = np.asarray([ant.diameter for ant in getattr(ms0.antenna_array, 'antennas', [])], dtype=np.float64)
    if diameters.size == 0:
        raise RuntimeError('No antenna diameters found in pipeline context.')
    dish_diameter_m = float(np.median(diameters))
    array = '7m' if dish_diameter_m < 9.0 else '12m'
    if array == '7m':
        npix_eff = 128
        fov_pb_mult_eff = 2.0
        uv_taper_auto_eff = False
        uv_taper_sigma_uv_eff = None
        timebin_sec_eff = 240.0
    else:
        npix_eff = int(npix)
        fov_pb_mult_eff = float(fov_pb_mult)
        uv_taper_auto_eff = bool(uv_taper_auto)
        uv_taper_sigma_uv_eff = uv_taper_sigma_uv
        timebin_sec_eff = timebin_sec
    inv = get_ddid_spw_inventory(vis_list[0], ms0)
    science_spw_ids = {
        int(spw_obj.id)
        for spw_obj in ms0.get_spectral_windows(science_windows_only=True)
    }
    sci = select_science_ddids(inv, science_spw_ids=science_spw_ids, min_nchan=min_nchan)
    sci = _filter_science_ddids(inv, sci, spw, context, vis_list[0])
    if not sci:
        raise RuntimeError(f'No science SPWs selected for hif_findroi spw={spw!r}.')
    spw_names = {r['ddid']: r['name'] for r in inv}
    ddid_rows = {int(r['ddid']): r for r in inv}
    sci_spw = []
    for ddid in sci:
        row = ddid_rows[int(ddid)]
        virtual_spw_id = int(row['spw_id'])
        mapped = context.observing_run.real2virtual_spw_id(int(row['spw_id']), ms0)
        if mapped is not None:
            virtual_spw_id = int(mapped)
        sci_spw.append((int(ddid), spw_names.get(int(ddid), ''), virtual_spw_id))
    all_field_info = _context_field_groups_by_source_id(context, vis_list[0], None)
    if all_field_info is None:
        raise RuntimeError(f'No field/source information found in context for {vis_list[0]}.')
    sources_by_id = {int(source.id): source for source in getattr(ms0, 'sources', [])}
    project_outframes = {}
    for source_id in sorted(int(k) for k in all_field_info.get('groups', {}).keys()):
        source = sources_by_id.get(int(source_id))
        project_outframes[int(source_id)] = 'SOURCE' if bool(getattr(source, 'is_eph_obj', False)) else 'LSRK'
    field_ephemeris_paths: dict[int, str] = {}
    for field_obj in getattr(ms0, 'fields', []):
        source = getattr(field_obj, 'source', None)
        if source is None or not bool(getattr(source, 'is_eph_obj', False)):
            continue
        table_name = str(getattr(source, 'ephemeris_table', '') or '')
        if not table_name:
            continue
        if not table_name.endswith('.tab'):
            table_name = f'{table_name}.tab'
        field_ephemeris_paths[int(field_obj.id)] = os.path.join(ms0.name, 'FIELD', table_name)
    project_has_ephemeris = any(str(v).upper() == 'SOURCE' for v in project_outframes.values())
    if project_has_ephemeris:
        timebin_sec_eff = None
    _rank_logf(
        tmp_dir,
        '[run] array=%s npix=%s fov_pb_mult=%s timebin_sec=%s uv_taper_auto=%s uv_taper_sigma_uv=%s project_has_ephemeris=%s',
        array,
        npix_eff,
        str(fov_pb_mult_eff),
        str(timebin_sec_eff),
        uv_taper_auto_eff,
        str(uv_taper_sigma_uv_eff),
        str(project_has_ephemeris),
    )
    if field is None or field == 'target' or field == 'target_groups':
        field_info = _context_field_groups_by_source_id(context, vis_list[0], field)
        if field_info is None:
            raise RuntimeError(f'No target fields found in context for {vis_list[0]}.')
        field_groups = field_info['groups']
    else:
        context_field_info = _context_field_groups_by_source_id(context, vis_list[0], field)
        if context_field_info is None:
            raise RuntimeError(f'No fields matched hif_findroi field={field!r} for {vis_list[0]}.')
        field_info = context_field_info
        field_groups = field_info['groups']
    antenna_selections_by_vis = _findroi_antenna_selections(context, vis_list, intent='TARGET')
    science_spws, science_rows = _science_spw_metadata_from_inventory(vis_list[0], ms0, inv, sci)
    dt_inventory = time.perf_counter() - t_inv
    source_names_by_id = {int(k): str(v) for k, v in field_info.get('source_names', {}).items()}
    field_names_by_id = {
        int(fid): _field_name_for_id(field_info.get('field_names', []), int(fid))
        for source_field_ids in field_groups.values()
        for fid in source_field_ids
    }
    field_phase_centers = imaging.get_field_phase_centers_rad(getattr(ms0, 'fields', []))
    if not field_phase_centers:
        raise RuntimeError('No field phase centers found in pipeline context.')
    common_geometry_plan = {
        int(source_id): _source_common_geometry_plan(
            source_id=int(source_id),
            field_ids=[int(fid) for fid in field_ids],
            science_rows=science_rows,
            phase_centers_rad=field_phase_centers,
            dish_diameter_m=dish_diameter_m,
            npix=npix_eff,
            fov_pb_mult=fov_pb_mult_eff,
            pb_cutoff=0.1,
        )
        for source_id, field_ids in field_groups.items()
    }
    _rank_logf(
        tmp_dir,
        '[run] inventory dt=%.2fs science_ddids=%s n_sources=%s',
        dt_inventory,
        len(sci),
        len(field_groups),
    )

    args = []
    for ddid, spw_name, virtual_spw_id in sci_spw:
        spw_ids_by_vis = _real_spw_ids_by_vis(
            context,
            vis_list,
            virtual_spw_id=virtual_spw_id,
            fallback_spw_id=int(ddid_rows[int(ddid)]['spw_id']),
        )
        args.append((
            vis_list, ddid, spw_name, spw_ids_by_vis, int(ddid_rows[int(ddid)]['spw_id']), field_groups,
            antenna_selections_by_vis,
            source_names_by_id, field_names_by_id,
            common_geometry_plan, project_outframes, field_phase_centers, field_ephemeris_paths, products_dir, dish_diameter_m,
            timebin_sec_eff, npix_eff, fov_pb_mult_eff,
            ref_sigma, mom0_thresh_sigma, gate_sigma,
            ref_zero_frac_thr, mom0_zero_frac_thr,
            ref_smooth_width, mom0_smooth_width,
            neg_extent_delta_thr, neg_extent_trim_frac,
            tmp_dir, tmp_overwrite, verbose, save_moment0, save_cube,
            uv_taper_auto_eff, uv_taper_sigma_uv_eff, uv_taper_fwhm_cell, executor,
        ))

    spw_results = None
    t_dispatch = time.perf_counter()
    parallel_wanted = mpihelpers.parse_parallel_input_parameter(parallel)
    with TaskQueue(parallel=parallel_wanted) as tq:
        tq.map(_process_spw, args)
    spw_results = tq.get_results()
    if spw_results is None:
        return None
    failed_spw = [r for r in spw_results if isinstance(r, dict) and r.get('__error__')]
    if failed_spw:
        for r in failed_spw:
            _rank_logf(
                tmp_dir,
                '[taskqueue] dropped failed spw ddid=%s spw=%s error=%s',
                r.get('ddid'),
                r.get('spw_name'),
                r.get('error'),
            )
        spw_results = [r for r in spw_results if isinstance(r, dict) and not r.get('__error__')]
    if not spw_results:
        _rank_logf(tmp_dir, '[run] no successful spw results')
        return None
    failed_spw_errors = [
        f"SPW {r.get('spw_name', '?')} (ddid={r.get('ddid', '?')}) failed: {r.get('error', 'unknown error')}"
        for r in failed_spw
    ]

    dt_dispatch = time.perf_counter() - t_dispatch
    _rank_logf(tmp_dir, '[run] spw processing dt=%.2fs n_spw=%s', dt_dispatch, len(spw_results))

    # aggregate linewidth per source with weighted global estimate + fallback
    t_linewidth = time.perf_counter()
    source_fwhm_kms: dict[int, float] = {}
    source_fwhm_mode_by_id: dict[int, str] = {}
    per_field_fwhm_kms: dict[tuple[int, int, Any], float] = {}
    source_global_inputs: dict[int, list[dict[str, float]]] = {}
    for res in spw_results:
        spw_id = int(res['spw_id'])
        for source_id, fields in res['sources'].items():
            for field_id, s in fields.items():
                evid = s['evidence']
                ref_freq_hz = s['ref_freq_hz']
                chan_width_hz = s['chan_width_hz']
                if chan_width_hz is None or ref_freq_hz is None:
                    continue
                dv_kms = abs(
                    (chan_width_hz / ref_freq_hz)
                    * casa_tools.quanta.getvalue(
                        casa_tools.quanta.convert(casa_tools.quanta.constants('c'), 'km/s')
                    )[0]
                )
                hwhm, fwhm = _acf_hwhm_fwhm(
                    evid,
                    smooth_frac=acf_smooth_frac,
                    edge_trim_frac=acf_edge_trim_frac,
                )
                fwhm_kms = fwhm * dv_kms
                per_field_fwhm_kms[(int(source_id), int(spw_id), field_id)] = float(fwhm_kms)
                if isinstance(field_id, str):
                    continue
                w_res = float(np.sqrt(1.0 / max(dv_kms, 1e-12)))
                evid_arr = np.asarray(evid, dtype=np.float64)
                evid_finite = evid_arr[np.isfinite(evid_arr)]
                if evid_finite.size == 0:
                    w_snr = 0.0
                else:
                    w_snr = float(max(0.0, np.nanmax(evid_finite)))
                w_total = w_res * w_snr
                if (not np.isfinite(fwhm_kms)) or (not np.isfinite(w_total)):
                    continue
                source_global_inputs.setdefault(int(source_id), []).append({
                    'fwhm_kms': float(fwhm_kms),
                    'dv_kms': float(dv_kms),
                    'w_res': float(w_res),
                    'w_snr': float(w_snr),
                    'w_total': float(w_total),
                })

    fallback_sources: set[int] = set()
    for source_id, vals in source_global_inputs.items():
        fwhm_arr = np.asarray([v['fwhm_kms'] for v in vals], dtype=np.float64)
        w_arr = np.asarray([v['w_total'] for v in vals], dtype=np.float64)
        valid = np.isfinite(fwhm_arr) & np.isfinite(w_arr) & (w_arr > 0.0)
        if np.count_nonzero(valid) == 0:
            continue
        fwhm_use = fwhm_arr[valid]
        w_use = w_arr[valid]
        fwhm_global = float(np.sum(w_use * fwhm_use) / np.sum(w_use))
        if not np.isfinite(fwhm_global):
            continue
        source_fwhm_kms[int(source_id)] = float(fwhm_global)

        factor = float(max(fwhm_global_fallback_factor, 1.0))
        ratios = np.maximum(
            fwhm_use / max(fwhm_global, 1.0e-12),
            max(fwhm_global, 1.0e-12) / np.maximum(fwhm_use, 1.0e-12),
        )
        if np.any(ratios > factor):
            fallback_sources.add(int(source_id))
            source_fwhm_mode_by_id[int(source_id)] = 'per_spw_fallback'
        else:
            source_fwhm_mode_by_id[int(source_id)] = 'global'

    for source_id in source_fwhm_kms:
        source_fwhm_mode_by_id.setdefault(int(source_id), 'global')

    dt_linewidth = time.perf_counter() - t_linewidth
    _rank_logf(tmp_dir, '[run] linewidth aggregation dt=%.2fs n_sources=%s', dt_linewidth, len(source_fwhm_kms))

    # per-spw ROI detection with negative-first ordering and ratio renormalization
    t_detect = time.perf_counter()
    final = []
    for res in spw_results:
        spw_id = int(res['spw_id'])
        out = {'spw_id': res['spw_id'], 'spw_name': res['spw_name'], 'sources': {}}
        for source_id, fields in res['sources'].items():
            source_id_i = int(source_id)
            out['sources'].setdefault(source_id, {})
            fwhm_kms = source_fwhm_kms.get(source_id_i, None)
            for field_id, s in fields.items():
                ref_snr = np.asarray(s['reference_sum_snr'], dtype=np.float64)
                mw_snr = np.asarray(s['moment0_weighted_sum_snr'], dtype=np.float64)
                nchan = int(min(ref_snr.size, mw_snr.size))
                ref_freq_hz = s['ref_freq_hz']
                chan_width_hz = s['chan_width_hz']
                if chan_width_hz is None or ref_freq_hz is None:
                    out['sources'][source_id][field_id] = _empty_mini_with_continuum(
                        nchan=nchan,
                        thr=float(pos_evidence_thr),
                        neg_thr=float(neg_evidence_thr),
                        fwhm_chan=int(fwhm_min_chan),
                        fwhm_kms=float('nan'),
                        dv_kms=float('nan'),
                        reason='missing_channel_metadata',
                    )
                    continue
                dv_kms = abs(
                    (chan_width_hz / ref_freq_hz)
                    * casa_tools.quanta.getvalue(
                        casa_tools.quanta.convert(casa_tools.quanta.constants('c'), 'km/s')
                    )[0]
                )
                if dv_kms <= 0.0 or not np.isfinite(dv_kms):
                    out['sources'][source_id][field_id] = _empty_mini_with_continuum(
                        nchan=nchan,
                        thr=float(pos_evidence_thr),
                        neg_thr=float(neg_evidence_thr),
                        fwhm_chan=int(fwhm_min_chan),
                        fwhm_kms=float('nan'),
                        dv_kms=float(dv_kms) if np.isfinite(dv_kms) else float('nan'),
                        reason='invalid_channel_width',
                    )
                    continue
                fwhm_mode = str(source_fwhm_mode_by_id.get(source_id_i, 'global'))
                linewidth_fallback_level = 'source_global'
                if (fwhm_kms is not None) and np.isfinite(float(fwhm_kms)):
                    fwhm_kms_use = float(fwhm_kms)
                else:
                    fwhm_kms_use = float(fwhm_min_chan) * float(dv_kms)
                    fwhm_mode = 'default_4chan'
                    linewidth_fallback_level = 'default_4chan'
                if source_id_i in fallback_sources:
                    per_key = (source_id_i, int(spw_id), field_id)
                    if per_key in per_field_fwhm_kms and np.isfinite(float(per_field_fwhm_kms[per_key])):
                        fwhm_kms_use = float(per_field_fwhm_kms[per_key])
                        linewidth_fallback_level = 'per_spw'
                    fwhm_mode = 'per_spw_fallback'
                if (not np.isfinite(fwhm_kms_use)) or fwhm_kms_use <= 0.0:
                    fwhm_chan = int(fwhm_min_chan)
                    fwhm_kms_use = float(fwhm_chan) * float(dv_kms)
                    fwhm_mode = 'default_4chan'
                    linewidth_fallback_level = 'default_4chan'
                else:
                    fwhm_chan = max(int(fwhm_min_chan), int(round(fwhm_kms_use / dv_kms)))
                roi_run = _run_final_roi_detection(
                    ref_snr=ref_snr,
                    mw_snr=mw_snr,
                    ref_noise_mask=s.get('reference_sum_noise_mask'),
                    mw_noise_mask=s.get('moment0_weighted_sum_noise_mask'),
                    diag=copy.deepcopy(s.get('spectra_qc', {})),
                    fwhm_chan=fwhm_chan,
                    pos_thr=float(pos_evidence_thr),
                    neg_thr=float(neg_evidence_thr),
                    bin_scales=evidence_bin_scales,
                    rolling_rms_window=int(rolling_rms_window),
                    rolling_rms_target_unsmoothed=float(rolling_rms_target_unsmoothed),
                    rolling_rms_target_smoothed=float(rolling_rms_target_smoothed),
                    neg_extent_delta_thr=float(neg_extent_delta_thr),
                    neg_extent_trim_frac=float(neg_extent_trim_frac),
                )
                s['reference_sum_snr'] = roi_run['reference_sum_snr'].astype(np.float32, copy=False)
                s['moment0_weighted_sum_snr'] = roi_run['moment0_weighted_sum_snr'].astype(np.float32, copy=False)
                s['evidence'] = roi_run['evidence'].astype(np.float32, copy=False)
                s['evidence_negative'] = roi_run['evidence_negative'].astype(np.float32, copy=False)
                s['reference_rms_spectrum'] = roi_run['reference_rms_spectrum'].astype(np.float32, copy=False)
                s['moment0_rms_spectrum'] = roi_run['moment0_rms_spectrum'].astype(np.float32, copy=False)
                s['roi_union_mask'] = roi_run['roi_union_mask'].astype(bool, copy=False)
                diag_new = copy.deepcopy(s.get('spectra_qc', {}))
                diag_new.update(roi_run.get('diagnostics', {}))
                diag_new['fwhm_selection_mode'] = fwhm_mode
                diag_new['fwhm_global_fallback_triggered'] = bool(source_id_i in fallback_sources)
                s['spectra_qc'] = diag_new

                mini = copy.deepcopy(roi_run['mini_pos'])
                mini_neg = roi_run['mini_neg']
                union_ranges = _merge_channel_ranges(
                    list(mini.get('line_ranges', [])) + list(mini_neg.get('line_ranges', [])),
                    nchan=int(np.asarray(roi_run['evidence']).size),
                )
                mini['cont_ranges'] = _complement_channel_ranges(union_ranges, int(np.asarray(roi_run['evidence']).size))
                mini['neg_line_ranges'] = [tuple(v) for v in mini_neg.get('line_ranges', [])]
                mini['neg_line_range_peakSNR'] = [float(v) for v in mini_neg.get('line_range_peakSNR', [])]
                mini['neg_threshold_snr'] = float(neg_evidence_thr)
                mini['reference_zero_fraction'] = float(diag_new.get('reference_zero_fraction', np.nan))
                mini['moment0_zero_fraction'] = float(diag_new.get('moment0_zero_fraction', np.nan))
                mini['reference_smoothed'] = bool(diag_new.get('reference_smoothed', False))
                mini['moment0_smoothed'] = bool(diag_new.get('moment0_smoothed', False))
                mini['moment0_rejected_zero_fraction'] = bool(diag_new.get('moment0_rejected_zero_fraction', False))
                mini['moment0_rejected_negative_extent'] = bool(diag_new.get('moment0_rejected_negative_extent', False))
                mini['mom0_usage_mode'] = str(diag_new.get('mom0_usage_mode', 'used'))
                mini['negative_extent_delta_sigma'] = float(diag_new.get('negative_extent_delta_sigma', np.nan))
                mini['renorm_ratio_reference'] = float(diag_new.get('renorm_ratio_reference', 1.0))
                mini['renorm_ratio_moment0'] = float(diag_new.get('renorm_ratio_moment0', 1.0))
                mini['fwhm_selection_mode'] = fwhm_mode
                mini['linewidth_fallback_level'] = linewidth_fallback_level
                mini['fwhm_global_fallback_triggered'] = bool(source_id_i in fallback_sources)
                mini['snr_failed_reference'] = bool(diag_new.get('snr_failed_reference', False))
                mini['snr_failed_moment0'] = bool(diag_new.get('snr_failed_moment0', False))
                mini['snr_failed_both'] = bool(diag_new.get('snr_failed_both', False))
                mini['evidence_valid_fraction'] = float(diag_new.get('evidence_valid_fraction', np.nan))
                mini['roi_skipped_reason'] = str(diag_new.get('roi_skipped_reason', 'none'))
                mini['decision_trace'] = copy.deepcopy(diag_new.get('decision_trace', {}))
                mini['fwhm_kms'] = float(fwhm_kms_use)
                mini['dv_kms'] = float(dv_kms)
                mini['acf_fwhm_kms_spw'] = float(per_field_fwhm_kms.get((source_id_i, int(spw_id), field_id), np.nan))
                out['sources'][source_id][field_id] = mini
        final.append(out)
    dt_detect = time.perf_counter() - t_detect
    _rank_logf(tmp_dir, '[run] roi detection dt=%.2fs', dt_detect)

    if save_results_path is None:
        save_results_path = os.path.join(tmp_dir, 'findroi_results.pkl') if tmp_dir else 'findroi_results.pkl'
    export_results_path = os.path.join(products_dir, 'findroi_results.pkl')

    config = {
        'timebin_sec': None if timebin_sec_eff is None else float(timebin_sec_eff),
        'timebin_sec_requested': None if timebin_sec is None else float(timebin_sec),
        'min_nchan': int(min_nchan),
        'field_selection': field,
        'array': array,
        'npix': int(npix_eff),
        'npix_requested': int(npix),
        'fov_pb_mult': float(fov_pb_mult_eff),
        'fov_pb_mult_requested': float(fov_pb_mult),
        'ref_sigma': float(ref_sigma),
        'mom0_thresh_sigma': float(mom0_thresh_sigma),
        'gate_sigma': float(gate_sigma),
        'pos_evidence_thr': float(pos_evidence_thr),
        'neg_evidence_thr': float(neg_evidence_thr),
        'evidence_thr': None if evidence_thr is None else float(evidence_thr),
        'evidence_bin_scales': tuple(int(v) for v in evidence_bin_scales),
        'ref_zero_frac_thr': float(ref_zero_frac_thr),
        'mom0_zero_frac_thr': float(mom0_zero_frac_thr),
        'ref_smooth_width': int(ref_smooth_width),
        'mom0_smooth_width': int(mom0_smooth_width),
        'neg_extent_delta_thr': float(neg_extent_delta_thr),
        'neg_extent_trim_frac': float(neg_extent_trim_frac),
        'acf_edge_trim_frac': float(acf_edge_trim_frac),
        'acf_smooth_frac': float(acf_smooth_frac),
        'fwhm_global_fallback_factor': float(fwhm_global_fallback_factor),
        'fwhm_min_chan': int(fwhm_min_chan),
        'rolling_rms_window': int(rolling_rms_window),
        'rolling_rms_target_unsmoothed': float(rolling_rms_target_unsmoothed),
        'rolling_rms_target_smoothed': float(rolling_rms_target_smoothed),
        'uv_taper_auto': bool(uv_taper_auto_eff),
        'uv_taper_sigma_uv': float(uv_taper_sigma_uv_eff) if uv_taper_sigma_uv_eff is not None else None,
        'uv_taper_fwhm_cell': float(uv_taper_fwhm_cell),
        'roi_thresh': float(roi_thresh),
        'roi_cont_thresh': float(roi_cont_thresh),
        'tmp_overwrite': bool(tmp_overwrite),
        'save_cube': bool(save_cube),
        'save_moment0': bool(save_moment0),
    }
    spw_timing = {}
    for spw_res in spw_results:
        spw_timing[str(int(spw_res['spw_id']))] = copy.deepcopy(spw_res.get('timing', {}))
    run_timing = {
        'inventory_s': float(dt_inventory),
        'spw_processing_s': float(dt_dispatch),
        'linewidth_aggregation_s': float(dt_linewidth),
        'roi_detection_s': float(dt_detect),
        'schema_build_s': 0.0,
        'summary_plot_s': 0.0,
        'roi_dat_write_s': 0.0,
        'save_results_s': 0.0,
        'tar_products_s': 0.0,
        'total_run_s': 0.0,
        'spw': spw_timing,
    }
    t_schema = time.perf_counter()
    results = _build_findroi_stage_product(
        input_vis_arg=vis,
        vis_list=vis_list,
        tmp_dir=tmp_dir,
        prefix=prefix,
        field_selection=field,
        config=config,
        inv=inv,
        sci_ddids=sci,
        science_spws=science_spws,
        field_info=field_info,
        spw_results=spw_results,
        findroi_blocks=final,
        source_fwhm_kms_by_id=source_fwhm_kms,
        source_fwhm_mode_by_id=source_fwhm_mode_by_id,
        common_geometry_plan=common_geometry_plan,
        run_timing=run_timing,
        save_results_path=save_results_path,
    )
    run_timing['schema_build_s'] = float(time.perf_counter() - t_schema)
    results['metadata']['errors'] = copy.deepcopy(failed_spw_errors)
    results['metadata']['counts'] = {
        'selected_spws': int(len(sci_spw)),
        'successful_spws': int(len(spw_results)),
        'failed_spws': int(len(failed_spw_errors)),
    }

    t_plot = time.perf_counter()
    plot_artifacts = _save_default_summary_plots(results, products_dir=products_dir)
    run_timing['summary_plot_s'] = float(time.perf_counter() - t_plot)
    results['metadata']['artifacts']['summary_plots'] = plot_artifacts
    _rank_logf(
        tmp_dir,
        '[run] summary plots dt=%.2fs n_sources=%s',
        run_timing['summary_plot_s'],
        len(plot_artifacts),
    )

    t_roi_dat = time.perf_counter()
    roi_dat_artifacts = _write_roi_dat_files(
        results,
        products_dir=products_dir,
        roi_thresh=roi_thresh,
        roi_cont_thresh=roi_cont_thresh,
    )
    run_timing['roi_dat_write_s'] = float(time.perf_counter() - t_roi_dat)
    results['metadata']['artifacts'].update(roi_dat_artifacts)
    _rank_logf(
        tmp_dir,
        '[run] ROI dat files dt=%.2fs',
        run_timing['roi_dat_write_s'],
    )

    results['metadata']['artifacts']['findroi_products_dir'] = products_dir
    results['metadata']['artifacts']['findroi_products_tar'] = products_tar_path
    results['metadata']['artifacts']['findroi_products_tar_bytes'] = None

    save_results_total_s = 0.0
    run_timing['save_results_s'] = 0.0
    if save_results_path:
        t_save = time.perf_counter()
        with open(save_results_path, 'wb') as fh:
            pickle.dump(results, fh, protocol=pickle.HIGHEST_PROTOCOL)
        final_save_s = float(time.perf_counter() - t_save)
        save_results_total_s += final_save_s
        # The timing metadata itself requires one final sync write; use the measured
        # post-tar save as the best estimate for that last write so persisted timing
        # does not underreport the total save path.
        run_timing['save_results_s'] = float(save_results_total_s + final_save_s)
        run_timing['total_run_s'] = float((time.perf_counter() - t_run) + final_save_s)
        results['metadata']['timing'] = copy.deepcopy(run_timing)
        with open(save_results_path, 'wb') as fh:
            pickle.dump(results, fh, protocol=pickle.HIGHEST_PROTOCOL)
    else:
        run_timing['save_results_s'] = float(save_results_total_s)
        run_timing['total_run_s'] = float(time.perf_counter() - t_run)
        results['metadata']['timing'] = copy.deepcopy(run_timing)

    # Keep the exported tarball self-contained by shipping a snapshot results pickle
    # alongside the product files, while the authoritative results pickle lives at
    # save_results_path and carries the final timing metadata.
    with open(export_results_path, 'wb') as fh:
        pickle.dump(results, fh, protocol=pickle.HIGHEST_PROTOCOL)
    if os.path.exists(products_tar_path):
        os.remove(products_tar_path)
    t_tar = time.perf_counter()
    with tarfile.open(products_tar_path, 'w') as tfh:
        tfh.add(products_dir, arcname=os.path.basename(products_dir))
    run_timing['tar_products_s'] = float(time.perf_counter() - t_tar)
    results['metadata']['artifacts']['findroi_products_tar_bytes'] = int(os.path.getsize(products_tar_path))
    if save_results_path:
        run_timing['total_run_s'] = float(time.perf_counter() - t_run)
        results['metadata']['timing'] = copy.deepcopy(run_timing)
        with open(save_results_path, 'wb') as fh:
            pickle.dump(results, fh, protocol=pickle.HIGHEST_PROTOCOL)
        _rank_logf(
            tmp_dir,
            '[run] finalized results to %s (save=%.2fs tar=%.2fs tar_bytes=%s total=%.2fs)',
            save_results_path,
            run_timing['save_results_s'],
            run_timing['tar_products_s'],
            results['metadata']['artifacts']['findroi_products_tar_bytes'],
            run_timing['total_run_s'],
        )
    _rank_logf(tmp_dir, '[run] total dt=%.2fs', run_timing['total_run_s'])

    return results


def default_tmp_dir(context: Any, output_dir: str | None) -> str:
    root = output_dir or getattr(context, 'output_dir', '.') or '.'
    return os.path.abspath(os.path.join(root, 'findroi_workdir'))


def summarize_stage_product(stage_product: dict[str, Any]) -> dict[str, Any]:
    fields = stage_product.get('products', {}).get('fields', {})
    spws = stage_product.get('inventory', {}).get('science_spws', {})
    counts = stage_product.get('metadata', {}).get('counts', {})
    n_source_spws = 0
    n_roi_with_lines = 0
    n_roi_with_cont = 0
    for spw_map in fields.values():
        for spw_block in spw_map.values():
            n_source_spws += 1
            roi = (spw_block.get('source_aggregate') or {}).get('roi_detected') or {}
            if roi.get('line_ranges') or roi.get('neg_line_ranges'):
                n_roi_with_lines += 1
            if roi.get('cont_ranges'):
                n_roi_with_cont += 1
    timing = stage_product.get('metadata', {}).get('timing', {})
    return {
        'n_sources': int(len(fields)),
        'n_spws': int(len(spws)),
        'n_selected_spws': int(counts.get('selected_spws', len(spws))),
        'n_successful_spws': int(counts.get('successful_spws', len(spws))),
        'n_failed_spws': int(counts.get('failed_spws', 0)),
        'n_source_spws': int(n_source_spws),
        'n_roi_with_lines': int(n_roi_with_lines),
        'n_roi_with_continuum': int(n_roi_with_cont),
        'total_run_s': timing.get('total_run_s'),
    }
