"""Unit tests for SpectralWindow prototype."""

import json
import unittest
from unittest.mock import patch

import numpy
import pytest

from pipeline.domain import measures
from pipeline.domain.measures import Frequency, FrequencyUnits
from pipeline.domain.spectralwindow import SpectralWindow


# Minimal SpectralWindow constructor arguments.
_NCHAN = 4
_REF_FREQ = {'m0': {'value': 1.0, 'unit': 'GHz'}, 'refer': 'LSRK'}
_CHAN_FREQS = numpy.array([100.0e9, 100.1e9, 100.2e9, 100.3e9])
_CHAN_WIDTHS = numpy.array([15625000.0] * _NCHAN)
_CHAN_EFFECTIVE_BWS = numpy.array([15625000.0] * _NCHAN)
_CHAN_RESOLUTIONS = numpy.array([31250000.0] * _NCHAN)


def _make_spw(mock_casa_tools, chan_resolutions=None):
    return SpectralWindow(
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


@pytest.fixture
def mock_casa_tools():
    """Mock casa_tools.quanta, which requires a live CASA environment."""
    with patch('pipeline.domain.spectralwindow.casa_tools') as mock:
        mock.quanta.convertfreq.return_value = {'value': 100e9, 'unit': 'Hz'}
        mock.quanta.getvalue.return_value = [100e9]
        yield mock


def test_resolution_returns_frequency_when_set(mock_casa_tools):
    """spw.resolution returns a Frequency when chan_resolutions is provided."""
    spw = _make_spw(mock_casa_tools, chan_resolutions=_CHAN_RESOLUTIONS)
    assert spw.resolution == Frequency(31250000.0, FrequencyUnits.HERTZ)


def test_resolution_returns_none_when_absent(mock_casa_tools):
    """spw.resolution returns None when chan_resolutions is not provided."""
    spw = _make_spw(mock_casa_tools)
    assert spw.resolution is None


class DummyQuanta:
    def convertfreq(self, value, unit):
        return {'value': value['value'], 'unit': unit}

    def getvalue(self, value):
        return [value['value']]


class TestSpectralWindow(unittest.TestCase):
    """Test SpectralWindow implementation."""

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

    def test_positional_constructor(self) -> None:
        with patch('pipeline.domain.spectralwindow.casa_tools.quanta', DummyQuanta()):
            spw = SpectralWindow(
                self.data['id'],
                self.data['name'],
                self.data['type'],
                self.data['bandwidth'],
                self.data['ref_freq'],
                self.data['mean_freq'],
                self.data['chan_freqs'],
                self.data['chan_widths'],
                self.data['chan_effective_bws'],
                self.data['sideband'],
                self.data['baseband'],
                self.data['receiver'],
                self.data['freq_lo'],
            )

        self.assertEqual(spw.id, 1)
        self.assertEqual(spw.name, 'SPW0')
        self.assertEqual(spw.num_channels, 2)

    def test_channel_range(self) -> None:
        with patch('pipeline.domain.spectralwindow.casa_tools.quanta', DummyQuanta()):
            spw = SpectralWindow(**self.data)

        minfreq = measures.Frequency(95.0, measures.FrequencyUnits.HERTZ)
        maxfreq = measures.Frequency(205.0, measures.FrequencyUnits.HERTZ)
        ch_min, ch_max = spw.channel_range(minfreq, maxfreq)

        self.assertEqual((ch_min, ch_max), (0, 1))

    def test_serialization_to_dict(self) -> None:
        with patch('pipeline.domain.spectralwindow.casa_tools.quanta', DummyQuanta()):
            spw = SpectralWindow(**self.data)

        serialized = spw.to_dict()
        self.assertEqual(serialized['id'], 1)
        self.assertEqual(serialized['bandwidth'], 100.0)

    def test_serialization_to_json(self) -> None:
        with patch('pipeline.domain.spectralwindow.casa_tools.quanta', DummyQuanta()):
            spw = SpectralWindow(**self.data)

        json_str = spw.to_json()
        parsed = json.loads(json_str)

        self.assertEqual(parsed['name'], 'SPW0')
        self.assertEqual(parsed['mean_freq'], 150.0)
