"""Tests for ImageParamsHeuristics."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pipeline.hif.heuristics.imageparams_base import ImageParamsHeuristics


@pytest.fixture
def heuristics() -> ImageParamsHeuristics:
    """Provide an ImageParamsHeuristics instance with synthetic inputs."""
    return ImageParamsHeuristics(['uid___A002_X000000_X000.ms'], '0', None)


@pytest.mark.parametrize(
    ('start', 'width', 'nchan', 'expected'),
    [
        ('100.0GHz', '10.0MHz', 100, (100 * 10e6) / (100e9 + 0.5 * 99 * 10e6)),
        ('200.0GHz', '-10.0MHz', 50, (50 * 10e6) / (200e9 - 0.5 * 49 * 10e6)),
        ('100.0GHz', '1.0GHz', 1, 1e9 / 100e9),
        ({'value': 100.0, 'unit': 'GHz'}, {'value': 10.0, 'unit': 'MHz'}, 10, (10 * 10e6) / (100e9 + 0.5 * 9 * 10e6)),
    ],
)
def test_fractional_bw_valid(
    heuristics: ImageParamsHeuristics,
    start: str | dict[str, float | str],
    width: str | dict[str, float | str],
    nchan: int,
    expected: float,
) -> None:
    """Verify fractional bandwidth calculation for valid frequency grids."""
    result = heuristics.fractional_bw(start, width, nchan)
    assert result is not None
    assert result == pytest.approx(expected)


@pytest.mark.parametrize(
    ('start', 'width', 'nchan'),
    [
        ('', '10.0MHz', 100),
        ('100.0GHz', '', 100),
        (None, '10.0MHz', 100),
        ('100.0GHz', None, 100),
        ('100.0GHz', '10.0MHz', None),
        ('100.0GHz', '10.0MHz', -1),
        ('100.0GHz', '10.0MHz', 0),
        ('100.0GHz', '0.0MHz', 10),
        ('0', '10.0MHz', 10),
        ('10km/s', '10.0MHz', 10),
        ('100.0GHz', '1.0km/s', 10),
    ],
)
def test_fractional_bw_invalid(
    heuristics: ImageParamsHeuristics,
    start: str | None,
    width: str | None,
    nchan: int | None,
) -> None:
    """Verify fractional_bw returns None when inputs do not form a valid frequency grid."""
    assert heuristics.fractional_bw(start, width, nchan) is None


def test_tclean_fractional_bw_kwargs_supported(heuristics: ImageParamsHeuristics) -> None:
    """Verify fractional_bw kwarg is returned for briggsbwtaper when tclean supports it."""

    def fake_tclean(vis: str = '', weighting: str = 'natural', fractional_bw: float = 0.0) -> None:
        return None

    with patch('pipeline.hif.heuristics.imageparams_base.casatasks.tclean', fake_tclean):
        kwargs = heuristics.tclean_fractional_bw_kwargs('briggsbwtaper', '100.0GHz', '10.0MHz', 100)
        assert 'fractional_bw' in kwargs
        assert kwargs['fractional_bw'] == pytest.approx((100 * 10e6) / (100e9 + 0.5 * 99 * 10e6))

        assert heuristics.tclean_fractional_bw_kwargs('briggs', '100.0GHz', '10.0MHz', 100) == {}


def test_tclean_fractional_bw_kwargs_unsupported(heuristics: ImageParamsHeuristics) -> None:
    """Verify fractional_bw kwarg is omitted when casatasks.tclean does not accept it."""

    def fake_tclean(vis: str = '', weighting: str = 'natural') -> None:
        return None

    with patch('pipeline.hif.heuristics.imageparams_base.casatasks.tclean', fake_tclean):
        assert heuristics.tclean_fractional_bw_kwargs('briggsbwtaper', '100.0GHz', '10.0MHz', 100) == {}
