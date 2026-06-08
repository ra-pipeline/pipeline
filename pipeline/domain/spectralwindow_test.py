"""Tests for SpectralWindow domain object."""

from unittest.mock import patch

import numpy
import pytest

from pipeline.domain import spectralwindow
from pipeline.domain.measures import Frequency, FrequencyUnits

# Minimal SpectralWindow constructor arguments.
_NCHAN = 4
_REF_FREQ = {'m0': {'value': 1.0, 'unit': 'GHz'}, 'refer': 'LSRK'}
_CHAN_FREQS = numpy.array([100.0e9, 100.1e9, 100.2e9, 100.3e9])
_CHAN_WIDTHS = numpy.array([15625000.0] * _NCHAN)
_CHAN_EFFECTIVE_BWS = numpy.array([15625000.0] * _NCHAN)
_CHAN_RESOLUTIONS = numpy.array([31250000.0] * _NCHAN)


@pytest.fixture
def mock_casa_tools():
    """Mock casa_tools.quanta, which requires a live CASA environment."""
    with patch('pipeline.domain.spectralwindow.casa_tools') as mock:
        mock.quanta.convertfreq.return_value = {'value': 100e9, 'unit': 'Hz'}
        mock.quanta.getvalue.return_value = [100e9]
        yield mock


def _make_spw(mock_casa_tools, chan_resolutions=None):
    return spectralwindow.SpectralWindow(
        spw_id=0,
        name='test_spw',
        spw_type='TDM',
        bandwidth=2000000000.0,
        ref_freq=_REF_FREQ,
        mean_freq=100e9,
        chan_freqs=_CHAN_FREQS,
        chan_widths=_CHAN_WIDTHS,
        chan_effective_bws=_CHAN_EFFECTIVE_BWS,
        sideband=1,
        baseband=1,
        receiver=None,
        freq_lo=None,
        chan_resolutions=chan_resolutions,
    )


def test_resolution_returns_frequency_when_set(mock_casa_tools):
    """spw.resolution returns a Frequency when chan_resolutions is provided."""
    spw = _make_spw(mock_casa_tools, chan_resolutions=_CHAN_RESOLUTIONS)
    assert spw.resolution == Frequency(31250000.0, FrequencyUnits.HERTZ)


def test_resolution_returns_none_when_absent(mock_casa_tools):
    """spw.resolution returns None when chan_resolutions is not provided."""
    spw = _make_spw(mock_casa_tools)
    assert spw.resolution is None
