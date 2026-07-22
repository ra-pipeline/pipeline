from __future__ import annotations

import argparse
import glob
import logging
import os
import pickle
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

LOGGER = logging.getLogger(__name__)


def _load_results(path: str) -> dict[str, Any]:
    with open(path, 'rb') as fh:
        return pickle.load(fh)


def _find_results_path(tmp_dir: str, prefix: str | None) -> str:
    candidate = os.path.join(tmp_dir, 'findroi_products', 'findroi_results.pkl')
    if os.path.exists(candidate):
        return candidate
    candidate = os.path.join(tmp_dir, 'findroi_results.pkl')
    if os.path.exists(candidate):
        return candidate
    if prefix:
        candidate = os.path.join(tmp_dir, f'{prefix}_findroi_results.pkl')
        if os.path.exists(candidate):
            return candidate
    matches = sorted(glob.glob(os.path.join(tmp_dir, '*_findroi_results.pkl')))
    if not matches:
        raise FileNotFoundError(f'No findROI results pickle found in {tmp_dir}')
    return matches[-1]


def _guess_prefix(results_path: str) -> str | None:
    base = os.path.basename(results_path)
    if base == 'findroi_results.pkl':
        return None
    if base.endswith('_findroi_results.pkl'):
        return base.replace('_findroi_results.pkl', '')
    return None


def _spw_order(res: dict[str, Any]) -> list[str]:
    keys = list(res['inventory']['science_spws'].keys())
    return sorted(keys, key=lambda x: int(x))


def _resolve_source_name(res: dict[str, Any], source_name: str | None, source_id: int | None) -> str:
    srcs = res['inventory']['sources']
    if source_name is not None:
        if source_name not in srcs:
            raise KeyError(f'Unknown source_name {source_name!r}')
        return source_name
    if source_id is None:
        raise ValueError('Provide source_name or source_id')
    for name, meta in srcs.items():
        if int(meta.get('source_id', -1)) == int(source_id):
            return name
    raise KeyError(f'Unknown source_id {source_id}')


def _source_spw_block(res: dict[str, Any], source_name: str, spw_key: str) -> dict[str, Any] | None:
    return res.get('products', {}).get('fields', {}).get(source_name, {}).get(spw_key)


def _pick_field_id(src_spw_block: dict[str, Any]) -> int | None:
    per_field = src_spw_block.get('per_field', {})
    if not per_field:
        return None
    return sorted(per_field.keys())[0]


def _select_product_block(src_spw_block: dict[str, Any], field_id: int | None) -> dict[str, Any]:
    if field_id is None:
        return src_spw_block['source_aggregate']
    return src_spw_block['per_field'][int(field_id)]


def _channel_to_freq_ghz(spw_meta: dict[str, Any], nchan: int) -> np.ndarray | None:
    channel_axis = spw_meta.get('channel_axis', {})
    ref_freq_hz = channel_axis.get('ref_freq_hz')
    chan_width_hz = channel_axis.get('chan_width_hz')
    if ref_freq_hz is None or chan_width_hz is None or nchan <= 0:
        return None
    idx = np.arange(nchan, dtype=np.float64)
    x_hz = float(ref_freq_hz) + (idx - 0.5 * (nchan - 1)) * float(chan_width_hz)
    return x_hz * 1.0e-9


def _linewidth_note(spw_meta: dict[str, Any], block: dict[str, Any]) -> str | None:
    roi = (block or {}).get('roi_detected') or {}
    fwhm_chan = roi.get('fwhm_chan')
    fwhm_kms = roi.get('fwhm_kms')
    if fwhm_chan is None:
        return None
    try:
        fwhm_chan_i = int(round(float(fwhm_chan)))
    except Exception:
        return None
    if fwhm_chan_i <= 0:
        return None
    chan_width_hz = ((spw_meta.get('channel_axis') or {}).get('chan_width_hz'))
    fwhm_mhz = None
    if chan_width_hz is not None:
        try:
            fwhm_mhz = abs(float(chan_width_hz)) * float(fwhm_chan_i) * 1.0e-6
        except Exception:
            fwhm_mhz = None
    if fwhm_kms is not None:
        try:
            fwhm_kms_f = float(fwhm_kms)
        except Exception:
            fwhm_kms_f = None
    else:
        fwhm_kms_f = None
    parts = [f'FWHM: {fwhm_chan_i} ch']
    if fwhm_mhz is not None and np.isfinite(fwhm_mhz):
        parts.append(f'{fwhm_mhz:.3f} MHz')
    if fwhm_kms_f is not None and np.isfinite(fwhm_kms_f):
        parts.append(f'{fwhm_kms_f:.3f} km/s')
    return ' | '.join(parts)


def _roi_qc_note(block: dict[str, Any]) -> str | None:
    roi = (block or {}).get('roi_detected') or {}
    bits: list[str] = []
    if roi.get('moment0_rejected_zero_fraction'):
        bits.append('mom0 rejected: zero-fraction')
    if roi.get('moment0_rejected_negative_extent'):
        bits.append('mom0 rejected: neg-extent')
    if roi.get('reference_smoothed'):
        bits.append('ref smoothed')
    if roi.get('moment0_smoothed'):
        bits.append('mom0 smoothed')
    mode = roi.get('fwhm_selection_mode')
    if mode:
        bits.append(f'fwhm={mode}')
    if not bits:
        return None
    return ' | '.join(bits)


def plot_spectra_by_spw(
    res: dict[str, Any],
    source_name: str | None = None,
    source_id: int | None = None,
    field_id: int | None = None,
    use_snr: bool = True,
) -> None:
    source_name = _resolve_source_name(res, source_name, source_id)
    spw_keys = _spw_order(res)
    n = len(spw_keys)
    fig, axes = plt.subplots(n, 1, figsize=(12, max(2.5, 2.2 * n)), sharex=False)
    axes = [axes] if n == 1 else list(axes)

    ykey_ref = 'reference_sum_snr' if use_snr else 'reference_sum_raw'
    ykey_mw = 'moment0_weighted_sum_snr' if use_snr else 'moment0_weighted_sum_raw'
    ylabel = r'SNR [$\sigma$]' if use_snr else 'Intensity'

    for ax, spw_key in zip(axes, spw_keys):
        spw_meta = res['inventory']['science_spws'][spw_key]
        src_spw = _source_spw_block(res, source_name, spw_key)
        if not src_spw:
            ax.axis('off')
            continue
        block = _select_product_block(src_spw, field_id)
        spec = block['spectra'][ykey_ref]
        mw = block['spectra'][ykey_mw]
        nchan = len(spec)
        x = _channel_to_freq_ghz(spw_meta, nchan)
        if x is None:
            x = np.arange(nchan, dtype=np.float64)
            xlabel = 'Channel'
        else:
            xlabel = 'Frequency (GHz)'
        if nchan > 0:
            ax.set_xlim(float(x[0]), float(x[-1]))
        ax.plot(x, spec, color='darkslateblue', lw=1.0, label='reference')
        ax.plot(x, mw, color='firebrick', lw=1.0, label='mom0-weighted')
        ax.set_title(f"spw {spw_meta['spw_id']} {spw_meta['spw_name']}")
        ax.set_ylabel(ylabel)
        lw_note = _linewidth_note(spw_meta, block)
        if lw_note:
            ax.text(
                0.01,
                0.98,
                lw_note,
                transform=ax.transAxes,
                ha='left',
                va='top',
                fontsize=plt.rcParams.get('axes.labelsize', 'medium'),
                color='dimgray',
                bbox={'boxstyle': 'round,pad=0.2', 'facecolor': 'white', 'alpha': 0.6, 'edgecolor': 'none'},
            )
        qc_note = _roi_qc_note(block)
        if qc_note:
            ax.text(
                0.01,
                0.88,
                qc_note,
                transform=ax.transAxes,
                ha='left',
                va='top',
                fontsize=plt.rcParams.get('axes.labelsize', 'medium'),
                color='dimgray',
                bbox={'boxstyle': 'round,pad=0.2', 'facecolor': 'white', 'alpha': 0.55, 'edgecolor': 'none'},
            )
        ax.grid(alpha=0.2)
    if axes:
        axes[0].legend(loc='upper right')
        axes[-1].set_xlabel(xlabel)
    level = 'source-level' if field_id is None else f'field {field_id}'
    fig.suptitle(f'{source_name} spectra per spw ({level})')
    fig.tight_layout()


def plot_moment0_by_spw(
    res: dict[str, Any],
    source_name: str | None = None,
    source_id: int | None = None,
    field_id: int | None = None,
) -> None:
    source_name = _resolve_source_name(res, source_name, source_id)
    spw_keys = [k for k in _spw_order(res) if _source_spw_block(res, source_name, k)]
    n = len(spw_keys)
    ncols = min(3, n) if n else 1
    nrows = int(np.ceil(n / ncols)) if n else 1
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.6 * ncols, 3.7 * nrows))
    axes = np.atleast_1d(axes).ravel()

    for i, ax in enumerate(axes):
        if i >= n:
            ax.axis('off')
            continue
        spw_key = spw_keys[i]
        spw_meta = res['inventory']['science_spws'][spw_key]
        src_spw = _source_spw_block(res, source_name, spw_key)
        block = _select_product_block(src_spw, field_id)
        art = block.get('artifacts', {})
        mom0_path = art.get('moment0_path')
        if not mom0_path or not os.path.exists(mom0_path):
            ax.text(0.5, 0.5, 'no moment0', ha='center', va='center')
            ax.set_axis_off()
            ax.set_title(f"spw {spw_meta['spw_id']}")
            continue
        img = np.load(mom0_path)
        im = ax.imshow(img, origin='lower')
        ax.set_title(f"spw {spw_meta['spw_id']} {spw_meta['spw_name']}")
        fig.colorbar(im, ax=ax, shrink=0.8)

    level = 'source-level' if field_id is None else f'field {field_id}'
    fig.suptitle(f'moment0 per spw ({source_name}, {level})')
    fig.tight_layout()


def plot_evidence_with_lines(
    res: dict[str, Any],
    source_name: str | None = None,
    source_id: int | None = None,
    field_id: int | None = None,
    min_region_snr: float = 7.0,
    min_neg_region_snr: float | None = None,
    region_label_fontsize: int | str | None = None,
) -> None:
    source_name = _resolve_source_name(res, source_name, source_id)
    spw_keys = _spw_order(res)
    n = len(spw_keys)
    fig, axes = plt.subplots(n, 1, figsize=(12, max(2.5, 2.2 * n)), sharex=False)
    axes = [axes] if n == 1 else list(axes)

    for ax, spw_key in zip(axes, spw_keys):
        spw_meta = res['inventory']['science_spws'][spw_key]
        src_spw = _source_spw_block(res, source_name, spw_key)
        if not src_spw:
            ax.axis('off')
            continue
        block = _select_product_block(src_spw, field_id)
        evid = block['spectra']['evidence']
        nchan = len(evid)
        x = _channel_to_freq_ghz(spw_meta, nchan)
        if x is None:
            x = np.arange(nchan, dtype=np.float64)
            xlabel = 'Channel'
            freq_axis = False
        else:
            xlabel = 'Frequency (GHz)'
            freq_axis = True
        ax.plot(x, evid, color='black', lw=1.0, label='evidence')
        roi = block.get('roi_detected') or {}
        line_ranges_all = roi.get('line_ranges', [])
        peak_snr_all = roi.get('line_range_peakSNR', [])
        neg_line_ranges_all = roi.get('neg_line_ranges', [])
        neg_peak_snr_all = roi.get('neg_line_range_peakSNR', [])

        line_ranges = []
        line_peak_snr = []
        for i, region in enumerate(line_ranges_all):
            if i >= len(peak_snr_all):
                continue
            snr = float(peak_snr_all[i])
            if np.isfinite(snr) and snr >= float(min_region_snr):
                line_ranges.append(region)
                line_peak_snr.append(snr)
        if min_neg_region_snr is None:
            min_neg_region_snr = float(min_region_snr)
        neg_line_ranges = []
        neg_line_peak_snr = []
        for i, region in enumerate(neg_line_ranges_all):
            if i >= len(neg_peak_snr_all):
                continue
            snr = float(neg_peak_snr_all[i])
            if np.isfinite(snr) and snr >= float(min_neg_region_snr):
                neg_line_ranges.append(region)
                neg_line_peak_snr.append(snr)

        if len(evid) and np.any(np.isfinite(evid)):
            ymax = float(np.nanmax(evid))
            ymin = float(np.nanmin(evid))
        else:
            ymax, ymin = 1.0, 0.0
        yrange = max(ymax - ymin, 1.0)
        if nchan > 0:
            ax.set_xlim(float(x[0]), float(x[-1]))

        # Keep bars and labels inside panel top with some headroom.
        bar_y0 = ymax + 0.02 * yrange
        level_dy = 0.05 * yrange
        label_dy = 0.012 * yrange
        max_levels = 8
        x_gap = max(3.0, 0.01 * max(float(nchan), 1.0))
        level_last_hi = [-1.0e30] * max_levels
        levels_by_index: dict[int, int] = {}

        order = sorted(range(len(line_ranges)), key=lambda idx: float(line_ranges[idx][0]))
        for idx in order:
            lo = float(line_ranges[idx][0])
            hi = float(line_ranges[idx][1])
            level = None
            for k in range(max_levels):
                if lo > (level_last_hi[k] + x_gap):
                    level = k
                    break
            if level is None:
                level = int(np.argmin(np.asarray(level_last_hi, dtype=np.float64)))
            level_last_hi[level] = max(level_last_hi[level], hi)
            levels_by_index[idx] = level

        neg_level_last_hi = [-1.0e30] * max_levels
        neg_levels_by_index: dict[int, int] = {}
        order_neg = sorted(range(len(neg_line_ranges)), key=lambda idx: float(neg_line_ranges[idx][0]))
        for idx in order_neg:
            lo = float(neg_line_ranges[idx][0])
            hi = float(neg_line_ranges[idx][1])
            level = None
            for k in range(max_levels):
                if lo > (neg_level_last_hi[k] + x_gap):
                    level = k
                    break
            if level is None:
                level = int(np.argmin(np.asarray(neg_level_last_hi, dtype=np.float64)))
            neg_level_last_hi[level] = max(neg_level_last_hi[level], hi)
            neg_levels_by_index[idx] = level

        if region_label_fontsize is None:
            region_label_fontsize = plt.rcParams.get('axes.labelsize', 'medium')

        level_max_used = 0
        for i, (lo, hi) in enumerate(line_ranges):
            level = int(levels_by_index.get(i, 0))
            level_max_used = max(level_max_used, level)
            bar_y = bar_y0 + level * level_dy
            lo_chan = int(lo)
            hi_chan = int(hi)
            if nchan > 0:
                lo_idx = max(0, min(lo_chan, nchan - 1))
                hi_idx = max(0, min(hi_chan, nchan - 1))
            else:
                lo_idx, hi_idx = 0, 0
            if freq_axis:
                lo_plot = float(x[lo_idx])
                hi_plot = float(x[hi_idx])
                if hi_plot < lo_plot:
                    lo_plot, hi_plot = hi_plot, lo_plot
                mid = 0.5 * (lo_plot + hi_plot)
            else:
                lo_plot = float(lo_chan)
                hi_plot = float(hi_chan)
                mid = 0.5 * (lo_plot + hi_plot)
            ax.hlines(bar_y, lo_plot, hi_plot, color='firebrick', lw=3)
            y_text = bar_y + label_dy
            ax.text(
                mid,
                y_text,
                f'{lo_chan}~{hi_chan}',
                ha='center',
                va='bottom',
                fontsize=region_label_fontsize,
            )

        neg_bar_base = bar_y0 + (level_max_used + 1) * level_dy + 0.025 * yrange
        neg_level_max_used = 0
        for i, (lo, hi) in enumerate(neg_line_ranges):
            level = int(neg_levels_by_index.get(i, 0))
            neg_level_max_used = max(neg_level_max_used, level)
            bar_y = neg_bar_base + level * level_dy
            lo_chan = int(lo)
            hi_chan = int(hi)
            if nchan > 0:
                lo_idx = max(0, min(lo_chan, nchan - 1))
                hi_idx = max(0, min(hi_chan, nchan - 1))
            else:
                lo_idx, hi_idx = 0, 0
            if freq_axis:
                lo_plot = float(x[lo_idx])
                hi_plot = float(x[hi_idx])
                if hi_plot < lo_plot:
                    lo_plot, hi_plot = hi_plot, lo_plot
                mid = 0.5 * (lo_plot + hi_plot)
            else:
                lo_plot = float(lo_chan)
                hi_plot = float(hi_chan)
                mid = 0.5 * (lo_plot + hi_plot)
            ax.hlines(bar_y, lo_plot, hi_plot, color='royalblue', lw=3)
            y_text = bar_y + label_dy
            ax.text(
                mid,
                y_text,
                f'{lo_chan}~{hi_chan}',
                ha='center',
                va='bottom',
                fontsize=region_label_fontsize,
                color='royalblue',
            )

        y_top = max(
            ymax + 0.18 * yrange,
            bar_y0 + (level_max_used + 1) * level_dy + 2.0 * label_dy,
            neg_bar_base + (neg_level_max_used + 1) * level_dy + 2.0 * label_dy,
        )
        y_bot = ymin - 0.06 * yrange
        ax.set_ylim(y_bot, y_top)
        ax.set_title(f"spw {spw_meta['spw_id']} {spw_meta['spw_name']}")
        ax.set_ylabel(r'Evidence [$\sigma$]')
        lw_note = _linewidth_note(spw_meta, block)
        if lw_note:
            ax.text(
                0.01,
                0.98,
                lw_note,
                transform=ax.transAxes,
                ha='left',
                va='top',
                fontsize=plt.rcParams.get('axes.labelsize', 'medium'),
                color='dimgray',
                bbox={'boxstyle': 'round,pad=0.2', 'facecolor': 'white', 'alpha': 0.6, 'edgecolor': 'none'},
            )
        qc_note = _roi_qc_note(block)
        if qc_note:
            ax.text(
                0.01,
                0.88,
                qc_note,
                transform=ax.transAxes,
                ha='left',
                va='top',
                fontsize=plt.rcParams.get('axes.labelsize', 'medium'),
                color='dimgray',
                bbox={'boxstyle': 'round,pad=0.2', 'facecolor': 'white', 'alpha': 0.55, 'edgecolor': 'none'},
            )
        ax.grid(alpha=0.2)
    if axes:
        axes[-1].set_xlabel(xlabel)
    level = 'source-level' if field_id is None else f'field {field_id}'
    fig.suptitle(f'{source_name} evidence with line ranges ({level})')
    fig.tight_layout()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--tmp-dir', default='tmp_findroi')
    parser.add_argument('--results-path', default=None)
    parser.add_argument('--prefix', default=None)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--source-name', default=None)
    group.add_argument('--source-id', type=int, default=None)
    parser.add_argument('--field-id', type=int, default=None)
    parser.add_argument('--min-region-snr', type=float, default=7.0)
    parser.add_argument('--no-show', action='store_true')
    args = parser.parse_args()

    tmp_dir = os.path.abspath(args.tmp_dir)
    results_path = args.results_path or _find_results_path(tmp_dir, args.prefix)
    res = _load_results(results_path)

    plot_spectra_by_spw(res, source_name=args.source_name, source_id=args.source_id, field_id=args.field_id)
    plot_moment0_by_spw(res, source_name=args.source_name, source_id=args.source_id, field_id=args.field_id)
    plot_evidence_with_lines(
        res,
        source_name=args.source_name,
        source_id=args.source_id,
        field_id=args.field_id,
        min_region_snr=args.min_region_snr,
    )

    if not args.no_show:
        plt.show()


if __name__ == '__main__':
    main()
