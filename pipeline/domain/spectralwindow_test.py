"""Tests for the Pydantic-based SpectralWindow domain object."""

import json
import unittest
from unittest.mock import patch

import numpy
import pytest

from pipeline.domain import measures, spectralwindow
from pipeline.domain.spectralwindow import SpectralWindow


class DummyQuanta:
    def convertfreq(self, value, unit):
        return {'value': value['value'], 'unit': unit}

    def getvalue(self, value):
        return numpy.asarray([value['value']])


class TestSpectralWindow(unittest.TestCase):
    """Test SpectralWindow creation and serialization."""

    def setUp(self) -> None:
        self.ref_freq = {
            'm0': {'value': 100.0, 'unit': 'Hz'},
            'refer': 'LSRK',
            'type': 'frequency',
        }
        self.data = {
            'id': 1,
            'name': 'SPW0',
            'type': 'TDM',
            'bandwidth': 100.0,
            'ref_freq': self.ref_freq,
            'mean_freq': 150.0,
            'chan_freqs': [100.0, 200.0],
            'chan_widths': [10.0, 10.0],
            'chan_effective_bws': [8.0, 8.0],
            'sideband': 0,
            'baseband': 0,
            'receiver': None,
            'freq_lo': None,
            'band': 'Unknown',
        }

    def test_creation(self) -> None:
        with patch('pipeline.domain.spectralwindow.casa_tools.quanta', DummyQuanta()):
            spw = SpectralWindow(**self.data)

        self.assertEqual(spw.id, 1)
        self.assertEqual(spw.name, 'SPW0')
        self.assertEqual(spw.frame, 'LSRK')
        self.assertEqual(spw.num_channels, 2)

    def test_channel_range(self) -> None:
        with patch('pipeline.domain.spectralwindow.casa_tools.quanta', DummyQuanta()):
            spw = SpectralWindow(**self.data)

        minfreq = measures.Frequency(95.0, measures.FrequencyUnits.HERTZ)
        maxfreq = measures.Frequency(205.0, measures.FrequencyUnits.HERTZ)
        self.assertEqual(spw.channel_range(minfreq, maxfreq), (0, 1))

    def test_serialization_to_dict(self) -> None:
        with patch('pipeline.domain.spectralwindow.casa_tools.quanta', DummyQuanta()):
            spw = SpectralWindow(**self.data)

        serialized = spw.to_dict()
        self.assertEqual(serialized['id'], 1)
        self.assertEqual(serialized['bandwidth'], 100.0)

    def test_serialization_to_json(self) -> None:
        with patch('pipeline.domain.spectralwindow.casa_tools.quanta', DummyQuanta()):
            spw = SpectralWindow(**self.data)

        parsed = json.loads(spw.to_json())
        self.assertEqual(parsed['name'], 'SPW0')
        self.assertEqual(parsed['mean_freq'], 150.0)


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
        mock.quanta.getvalue.return_value = numpy.array([100e9])
        yield mock


def _make_spw(chan_resolutions=None):
    return spectralwindow.SpectralWindow(
        id=0,
        name='test_spw',
        type='TDM',
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
    """Return a Frequency when channel resolutions are available."""
    spw = _make_spw(chan_resolutions=_CHAN_RESOLUTIONS)
    assert spw.resolution == measures.Frequency(31250000.0, measures.FrequencyUnits.HERTZ)


def test_resolution_returns_none_when_absent(mock_casa_tools):
    """Return None when channel resolutions are unavailable."""
    spw = _make_spw()
    assert spw.resolution is None
