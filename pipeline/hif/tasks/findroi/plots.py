from __future__ import annotations

import argparse
import glob
import logging
import os
import pickle
from typing import Any

from matplotlib.lines import Line2D
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


def _plot_spw_keys(res: dict[str, Any], spw_key: str | None) -> list[str]:
    if spw_key is None:
        return _spw_order(res)
    key = str(spw_key)
    if key not in res['inventory']['science_spws']:
        raise KeyError(f'Unknown science SPW {spw_key!r}')
    return [key]


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


def has_valid_source_spw(
    res: dict[str, Any],
    source_name: str,
    field_id: int | None = None,
    spw_key: str | None = None,
) -> bool:
    """Return whether a source has at least one non-empty spectrum product."""
    for key in _plot_spw_keys(res, spw_key):
        src_spw = _source_spw_block(res, source_name, key)
        if not src_spw:
            continue
        try:
            block = _select_product_block(src_spw, field_id)
        except (KeyError, TypeError):
            continue
        evidence = (block.get('spectra') or {}).get('evidence')
        if evidence is not None and np.asarray(evidence).size > 0:
            return True
    return False


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


def _region_label(peak_snr: float) -> str:
    return f'peak {peak_snr:.1f} σ'


def _disable_axis_offsets(ax: Any) -> None:
    """Prevent Matplotlib from displaying hidden additive offsets on either axis."""
    ax.ticklabel_format(axis='both', useOffset=False)


def _add_channel_axis(ax: Any, x: np.ndarray, nchan: int, fontsize: float) -> None:
    """Add channel-number ticks above a frequency-based spectrum axis."""
    channel_ax = ax.twiny()
    _disable_axis_offsets(channel_ax)
    channel_ax.set_xlim(ax.get_xlim())
    n_ticks = min(7, max(nchan, 1))
    channel_ticks = np.unique(np.linspace(0, max(nchan - 1, 0), n_ticks, dtype=int))
    channel_ax.set_xticks([x[idx] for idx in channel_ticks])
    channel_ax.set_xticklabels([str(idx) for idx in channel_ticks])
    channel_ax.set_xlabel('Channel', fontsize=fontsize)
    channel_ax.tick_params(axis='x', labelsize=fontsize, pad=4)


def _add_legend_avoiding_annotations(
    fig: Any,
    ax: Any,
    handles: list[Line2D],
    annotations: list[Any],
    fontsize: float,
) -> None:
    """Place the legend where it does not cover ROI or metadata annotations."""
    locations = ('upper right', 'lower right', 'upper left', 'lower left', 'center right', 'center left')
    legend = None
    for location in locations:
        if legend is not None:
            legend.remove()
        legend = ax.legend(handles=handles, loc=location, fontsize=fontsize)
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        legend_bbox = legend.get_window_extent(renderer)
        if not any(legend_bbox.overlaps(annotation.get_window_extent(renderer)) for annotation in annotations):
            return


def _move_metadata_away_from_roi(
    fig: Any,
    metadata: list[Any],
    roi_annotations: list[Any],
) -> None:
    """Move metadata text if its rendered box overlaps a detected ROI label."""
    if not metadata or not roi_annotations:
        return
    alternate_positions = ((0.01, 0.85), (0.01, 0.72), (0.58, 0.95), (0.58, 0.72))
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    for annotation in metadata:
        original_position = annotation.get_position()
        for position in (original_position,) + alternate_positions:
            annotation.set_position(position)
            fig.canvas.draw()
            annotation_bbox = annotation.get_window_extent(renderer)
            overlaps_roi = any(
                annotation_bbox.overlaps(roi.get_window_extent(renderer)) for roi in roi_annotations
            )
            overlaps_metadata = any(
                other is not annotation and annotation_bbox.overlaps(other.get_window_extent(renderer))
                for other in metadata
            )
            if not overlaps_roi and not overlaps_metadata:
                break
        else:
            annotation.set_position(original_position)


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
    parts = [f'Auto-FWHM: {fwhm_chan_i} ch']
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
    spw_key: str | None = None,
) -> bool:
    source_name = _resolve_source_name(res, source_name, source_id)
    if not has_valid_source_spw(res, source_name, field_id, spw_key):
        return False
    spw_keys = _plot_spw_keys(res, spw_key)
    n = len(spw_keys)
    fig, axes = plt.subplots(n, 1, figsize=(12, max(4.0, 3.5 * n)), sharex=False)
    axes = [axes] if n == 1 else list(axes)
    metadata_annotations = {id(ax): [] for ax in axes}
    base_fontsize = float(plt.rcParams.get('font.size', 10.0))
    plot_fontsize = base_fontsize + 1.0
    title_fontsize = base_fontsize + 2.0
    label_fontsize = base_fontsize + 1.0

    ykey_ref = 'reference_sum_snr' if use_snr else 'reference_sum_raw'
    ykey_mw = 'moment0_weighted_sum_snr' if use_snr else 'moment0_weighted_sum_raw'
    ylabel = r'SNR [$\sigma$]' if use_snr else 'Intensity'

    for ax, spw_key in zip(axes, spw_keys):
        _disable_axis_offsets(ax)
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
        ax.set_title(
            f'{source_name} | SPW {spw_meta.get("spw_id", spw_key)} Spectra (LSRK frame)',
            fontsize=title_fontsize,
        )
        ax.set_ylabel(ylabel, fontsize=label_fontsize)
        if x is not None and xlabel == 'Frequency (GHz)':
            _add_channel_axis(ax, x, nchan, label_fontsize)
        lw_note = _linewidth_note(spw_meta, block)
        if lw_note:
            annotation = ax.text(
                0.01,
                0.95,
                lw_note,
                transform=ax.transAxes,
                ha='left',
                va='top',
                fontsize=plot_fontsize,
                color='dimgray',
                bbox={'boxstyle': 'round,pad=0.2', 'facecolor': 'white', 'alpha': 0.6, 'edgecolor': 'none'},
            )
            metadata_annotations[id(ax)].append(annotation)
        qc_note = _roi_qc_note(block)
        if qc_note:
            annotation = ax.text(
                0.01,
                0.85,
                qc_note,
                transform=ax.transAxes,
                ha='left',
                va='top',
                fontsize=plot_fontsize,
                color='dimgray',
                bbox={'boxstyle': 'round,pad=0.2', 'facecolor': 'white', 'alpha': 0.55, 'edgecolor': 'none'},
            )
            metadata_annotations[id(ax)].append(annotation)
        ax.grid(alpha=0.2)
        ax.tick_params(axis='both', labelsize=plot_fontsize)
    legend_ax = None
    handles = []
    if axes:
        legend_ax = next((ax for ax in axes if ax.lines), axes[0])
        handles, _ = legend_ax.get_legend_handles_labels()
        axes[-1].set_xlabel(xlabel, fontsize=label_fontsize)
    fig.tight_layout()
    if legend_ax is not None and handles:
        _add_legend_avoiding_annotations(
            fig,
            legend_ax,
            handles,
            metadata_annotations[id(legend_ax)],
            plot_fontsize,
        )
    return True


def plot_moment0_by_spw(
    res: dict[str, Any],
    source_name: str | None = None,
    source_id: int | None = None,
    field_id: int | None = None,
    spw_key: str | None = None,
) -> bool:
    source_name = _resolve_source_name(res, source_name, source_id)
    spw_keys = [
        key for key in _plot_spw_keys(res, spw_key)
        if has_valid_source_spw(res, source_name, field_id, key)
    ]
    if not spw_keys:
        return False
    n = len(spw_keys)
    ncols = min(3, n) if n else 1
    nrows = int(np.ceil(n / ncols)) if n else 1
    fig, axes = plt.subplots(nrows, ncols, figsize=(5.5 * ncols, 4.5 * nrows))
    axes = np.atleast_1d(axes).ravel()
    base_fontsize = float(plt.rcParams.get('font.size', 10.0))
    plot_fontsize = base_fontsize + 1.0
    title_fontsize = base_fontsize + 2.0

    for i, ax in enumerate(axes):
        _disable_axis_offsets(ax)
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
            ax.set_title(
                f'{source_name} | SPW {spw_meta.get("spw_id", spw_key)} Moment 0',
                fontsize=title_fontsize,
            )
            continue
        img = np.load(mom0_path)
        finite_values = np.asarray(img)[np.isfinite(img)]
        if finite_values.size:
            vmax = float(np.max(finite_values))
            vmin = -0.1 * vmax
            if vmin >= vmax:
                vmin = float(np.min(finite_values))
        else:
            vmin, vmax = 0.0, 1.0
        im = ax.imshow(img, origin='lower', vmin=vmin, vmax=vmax)
        ax.set_title(
            f'{source_name} | SPW {spw_meta.get("spw_id", spw_key)} Moment 0',
            fontsize=title_fontsize,
        )
        colorbar = fig.colorbar(im, ax=ax, shrink=0.8)
        _disable_axis_offsets(colorbar.ax)
        colorbar.ax.tick_params(labelsize=plot_fontsize)

        ax.tick_params(axis='both', labelsize=plot_fontsize)
    fig.tight_layout()
    return True


def plot_evidence_with_lines(
    res: dict[str, Any],
    source_name: str | None = None,
    source_id: int | None = None,
    field_id: int | None = None,
    min_region_snr: float = 7.0,
    min_neg_region_snr: float | None = None,
    region_label_fontsize: int | str | None = None,
    spw_key: str | None = None,
) -> bool:
    source_name = _resolve_source_name(res, source_name, source_id)
    if not has_valid_source_spw(res, source_name, field_id, spw_key):
        return False

    spw_keys = _plot_spw_keys(res, spw_key)
    n = len(spw_keys)
    fig, axes = plt.subplots(n, 1, figsize=(12, max(4.0, 3.5 * n)), sharex=False)
    axes = [axes] if n == 1 else list(axes)
    panel_limits = []
    roi_annotations = {id(ax): [] for ax in axes}
    metadata_annotations = {id(ax): [] for ax in axes}
    base_fontsize = float(plt.rcParams.get('font.size', 10.0))
    plot_fontsize = base_fontsize + 1.0
    title_fontsize = base_fontsize + 2.0
    label_fontsize = base_fontsize + 1.0
    if region_label_fontsize is None:
        region_label_fontsize = plot_fontsize
    if min_neg_region_snr is None:
        min_neg_region_snr = float(min_region_snr)

    for ax, spw_key in zip(axes, spw_keys):
        _disable_axis_offsets(ax)
        spw_meta = res['inventory']['science_spws'][spw_key]
        src_spw = _source_spw_block(res, source_name, spw_key)
        if not src_spw:
            ax.axis('off')
            continue
        try:
            block = _select_product_block(src_spw, field_id)
        except (KeyError, TypeError):
            ax.axis('off')
            continue
        evid = (block.get('spectra') or {}).get('evidence')
        if evid is None or np.asarray(evid).size == 0:
            ax.axis('off')
            continue
        nchan = len(evid)
        x = _channel_to_freq_ghz(spw_meta, nchan)
        if x is None:
            x = np.arange(nchan, dtype=np.float64)
            xlabel = 'Channel'
            freq_axis = False
        else:
            xlabel = 'Frequency (GHz)'
            freq_axis = True
        ax.plot(x, evid, color='black', lw=1.0, label='Evidence')
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
        _add_channel_axis(ax, x, nchan, label_fontsize)

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
            annotation = ax.text(
                mid,
                y_text,
                _region_label(line_peak_snr[i]),
                ha='center',
                va='bottom',
                fontsize=region_label_fontsize,
            )
            roi_annotations[id(ax)].append(annotation)

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
            annotation = ax.text(
                mid,
                y_text,
                _region_label(neg_line_peak_snr[i]),
                ha='center',
                va='bottom',
                fontsize=region_label_fontsize,
                color='royalblue',
            )
            roi_annotations[id(ax)].append(annotation)

        y_top = max(
            ymax + 0.18 * yrange,
            bar_y0 + (level_max_used + 1) * level_dy + 2.0 * label_dy,
            neg_bar_base + (neg_level_max_used + 1) * level_dy + 2.0 * label_dy,
        )
        y_bot = ymin - 0.06 * yrange
        panel_limits.append((y_bot, y_top))
        ax.set_title(
            f'{source_name} | SPW {spw_meta.get("spw_id", spw_key)} Evidence Spectrum (LSRK frame)',
            fontsize=title_fontsize,
        )
        ax.set_ylabel(r'Evidence [$\sigma$]', fontsize=label_fontsize)
        lw_note = _linewidth_note(spw_meta, block)
        if lw_note:
            annotation = ax.text(
                0.01,
                0.95,
                lw_note,
                transform=ax.transAxes,
                ha='left',
                va='top',
                fontsize=plot_fontsize,
                color='dimgray',
                bbox={'boxstyle': 'round,pad=0.2', 'facecolor': 'white', 'alpha': 0.6, 'edgecolor': 'none'},
            )
            metadata_annotations[id(ax)].append(annotation)
        qc_note = _roi_qc_note(block)
        if qc_note:
            annotation = ax.text(
                0.01,
                0.85,
                qc_note,
                transform=ax.transAxes,
                ha='left',
                va='top',
                fontsize=plot_fontsize,
                color='dimgray',
                bbox={'boxstyle': 'round,pad=0.2', 'facecolor': 'white', 'alpha': 0.55, 'edgecolor': 'none'},
            )
            metadata_annotations[id(ax)].append(annotation)
        ax.grid(alpha=0.2)
    if axes:
        axes[-1].set_xlabel(
            'Frequency (GHz, LSRK)' if xlabel == 'Frequency (GHz)' else xlabel,
            fontsize=label_fontsize,
        )
        common_ymin = min(limit[0] for limit in panel_limits)
        common_ymax = max(limit[1] for limit in panel_limits)
        for ax in axes:
            ax.set_ylim(common_ymin, common_ymax)
            ax.tick_params(axis='both', labelsize=plot_fontsize)
        legend_handles = [
            Line2D([0], [0], color='black', lw=1.0, label='Evidence'),
            Line2D([0], [0], color='firebrick', lw=3.0, label='Positive ROI'),
            Line2D([0], [0], color='royalblue', lw=3.0, label='Negative ROI'),
        ]
    fig.tight_layout()
    if axes:
        _move_metadata_away_from_roi(
            fig,
            metadata_annotations[id(axes[0])],
            roi_annotations[id(axes[0])],
        )
        _add_legend_avoiding_annotations(
            fig,
            axes[0],
            legend_handles,
            roi_annotations[id(axes[0])] + metadata_annotations[id(axes[0])],
            plot_fontsize,
        )
    return True


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
