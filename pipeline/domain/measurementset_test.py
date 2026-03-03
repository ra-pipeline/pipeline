"""Unit tests for core MeasurementSet port (Phase 5)."""

import datetime
import unittest
from unittest import mock
from types import SimpleNamespace

from pipeline.domain.measurementset import MeasurementSet


class DummyField:
    def __init__(self, field_id: int, name: str, intents: set[str]) -> None:
        self.id = field_id
        self.name = name
        self.intents = intents


class DummyState:
    def __init__(self, state_id: int) -> None:
        self.id = state_id

    def get_obs_mode_for_intent(self, intent: str) -> list[str]:
        return [f'OBS_{intent}']


class DummySpw:
    def __init__(self, spw_id: int, intents: set[str]) -> None:
        self.id = spw_id
        self.intents = intents
        self.num_channels = 16
        self.spectralspec = 'spec'


class DummyDD:
    def __init__(self, dd_id: int, spw: DummySpw) -> None:
        self.id = dd_id
        self.spw = spw
        self.pol_id = 0
        self.polarizations = ['XX']


class DummyScan:
    def __init__(self, scan_id: int, intents: set[str], fields: set[DummyField], spws: set[DummySpw]) -> None:
        self.id = scan_id
        self.intents = intents
        self.fields = fields
        self.spws = spws
        self.start_time = {'m0': {'value': 0.0}, 'refer': 'UTC', 'type': 'epoch'}
        self.end_time = {'m0': {'value': 1.0}, 'refer': 'UTC', 'type': 'epoch'}


class DummyAntennaArray:
    def __init__(self, name: str) -> None:
        self.name = name
        self.antennas = [SimpleNamespace(id=0, name='DV01')]


class TestMeasurementSet(unittest.TestCase):
    """Test core MeasurementSet methods."""

    def setUp(self) -> None:
        self.ms = MeasurementSet(name='dummy.ms')
        self.ms.fields = [DummyField(0, 'Field0', {'TARGET'})]
        self.ms.states = [DummyState(1)]
        spw = DummySpw(0, {'TARGET'})
        self.ms.spectral_windows = [spw]
        self.ms.data_descriptions = [DummyDD(0, spw)]
        self.ms.scans = [DummyScan(1, {'TARGET'}, set(self.ms.fields), {spw})]
        self.ms.antenna_array = DummyAntennaArray('ALMA')

    def test_intents(self) -> None:
        self.assertEqual(self.ms.intents, {'TARGET'})

    def test_basename(self) -> None:
        self.assertEqual(self.ms.basename, 'dummy.ms')

    def test_get_state(self) -> None:
        state = self.ms.get_state(1)
        self.assertIsNotNone(state)
        self.assertEqual(state.id, 1)

    def test_get_scans_by_intent(self) -> None:
        scans = self.ms.get_scans(scan_intent='TARGET')
        self.assertEqual(len(scans), 1)

    def test_get_data_description_by_id(self) -> None:
        dd = self.ms.get_data_description(id=0)
        self.assertIsNotNone(dd)
        self.assertEqual(dd.id, 0)

    def test_get_spectral_window(self) -> None:
        spw = self.ms.get_spectral_window(0)
        self.assertEqual(spw.id, 0)

    def test_get_original_intent(self) -> None:
        intents = self.ms.get_original_intent('TARGET')
        self.assertEqual(intents, {'OBS_TARGET'})

    def test_start_end_time(self) -> None:
        with mock.patch(
            'pipeline.domain.measurementset.utils.get_epoch_as_datetime'
        ) as mock_get_dt:
            mock_get_dt.side_effect = [
                datetime.datetime.utcfromtimestamp(0),
                datetime.datetime.utcfromtimestamp(1),
                datetime.datetime.utcfromtimestamp(0),
                datetime.datetime.utcfromtimestamp(1),
            ]
            self.assertIsNotNone(self.ms.start_time)
            self.assertIsNotNone(self.ms.end_time)
