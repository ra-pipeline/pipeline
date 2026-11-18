"""Regression test for compute_zd_telmjd_for_ms.

Records exact output values from main at commit c79f0ba71 to guard against
regressions when optimising the CASA measures-based implementation.

Updated for PIPE-3189: timestamps are decimated onto a uniform ~1s target
grid to avoid the unnecessarily dense SQLD sampling grid, with a floor of
50 retained timestamps so a short field keeps its resolution.

Updated for PIPE-3305: the zenith-distance check compares the level of the
series with its shape. The geodetic tables behind measures() change weekly.
One update moves every value by the same 2.1e-08 deg, with a spread of
9.8e-10 deg, and moves consecutive differences by at most 5.6e-10 deg. The
level is not stable, so a fixed relative tolerance on each value is the wrong
guard: rel=1e-5 is 2.27e-04 deg at 22.675 deg, larger than the smallest step
of the series (2.1176e-04 deg). It accepts a value paired with the next
timestamp for 5 of the 58 adjacent pairs.
"""
import datetime
import warnings

import numpy as np
import pytest

from pipeline.infrastructure import casa_tools
from pipeline.infrastructure.tablereader import MeasurementSetReader
from pipeline.infrastructure.renderer.htmlrenderer import (
    _decimate_timestamps,
    compute_zd_telmjd_for_ms,
)
from pipeline.infrastructure.utils.casa_data import get_measures_fingerprint

MS_NAME = casa_tools.utils.resolve(
    "pl-unittest/uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.ms"
)

# Expected zenith-distance values (degrees) after decimation onto the ~1s
# target grid (PIPE-3189).
# fmt: off
_ZDS = [
    22.674321225165677,
    22.674773617423011,
    22.675000172283028,
    22.675453998443540,
    22.675908780715012,
    22.676364519041385,
    22.677393423525434,
    22.677852267574703,
    22.678312066683262,
    22.678772821793711,
    22.679003557769615,
    22.679465746275614,
    22.680509162209933,
    22.680741689156665,
    22.681207459691386,
    22.681440703265075,
    22.681907905971624,
    22.682376064232631,
    22.682610501614711,
    22.688258545305636,
    22.688679320242041,
    22.689100827039013,
    22.689523063034240,
    22.689946030812887,
    22.690157788220976,
    22.690794156299898,
    22.691219314450919,
    22.691645203171596,
    22.692071821625476,
    22.692499171364517,
    22.692927249954650,
    22.693356059749938,
    22.693785598575307,
    22.694431277260762,
    22.694646867957381,
    22.695078597629955,
    22.695511056965412,
    22.695944247268717,
    22.696378165802447,
    22.696812815221968,
    22.697248193864752,
    22.697684302500281,
    22.698121140000090,
    22.698777765665348,
    22.698997004953945,
    22.699436032600186,
    22.699875788664055,
    22.700316274742651,
    22.700757489972187,
    22.701199435409116,
    22.701642109085881,
    22.702085512886388,
    22.702529645389504,
    22.703197211678173,
    22.703420097985255,
    22.703866418269691,
    22.704313467358521,
    22.704761246043255,
    22.705209752608432,
]
# fmt: on

_TELMJDS = [
    "2017-09-11T06:22:06.192000+00:00",
    "2017-09-11T06:22:07.344000+00:00",
    "2017-09-11T06:22:07.920000+00:00",
    "2017-09-11T06:22:09.072000+00:00",
    "2017-09-11T06:22:10.224000+00:00",
    "2017-09-11T06:22:11.376000+00:00",
    "2017-09-11T06:22:13.968000+00:00",
    "2017-09-11T06:22:15.120000+00:00",
    "2017-09-11T06:22:16.271999+00:00",
    "2017-09-11T06:22:17.424000+00:00",
    "2017-09-11T06:22:18+00:00",
    "2017-09-11T06:22:19.152000+00:00",
    "2017-09-11T06:22:21.743999+00:00",
    "2017-09-11T06:22:22.320000+00:00",
    "2017-09-11T06:22:23.472000+00:00",
    "2017-09-11T06:22:24.048000+00:00",
    "2017-09-11T06:22:25.200000+00:00",
    "2017-09-11T06:22:26.352000+00:00",
    "2017-09-11T06:22:26.928000+00:00",
    "2017-09-11T06:22:40.632001+00:00",
    "2017-09-11T06:22:41.639999+00:00",
    "2017-09-11T06:22:42.648001+00:00",
    "2017-09-11T06:22:43.655999+00:00",
    "2017-09-11T06:22:44.664001+00:00",
    "2017-09-11T06:22:45.168000+00:00",
    "2017-09-11T06:22:46.680000+00:00",
    "2017-09-11T06:22:47.688000+00:00",
    "2017-09-11T06:22:48.696000+00:00",
    "2017-09-11T06:22:49.704000+00:00",
    "2017-09-11T06:22:50.712001+00:00",
    "2017-09-11T06:22:51.719999+00:00",
    "2017-09-11T06:22:52.728001+00:00",
    "2017-09-11T06:22:53.735999+00:00",
    "2017-09-11T06:22:55.248000+00:00",
    "2017-09-11T06:22:55.752000+00:00",
    "2017-09-11T06:22:56.760000+00:00",
    "2017-09-11T06:22:57.768000+00:00",
    "2017-09-11T06:22:58.776001+00:00",
    "2017-09-11T06:22:59.783999+00:00",
    "2017-09-11T06:23:00.792001+00:00",
    "2017-09-11T06:23:01.800000+00:00",
    "2017-09-11T06:23:02.808001+00:00",
    "2017-09-11T06:23:03.815999+00:00",
    "2017-09-11T06:23:05.328000+00:00",
    "2017-09-11T06:23:05.831999+00:00",
    "2017-09-11T06:23:06.840000+00:00",
    "2017-09-11T06:23:07.848000+00:00",
    "2017-09-11T06:23:08.856000+00:00",
    "2017-09-11T06:23:09.863999+00:00",
    "2017-09-11T06:23:10.872001+00:00",
    "2017-09-11T06:23:11.879999+00:00",
    "2017-09-11T06:23:12.888000+00:00",
    "2017-09-11T06:23:13.896000+00:00",
    "2017-09-11T06:23:15.408000+00:00",
    "2017-09-11T06:23:15.912000+00:00",
    "2017-09-11T06:23:16.920000+00:00",
    "2017-09-11T06:23:17.927999+00:00",
    "2017-09-11T06:23:18.936001+00:00",
    "2017-09-11T06:23:19.943999+00:00",
]


# PIPE-3305: two checks replace the old per-value relative tolerance.
# Level: one data refresh moves every value by the same 2.1e-08 deg (spread
# 9.8e-10 deg). Pattern: consecutive differences drift by at most 5.6e-10 deg,
# and the smallest step in the series is 2.1176e-04 deg.
_ZD_LEVEL_TOL = 1e-4  # deg, absorbs the constant offset a data refresh adds
_ZD_PATTERN_TOL = 1e-7  # deg, checks the shape after the offset is removed
_MEASURES_FP = '60ece9bd21e01000'  # fingerprint of the data these values came from


def _level_and_pattern(actual, expected):
    """Return the median level offset and the largest pattern residual, in degrees."""
    diffs = np.asarray(actual, dtype=float) - np.asarray(expected, dtype=float)
    offset = float(np.median(diffs))
    return offset, float(np.max(np.abs(diffs - offset)))


@pytest.fixture(scope='module')
def ms():
    return MeasurementSetReader.get_measurement_set(MS_NAME)


@pytest.mark.unit
class TestZdTelmjd:
    """Verify that compute_zd_telmjd_for_ms produces expected values."""

    def test_zd_values(self, ms):
        """Check the level and the pattern of the zenith-distance series."""
        result = compute_zd_telmjd_for_ms(ms)
        field = result[3]
        fingerprint = get_measures_fingerprint()
        offset, residual = _level_and_pattern(field['zd'], _ZDS)
        message = (
            f'zd series mismatch: level offset {offset:.3e} deg '
            f'(tolerance {_ZD_LEVEL_TOL:.1e} deg), worst pattern residual '
            f'{residual:.3e} deg (tolerance {_ZD_PATTERN_TOL:.1e} deg), '
            f'measures fingerprint {fingerprint} (recorded {_MEASURES_FP})'
        )
        assert abs(offset) < _ZD_LEVEL_TOL, message
        assert residual < _ZD_PATTERN_TOL, message

    def test_field_count(self, ms):
        result = compute_zd_telmjd_for_ms(ms)
        assert len(result) == 1

    def test_timestamp_count(self, ms):
        result = compute_zd_telmjd_for_ms(ms)
        assert len(result[3]['zd']) == 59
        assert len(result[3]['telmjd']) == 59

    def test_telmjd_exact(self, ms):
        result = compute_zd_telmjd_for_ms(ms)
        field = result[3]
        expected_dts = [
            datetime.datetime.fromisoformat(s)
            for s in _TELMJDS
        ]
        for i, (actual, expected) in enumerate(zip(field['telmjd'], expected_dts)):
            assert actual == expected, (
                f"telmjd[{i}] exact mismatch: {actual!r} != {expected!r}"
            )


@pytest.mark.unit
class TestMeasuresData:
    """Checks on the geodetic data behind the recorded values. No MS required."""

    def test_fingerprint_is_recorded(self):
        """Warn when the geodetic tables differ from the recorded reference."""
        fingerprint = get_measures_fingerprint()
        if fingerprint != _MEASURES_FP:
            warnings.warn(
                f'CASA measures data changed: fingerprint {fingerprint}, '
                f'recorded {_MEASURES_FP}. The level check absorbs a constant '
                'shift, but the recorded _ZDS values may need re-derivation.',
                stacklevel=2,
            )


@pytest.mark.unit
class TestZdSeriesChecks:
    """Property tests for the PIPE-3305 level and pattern checks. No MS required."""

    def test_single_value_shift_breaks_the_pattern(self):
        """One value off by 1e-6 deg fails the pattern check."""
        expected = list(_ZDS)
        expected[10] += 1e-6
        offset, residual = _level_and_pattern(_ZDS, expected)
        assert offset == pytest.approx(0.0, abs=1e-12), offset
        assert residual > _ZD_PATTERN_TOL, residual

    def test_uniform_shift_keeps_the_pattern(self):
        """A refresh that moves every value alike passes the pattern check."""
        actual = [v + 1e-6 for v in _ZDS]
        offset, residual = _level_and_pattern(actual, _ZDS)
        assert offset == pytest.approx(1e-6, abs=1e-12), offset
        assert residual < _ZD_PATTERN_TOL, residual
        assert abs(offset) < _ZD_LEVEL_TOL, offset

    def test_adjacent_swap_breaks_the_pattern(self):
        """Two values paired with the wrong timestamps fail the pattern check."""
        actual = list(_ZDS)
        actual[23], actual[24] = actual[24], actual[23]
        _, residual = _level_and_pattern(actual, _ZDS)
        assert residual > _ZD_PATTERN_TOL, residual

    def test_pattern_tolerance_stays_below_the_pairing_signal(self):
        """The pattern check must stay far below the smallest step of the series."""
        smallest_step = float(np.min(np.abs(np.diff(_ZDS))))
        assert _ZD_PATTERN_TOL < smallest_step / 1000, (
            f'pattern tolerance {_ZD_PATTERN_TOL} deg is not below one '
            f'thousandth of the smallest step {smallest_step:.3e} deg'
        )


@pytest.mark.unit
class TestDecimateTimestamps:
    """Property tests for the PIPE-3189 decimation. No MS required."""

    # Mirrors the min_count default of _decimate_timestamps.
    MIN_COUNT = 50

    @staticmethod
    def _dense(duration, dt=0.016):
        """Duration seconds sampled at the SQLD (16ms) rate."""
        return np.arange(0.0, duration, dt)

    def test_output_is_sorted_subset_of_input(self):
        """Only real input timestamps may be returned, in ascending order."""
        t = self._dense(100.0)
        out = _decimate_timestamps(t)
        assert np.all(np.diff(out) > 0)
        assert set(out).issubset(set(t))

    def test_endpoints_preserved(self):
        """The full time range must survive decimation."""
        t = self._dense(100.0)
        out = _decimate_timestamps(t)
        assert out[0] == t[0]
        assert out[-1] == t[-1]

    @pytest.mark.parametrize('duration', [2.0, 10.0, 30.0, 48.0])
    def test_short_dense_span_keeps_min_count(self, duration):
        """A short dense field keeps min_count points, it is not exempted."""
        # The floor must tighten the grid rather than fall back to no
        # decimation: a binary fallback hands a short-but-dense field all of
        # its samples back, re-opening the SQLD pathology for short dwells.
        t = self._dense(duration)
        out = _decimate_timestamps(t)
        assert len(out) >= self.MIN_COUNT, len(out)
        assert len(out) < len(t), 'field was not decimated at all'

    def test_long_span_uses_one_second_grid(self):
        """Spans longer than min_count seconds resolve to the 1s grid."""
        t = self._dense(100.0)
        out = _decimate_timestamps(t)
        gaps = np.diff(out)
        # The grid is 1s; snapping to 16ms samples shifts a point by <= dt.
        assert gaps.min() >= 1.0 - 0.016 - 1e-9
        assert gaps.max() <= 1.0 + 0.016 + 1e-9
        assert 100 <= len(out) <= 102

    def test_grid_spacing_not_inflated_by_coarse_sampling(self):
        """A 0.576s input must not round the 1s target up to 1.152s."""
        # A minimum-gap rule cannot hit a 1s target with 0.576s sampling and
        # has to skip every other sample, under-sampling by a third.
        t = np.arange(0.0, 73.75 + 1e-9, 0.576)
        out = _decimate_timestamps(t)
        mean_gap = (out[-1] - out[0]) / (len(out) - 1)
        assert mean_gap == pytest.approx(1.0, rel=0.05), mean_gap

    def test_sparse_input_is_untouched(self):
        """Input already sparser than the target is returned unchanged."""
        t = np.arange(0.0, 100.0, 1.5)
        assert np.array_equal(_decimate_timestamps(t), t)

    def test_unsorted_input_is_sorted_before_selection(self):
        """Unsorted input must not collapse during selection."""
        t = np.array([3.0, 1.0, 2.0, 1.5, 0.5])
        out = _decimate_timestamps(t)
        assert np.all(np.diff(out) >= 0)
        assert out[0] == t.min()
        assert out[-1] == t.max()

    def test_degenerate_inputs(self):
        """Single and zero-span inputs must not raise or divide by zero."""
        assert np.array_equal(_decimate_timestamps(np.array([5.0])), [5.0])
        # Every timestamp identical: one evaluation covers all of them.
        assert len(_decimate_timestamps(np.full(100, 5.0))) == 1

    def test_allocation_follows_time_not_sample_count(self):
        """Equal-duration bursts get equal points despite a 62x rate gap."""
        # A density-driven selector fails this: it would hand the 16ms burst
        # ~62x more points than the 1s burst.
        a = np.arange(0.0, 30.0, 0.016)  # 1875 samples at the SQLD rate
        b = np.arange(100.0, 130.0, 1.0)  # 30 samples at the continuum rate
        out = _decimate_timestamps(np.concatenate([a, b]))
        n_a = int(np.sum(out < 100.0))
        n_b = int(np.sum(out >= 100.0))
        assert abs(n_a - n_b) <= 1, f'equal bursts got {n_a} vs {n_b} points'
        assert n_a == pytest.approx(30, abs=2), n_a

    def test_mean_tracks_time_weighting_across_equal_bursts(self):
        """The returned series must be unbiased across equal-length bursts."""
        # The weblog zd_avg is a plain mean of the returned series, so any
        # per-burst phase error shows up directly in the published average.
        # A selector that keeps the first sample of every burst (the greedy
        # rule) restarts phase at each gap and is biased by up to ~0.005 deg.
        bursts = [np.arange(i * 100.0, i * 100.0 + 30.0, 0.016) for i in range(10)]
        t = np.concatenate(bursts)
        truth = float(np.mean([b[0] + (b[-1] - b[0]) / 2 for b in bursts]))
        out = _decimate_timestamps(t)
        assert out.mean() == pytest.approx(truth, rel=1e-4), f'mean {out.mean()} vs time-weighted {truth}'
