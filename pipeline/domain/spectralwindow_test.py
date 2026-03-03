"""Unit tests for SpectralWindow prototype (Phase 5)."""

import json
import unittest
from unittest.mock import patch

from pipeline.domain import measures
from pipeline.domain.spectralwindow import SpectralWindow


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
