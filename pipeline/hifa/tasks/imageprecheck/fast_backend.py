from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
import os
import math
import shutil
import tempfile
import time

import numpy as np

import pipeline.infrastructure as infrastructure
import pipeline.domain.measures as measures
import pipeline.infrastructure.utils as utils
from pipeline.infrastructure import casa_tools
from pipeline.hif.heuristics import mosaicoverlap

LOG = infrastructure.get_logger(__name__)

SAMPLE_SPACING_HZ = 500e6


@dataclass(frozen=True)
class SampleSpec:
    msname: str
    field_id: int
    virtual_spw: int
    real_spw: int
    channel_index: int
    channel_width_hz: float
    chunk_bw_hz: float
    center_freq_hz: float
    scanids: str
    taql: str


def _parse_channel_ranges(selection: str, nchan: int) -> list[tuple[int, int]]:
    if selection in ('', 'NONE', 'ALL', 'ALLCONT'):
        return [(0, nchan - 1)]

    ranges = []
    for part in selection.split(';'):
        part = part.strip()
        if not part:
            continue
        if '~' in part:
            start_s, end_s = part.split('~', 1)
            start = max(0, min(nchan - 1, int(float(start_s))))
            end = max(0, min(nchan - 1, int(float(end_s))))
        else:
            start = end = max(0, min(nchan - 1, int(float(part))))
        if start <= end:
            ranges.append((start, end))
        else:
            ranges.append((end, start))
    return ranges


def _contiguous_runs(indices: list[int]) -> list[list[int]]:
    if not indices:
        return []
    runs = [[indices[0]]]
    for idx in indices[1:]:
        if idx == runs[-1][-1] + 1:
            runs[-1].append(idx)
        else:
            runs.append([idx])
    return runs


def _make_psf_from_weights(total_weights: np.ndarray) -> np.ndarray:
    # Match the prototype behavior here so CASA fitpsf sees the same
    # singleton-axis array shape it was tuned against.
    psf = np.abs(np.array([np.fft.fftshift(np.fft.fft2(np.fft.fftshift(total_weights))).T]).T)
    peak = np.max(psf)
    if peak > 0:
        psf /= peak
    return psf


def _create_briggsbw_grid(npix_x: int, npix_y: int, frac_bw: float) -> np.ndarray:
    uvdist_grid = np.sqrt(np.add.outer(np.arange(-(npix_x / 2.0), (npix_x / 2.0), 1.0) ** 2,
                                       np.arange(-(npix_y / 2.0), (npix_y / 2.0), 1.0) ** 2))
    r_nu_grid = frac_bw * uvdist_grid
    corr_factor_grid = r_nu_grid + 0.5
    transition_grid = (4.0 - r_nu_grid) / (4.0 - 2.0 * r_nu_grid)
    corr_factor_grid[corr_factor_grid < 1.5] = transition_grid[corr_factor_grid < 1.5]
    return corr_factor_grid


def _briggs_weight(grid: np.ndarray, robust: float, corr_factor_grid=1.0):
    grid = np.asarray(grid, dtype=float)
    grid_sq = grid**2
    denom = np.sum(grid_sq) / np.sum(grid) if np.sum(grid) > 0 else 0.0
    if denom <= 0.0:
        return None, None

    f_sq = ((5 * 10 ** (-robust)) ** 2) / denom
    robust_wgts = 1.0 / (1.0 + grid / corr_factor_grid * f_sq)
    robust_wgts[grid <= 0] = 0.0
    imaging_wgts = robust_wgts * grid
    sens_wgts = robust_wgts**2 * grid
    sens_factor = np.sqrt(np.sum(sens_wgts) * np.sum(grid)) / np.sum(imaging_wgts)
    return imaging_wgts, sens_factor


class FastImagePrecheckBackend:
    """Standalone imageprecheck backend.

    The backend keeps the PL shell and selection logic, but caches a sparse
    set of gridded weights so robust values can be re-evaluated without
    repeating CASA gridding.
    """

    def __init__(
            self,
            inputs,
            image_heuristics,
            repr_field,
            repr_source,
            repr_spw,
            reprBW_mode,
            cont_spw,
            array,
            robust_values,
            primary_beam_size,
            gridder,
            field_ids,
            repr_bandwidth_hz,
            repr_frac_bw,
            single_continuum=False,
            sample_spacing_hz=SAMPLE_SPACING_HZ):
        self.inputs = inputs
        self.image_heuristics = image_heuristics
        self.repr_field = repr_field
        self.repr_source = repr_source
        self.repr_spw = int(repr_spw)
        self.reprBW_mode = reprBW_mode
        self.cont_spw = cont_spw
        self.array = array
        self.robust_values = robust_values
        self.primary_beam_size = primary_beam_size
        self.gridder = gridder
        self.field_ids = field_ids
        self.repr_bandwidth_hz = float(repr_bandwidth_hz)
        self.repr_frac_bw = float(repr_frac_bw)
        self.single_continuum = single_continuum
        self.sample_spacing_hz = float(sample_spacing_hz)

        self._cqa = casa_tools.quanta
        self._ms_by_name = {msname: self.image_heuristics.observing_run.get_ms(msname) for msname in self.inputs.vis}
        self._phasecenter = self._derive_phasecenter()
        self._center_field_ids = self.image_heuristics.center_field_ids(
            self.inputs.vis, self.repr_field, 'TARGET', self._phasecenter)
        self._mosweight = self.image_heuristics.mosweight('TARGET', self.repr_field)

    def _derive_phasecenter(self):
        try:
            _, phasecenter = self.image_heuristics.phasecenter(self.field_ids, vislist=self.inputs.vis)
            return phasecenter
        except Exception:
            return None

    def _mode_selection_inputs(self, mode):
        if mode == 'repBW':
            return str(self.repr_spw), {}, self.repr_bandwidth_hz

        spw = self.cont_spw

        # Use existing PL cont.dat / linesfile handling if present.
        spwsel_lsrk = {}
        cont_ranges_spwsel, _, _, _ = self.image_heuristics.cont_ranges_spwsel()
        selected_spws = [int(s) for s in spw.split(',') if str(s).strip() != '']
        for spw_id in selected_spws:
            spwsel_lsrk[f'spw{spw_id}'] = cont_ranges_spwsel.get(self.repr_source, {}).get(str(spw_id), 'NONE')

        fake_inputs = SimpleNamespace(
            vis=self.inputs.vis,
            field=self.repr_field,
            intent='TARGET',
            spw=spw,
            phasecenter=self._phasecenter,
            spwsel_lsrk=spwsel_lsrk,
        )
        try:
            if self.image_heuristics.contfile and os.path.isfile(self.image_heuristics.contfile):
                _, _, _, spw_topo_chan_param_dict, _, aggregate_topo_bw, _ = \
                    self.image_heuristics.calc_topo_ranges(fake_inputs)
                return spw, spw_topo_chan_param_dict, float(self._cqa.getvalue(self._cqa.convert(aggregate_topo_bw, 'Hz'))[0])
        except Exception as exc:
            LOG.info('Falling back to full-spw selection for %s: %s', mode, exc)

        try:
            topo_dict = {}
            for msname in self.inputs.vis:
                topo_dict[os.path.basename(msname)] = {}
                for spw_id in selected_spws:
                    ms = self._ms_by_name[msname]
                    real_spw = self.image_heuristics.observing_run.virtual2real_spw_id(spw_id, ms)
                    if real_spw is None:
                        continue
                    spw_obj = ms.get_spectral_window(real_spw)
                    topo_dict[os.path.basename(msname)][spw_id] = f'0~{spw_obj.num_channels - 1}'
            total_bw = 0.0
            for spw_id in selected_spws:
                msname = self.image_heuristics.get_ref_msname(spw_id)
                ms = self._ms_by_name[msname]
                real_spw = self.image_heuristics.observing_run.virtual2real_spw_id(spw_id, ms)
                spw_obj = ms.get_spectral_window(real_spw)
                total_bw += float(spw_obj.bandwidth.to_units(measures.FrequencyUnits.HERTZ))
            aggregate_bw = float(self._cqa.getvalue(self._cqa.convert(self.image_heuristics.aggregate_bandwidth(selected_spws), 'Hz'))[0])
            if aggregate_bw > 0.0:
                total_bw = aggregate_bw
            return spw, topo_dict, total_bw
        except Exception as exc:
            LOG.info('Falling back to empty selection for %s after selection failure: %s', mode, exc)
            topo_dict = {}
            for msname in self.inputs.vis:
                topo_dict[os.path.basename(msname)] = {}
            return spw, topo_dict, 0.0

    def _channel_info(self, ms, real_spw):
        spw_obj = ms.get_spectral_window(real_spw)
        channel_centers = np.array([
            float(chan.getCentreFrequency().convert_to(measures.FrequencyUnits.HERTZ).value)
            for chan in spw_obj.channels
        ], dtype=float)
        channel_widths = np.array([
            abs(float(chan.getWidth().convert_to(measures.FrequencyUnits.HERTZ).value))
            for chan in spw_obj.channels
        ], dtype=float)
        return spw_obj, channel_centers, channel_widths

    def _representative_channel(self, channel_flags, nchan):
        if nchan <= 0:
            return None

        center = int(nchan / 2)
        if len(channel_flags) == 0:
            return center

        if not channel_flags[center]:
            return center

        for offset in range(1, nchan):
            left = center - offset
            right = center + offset
            if left >= 0 and not channel_flags[left]:
                return left
            if right < nchan and not channel_flags[right]:
                return right

        return None

    def _create_temp_psf_file(self, seed_sample, cell, imsize):
        temp_dir = tempfile.mkdtemp(prefix='imageprecheck_psf_', dir=os.getcwd())
        temp_psf_file = os.path.join(temp_dir, 'scratch.psf')

        with casa_tools.SelectvisReader(seed_sample.msname,
                                        spw=f'{seed_sample.real_spw}:{seed_sample.channel_index}',
                                        field=seed_sample.field_id,
                                        scan=seed_sample.scanids,
                                        taql=seed_sample.taql) as imTool:
            imTool.defineimage(mode='mfs',
                               spw=seed_sample.real_spw,
                               cellx=cell[0],
                               celly=cell[0],
                               nx=imsize[0],
                               ny=imsize[1])
            imTool.makeimage(type='psf', image=temp_psf_file)

        return temp_dir, temp_psf_file

    def _fit_psf(self, seed_sample, psf_array, cell, imsize, temp_psf_file):
        try:
            with casa_tools.SelectvisReader(seed_sample.msname,
                                            spw=f'{seed_sample.real_spw}:{seed_sample.channel_index}',
                                            field=seed_sample.field_id,
                                            scan=seed_sample.scanids,
                                            taql=seed_sample.taql) as imTool:
                imTool.defineimage(mode='mfs',
                                   spw=seed_sample.real_spw,
                                   cellx=cell[0],
                                   celly=cell[0],
                                   nx=imsize[0],
                                   ny=imsize[1])
                with casa_tools.ImageReader(temp_psf_file) as image_tool:
                    image_tool.putregion(pixels=psf_array)
                fit_result = imTool.fitpsf(psf=temp_psf_file)
            return {
                'major': fit_result[1],
                'minor': fit_result[2],
                'positionangle': fit_result[3],
            }
        except Exception as exc:
            LOG.info('PSF fit failed for %s: %s', temp_psf_file, exc)
            return 'invalid'

    def _sample_specs_for_mode(self, mode):
        spw_spec, topo_dict, selected_bw_hz = self._mode_selection_inputs(mode)
        sample_specs = []

        for msname in self.inputs.vis:
            ms = self._ms_by_name[msname]
            field_id = self._center_field_ids[self.inputs.vis.index(msname)]
            if field_id in (-1, None):
                continue

            scanids = [str(scan.id) for scan in ms.scans if 'TARGET' in scan.intents and field_id in [fld.id for fld in scan.fields]]
            if not scanids:
                continue
            scanids = ','.join(scanids)

            antenna_ids = self.image_heuristics.antenna_ids('TARGET', [os.path.basename(msname)])
            taql = f"{'||'.join(['ANTENNA1==%d' % i for i in antenna_ids[os.path.basename(msname)]])}&&" \
                   f"{'||'.join(['ANTENNA2==%d' % i for i in antenna_ids[os.path.basename(msname)]])}"

            for spw_id in [int(s) for s in spw_spec.split(',') if s.strip() != '']:
                real_spw = self.image_heuristics.observing_run.virtual2real_spw_id(spw_id, ms)
                if real_spw is None:
                    continue

                spw_obj, channel_centers, channel_widths = self._channel_info(ms, real_spw)
                channel_flags = self.image_heuristics.get_channel_flags(msname, field_id, spw_id)

                if mode == 'repBW':
                    chan_index = self._representative_channel(channel_flags, spw_obj.num_channels)
                    if chan_index is None:
                        continue
                    sample_specs.append(
                        SampleSpec(
                            msname=msname,
                            field_id=int(field_id),
                            virtual_spw=int(spw_id),
                            real_spw=int(real_spw),
                            channel_index=int(chan_index),
                            channel_width_hz=float(channel_widths[chan_index]),
                            chunk_bw_hz=float(self.repr_bandwidth_hz),
                            center_freq_hz=float(channel_centers[chan_index]),
                            scanids=scanids,
                            taql=taql,
                        )
                    )
                    continue

                selection = topo_dict.get(os.path.basename(msname), {}).get(spw_id, '')
                ranges = _parse_channel_ranges(selection, spw_obj.num_channels)

                for start, stop in ranges:
                    allowed = [idx for idx in range(start, stop + 1) if idx < len(channel_centers) and (len(channel_flags) == 0 or not channel_flags[idx])]
                    for run in _contiguous_runs(allowed):
                        if not run:
                            continue

                        run_width = float(np.sum(channel_widths[run]))
                        if run_width <= 0.0:
                            continue

                        n_samples = max(1, int(math.ceil(run_width / self.sample_spacing_hz)))
                        n_samples = min(n_samples, len(run))
                        sample_edges = np.linspace(0, len(run), n_samples + 1)
                        chosen = []
                        for i in range(n_samples):
                            left = int(math.floor(sample_edges[i]))
                            right = int(math.ceil(sample_edges[i + 1])) - 1
                            left = max(0, min(len(run) - 1, left))
                            right = max(0, min(len(run) - 1, right))
                            mid_index = int(round(0.5 * (left + right)))
                            chosen.append(run[mid_index])

                        # De-duplicate while preserving order.
                        dedup = []
                        for idx in chosen:
                            if idx not in dedup:
                                dedup.append(idx)
                        if not dedup:
                            continue

                        chunk_bw_hz = run_width / len(dedup)
                        for chan_index in dedup:
                            sample_specs.append(
                                SampleSpec(
                                    msname=msname,
                                    field_id=int(field_id),
                                    virtual_spw=int(spw_id),
                                    real_spw=int(real_spw),
                                    channel_index=int(chan_index),
                                    channel_width_hz=float(channel_widths[chan_index]),
                                    chunk_bw_hz=float(chunk_bw_hz),
                                    center_freq_hz=float(channel_centers[chan_index]),
                                    scanids=scanids,
                                    taql=taql,
                                )
                            )

        sample_specs.sort(key=lambda s: s.center_freq_hz)
        return spw_spec, sample_specs, selected_bw_hz

    def _seed_cell_and_imsize(self, sample_specs):
        if not sample_specs:
            raise RuntimeError('No valid samples available for imageprecheck seed')

        seed_sample = max(sample_specs, key=lambda s: s.center_freq_hz)
        ms = self._ms_by_name[seed_sample.msname]
        aipsfieldofview = '%4.1farcsec' % (2.0 * np.asarray(self.primary_beam_size).item())
        t0 = time.perf_counter()
        with casa_tools.SelectvisReader(seed_sample.msname,
                                        spw=f'{seed_sample.real_spw}:{seed_sample.channel_index}',
                                        field=seed_sample.field_id,
                                        scan=seed_sample.scanids,
                                        taql=seed_sample.taql) as imTool:
            rtn = imTool.advise(takeadvice=False, amplitudeloss=0.5, fieldofview=aipsfieldofview)
        advise_time = time.perf_counter() - t0
        LOG.info('imageprecheck seed advise() on %s spw %s chan %s took %.3fs',
                 os.path.basename(seed_sample.msname), seed_sample.real_spw, seed_sample.channel_index, advise_time)

        if not rtn[0]:
            raise RuntimeError('imager.advise failed for reduced imageprecheck seed selection')

        qa = casa_tools.quanta
        cellv = qa.convert(rtn[2], 'arcsec')['value']
        cellv /= (0.5 * 5.0)
        cell = ['%.2garcsec' % cellv]
        imsize = self.image_heuristics.imsize(
            self.field_ids,
            cell,
            self.primary_beam_size,
            centreonly=False,
            intent='TARGET')
        return seed_sample, cell, imsize

    def _evaluate_mode(self, mode, sample_specs, cell, imsize, selection_bw_hz, corr_factor_grid,
                       temp_psf_file, seed_sample):
        if not sample_specs:
            raise RuntimeError(f'No valid samples available for {mode}')

        total_bandwidth_hz = float(selection_bw_hz or 0.0)
        sample_cache = []
        timing_start = time.perf_counter()
        selection_sum_bw_hz = 0.0

        for sample in sample_specs:
            try:
                with casa_tools.SelectvisReader(sample.msname,
                                                spw=f'{sample.real_spw}:{sample.channel_index}',
                                                field=sample.field_id,
                                                scan=sample.scanids,
                                                taql=sample.taql) as imTool:
                    imTool.defineimage(mode='mfs',
                                       spw=sample.real_spw,
                                       cellx=cell[0],
                                       celly=cell[0],
                                       nx=imsize[0],
                                       ny=imsize[1])
                    imTool.weight(type='uniform')
                    gwgts = np.squeeze(np.asarray(imTool.getweightgrid(), dtype=float))
                    imTool.weight(type='natural')
                    nat_sens = float(imTool.apparentsens()[1])
                    if not np.isfinite(nat_sens) or nat_sens <= 0.0:
                        continue

                    bw_scale = sample.chunk_bw_hz / sample.channel_width_hz if sample.channel_width_hz > 0 else 1.0
                    gwgts_scaled = gwgts * bw_scale
                    nat_sens_scaled = nat_sens * math.sqrt(sample.channel_width_hz / sample.chunk_bw_hz) if sample.chunk_bw_hz > 0 else nat_sens
                    nchan_equiv = max(1, int(round(sample.chunk_bw_hz / sample.channel_width_hz))) if sample.channel_width_hz > 0 else 1
                    bw_corr_factor = 1.0
                    try:
                        bw_corr_factor, _, _, _ = self.image_heuristics.get_bw_corr_factor(
                            self._ms_by_name[sample.msname], sample.virtual_spw, nchan_equiv)
                    except Exception as exc:
                        LOG.info('Could not determine bandwidth correction for ms=%s spw=%s nchan=%s: %s',
                                 os.path.basename(sample.msname), sample.virtual_spw, nchan_equiv, exc)
                    nat_sens_scaled *= bw_corr_factor

                    if self.gridder == 'mosaic':
                        ms = self._ms_by_name[sample.msname]
                        source_matches = [f.source.name for f in ms.fields
                                          if (utils.dequote(f.name) == utils.dequote(self.repr_field) and 'TARGET' in f.intents)]
                        if source_matches:
                            source_name = source_matches[0]
                            if source_name.isdigit():
                                source_name = '"{}"'.format(source_name)
                            diameter = np.median([a.diameter for a in ms.antennas])
                            overlap_factor = mosaicoverlap.mosaicOverlapFactorMS(ms, source_name, sample.virtual_spw, diameter)
                            nat_sens_scaled /= overlap_factor
                        else:
                            LOG.info('No mosaic source match for %s field %s; leaving overlap factor at unity',
                                     os.path.basename(sample.msname), self.repr_field)

                    sample_cache.append({
                        'sample': sample,
                        'gwgts': gwgts_scaled,
                        'nat_sens': nat_sens_scaled,
                    })
                    selection_sum_bw_hz += float(sample.chunk_bw_hz)
            except Exception as exc:
                LOG.info('Skipping sample ms=%s spw=%s chan=%s: %s',
                         os.path.basename(sample.msname), sample.real_spw, sample.channel_index, exc)
                continue

        build_time = time.perf_counter() - timing_start
        LOG.info('imageprecheck %s cached %d sparse samples in %.3fs', mode, len(sample_cache), build_time)

        if not sample_cache:
            raise RuntimeError(f'No valid imageprecheck samples collected for {mode}')

        combined_gwgts = None
        combined_nat_sens_terms = []
        for entry in sample_cache:
            combined_gwgts = entry['gwgts'] if combined_gwgts is None else combined_gwgts + entry['gwgts']
            if np.isfinite(entry['nat_sens']) and entry['nat_sens'] > 0.0:
                combined_nat_sens_terms.append(entry['nat_sens'])

        if combined_gwgts is None or not combined_nat_sens_terms:
            raise RuntimeError(f'Unable to build combined weight grid for {mode}')

        combined_nat_sens = 1.0 / np.sqrt(np.sum(1.0 / np.array(combined_nat_sens_terms) ** 2))

        results = {}
        for robust in self.robust_values:
            t0 = time.perf_counter()
            total_weights, sens_factor = _briggs_weight(combined_gwgts, robust, corr_factor_grid)

            if total_weights is None or sens_factor is None:
                beam = 'invalid'
                sensitivity = None
                sens_bw = None
            else:
                psf = _make_psf_from_weights(total_weights)
                beam = self._fit_psf(seed_sample, psf, cell, imsize, temp_psf_file)
                if beam == 'invalid':
                    sensitivity = None
                    sens_bw = None
                else:
                    sensitivity = combined_nat_sens * sens_factor
                    if mode == 'aggBW' and total_bandwidth_hz > 0.0 and selection_sum_bw_hz > total_bandwidth_hz:
                        sensitivity *= math.sqrt(selection_sum_bw_hz / total_bandwidth_hz)
                    sens_bw = total_bandwidth_hz

            elapsed = time.perf_counter() - t0
            LOG.info('imageprecheck %s robust %.1f evaluated in %.3fs', mode, robust, elapsed)
            results[robust] = {
                'beam': beam,
                'cell': cell,
                'imsize': imsize,
                'sensitivity': sensitivity,
                'sens_bw_hz': sens_bw,
                'sample_count': len(sample_cache),
                'selection_bw_hz': total_bandwidth_hz,
            }

        return results

    def run(self):
        mode_results = {}
        timings = {}

        t0 = time.perf_counter()
        rep_spw_spec, rep_samples, rep_bw_hz = self._sample_specs_for_mode('repBW')
        agg_spw_spec, agg_samples, agg_bw_hz = self._sample_specs_for_mode('aggBW')
        timings['sample_build'] = time.perf_counter() - t0

        t_seed = time.perf_counter()
        seed_sample, cell, imsize = self._seed_cell_and_imsize(rep_samples or agg_samples)
        timings['seed'] = time.perf_counter() - t_seed

        temp_dir = None
        temp_psf_file = None
        try:
            temp_dir, temp_psf_file = self._create_temp_psf_file(seed_sample, cell, imsize)
            rep_corr_factor_grid = _create_briggsbw_grid(imsize[0], imsize[1], self.repr_frac_bw) \
                if self.repr_frac_bw > 0.0 else 1.0

            t1 = time.perf_counter()
            mode_results['repBW'] = self._evaluate_mode('repBW', rep_samples, cell, imsize, rep_bw_hz,
                                                        rep_corr_factor_grid, temp_psf_file, seed_sample)
            mode_results['aggBW'] = self._evaluate_mode('aggBW', agg_samples, cell, imsize, agg_bw_hz,
                                                        1.0, temp_psf_file, seed_sample)
            timings['evaluate'] = time.perf_counter() - t1
        finally:
            if temp_dir and os.path.isdir(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

        LOG.info('imageprecheck backend timings: sample build %.3fs, evaluation %.3fs',
                 timings['sample_build'], timings['evaluate'])

        return {
            'seed_sample': seed_sample,
            'seed_cell': cell,
            'seed_imsize': imsize,
            'mode_results': mode_results,
            'timings': timings,
            'rep_spw_spec': rep_spw_spec,
            'rep_bw_hz': rep_bw_hz,
            'agg_spw_spec': agg_spw_spec,
            'agg_bw_hz': agg_bw_hz,
        }
