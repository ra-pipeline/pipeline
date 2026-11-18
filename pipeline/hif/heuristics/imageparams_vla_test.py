"""Tests for the VLA uvrange heuristic in ImageParamsHeuristicsVLA."""

from __future__ import annotations

from unittest import mock

import pytest

from pipeline.hif.heuristics.imageparams_vla import ImageParamsHeuristicsVLA

VISSTAT_PATH = 'pipeline.hif.heuristics.imageparams_vla.casa_tasks.visstat'

UV_STAT = {'DATA_DESC_ID=1': {'max': 3000.0, 'npts': 100.0}}
GOOD_AMP = {'mean': 0.5, 'npts': 1000.0}
# visstat output for a selection with no unflagged points
EMPTY_AMP = {'mean': 0.0, 'npts': 0.0}
ZERO_MEAN_AMP = {'mean': 0.0, 'npts': 10.0}


@pytest.fixture
def heuristics() -> ImageParamsHeuristicsVLA:
    """Fixture providing an ImageParamsHeuristicsVLA with a mocked observing run."""
    heuristics = ImageParamsHeuristicsVLA.__new__(ImageParamsHeuristicsVLA)
    heuristics.vislist = ['test_small.ms']

    spw = mock.MagicMock()
    spw.mean_frequency.to_units.return_value = 3.0e9
    ms = mock.MagicMock()
    ms.get_spectral_window.return_value = spw
    heuristics.observing_run = mock.MagicMock()
    heuristics.observing_run.get_ms.return_value = ms
    heuristics.observing_run.virtual2real_spw_id.side_effect = lambda spwid, _ms: int(spwid)
    return heuristics


def run_uvrange(
    heuristics: ImageParamsHeuristicsVLA, sbl_stats: dict, mbl_stats: dict, spwspec: str = '1'
) -> tuple[str | None, float | None]:
    """Run the uvrange heuristic with mocked visstat results.

    Args:
        heuristics: Heuristics instance under test.
        sbl_stats: visstat amplitude result for the short-baseline bin.
        mbl_stats: visstat amplitude result for the mid-baseline bin.
        spwspec: Comma-separated spw selection.

    Returns:
        The (uvrange, ratio) tuple returned by the heuristic.
    """
    jobs = [mock.MagicMock(**{'execute.return_value': r}) for r in (UV_STAT, sbl_stats, mbl_stats)]
    with mock.patch(VISSTAT_PATH, side_effect=jobs):
        return heuristics.uvrange(field='F', spwspec=spwspec, specmode='cont')


@pytest.mark.parametrize(
    'sbl_amp, mbl_amp',
    [
        pytest.param(GOOD_AMP, EMPTY_AMP, id='empty_mid_bin'),
        pytest.param(GOOD_AMP, ZERO_MEAN_AMP, id='zero_mean_mid_bin'),
    ],
)
def test_uvrange_falls_back_without_usable_data(
    heuristics: ImageParamsHeuristicsVLA, sbl_amp: dict, mbl_amp: dict
) -> None:
    """Verify an empty or zero-amplitude bin returns the full uvrange instead of raising."""
    result = run_uvrange(heuristics, {'DATA_DESC_ID=1': sbl_amp}, {'DATA_DESC_ID=1': mbl_amp})

    assert result == ('>0.0klambda', 1.0)


@pytest.mark.parametrize(
    'sbl_mean, expected_uvrange, expected_ratio',
    [
        pytest.param(1.5, '>1.5klambda', 3.0, id='above_threshold'),
        pytest.param(1.0, '>0.0klambda', 2.0, id='at_threshold'),
    ],
)
def test_uvrange_ignores_empty_spw_in_multi_spw_bin(
    heuristics: ImageParamsHeuristicsVLA, sbl_mean: float, expected_uvrange: str, expected_ratio: float
) -> None:
    """Verify an empty spw does not bias the ratio and only a ratio above 2 restricts the uvrange.
    """
    sbl_amp = {'mean': sbl_mean, 'npts': 1000.0}
    sbl = {'DATA_DESC_ID=1': sbl_amp, 'DATA_DESC_ID=2': sbl_amp}
    mbl = {'DATA_DESC_ID=1': GOOD_AMP, 'DATA_DESC_ID=2': EMPTY_AMP}

    uvrange, ratio = run_uvrange(heuristics, sbl, mbl, spwspec='1,2')

    assert uvrange == expected_uvrange
    assert ratio == pytest.approx(expected_ratio)
