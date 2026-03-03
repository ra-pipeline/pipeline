"""Unit tests for ObservingRun prototype (Phase 5)."""

import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pipeline.domain.observingrun import ObservingRun


class DummyField:
    def __init__(self, name: str, intents: set[str]) -> None:
        self.name = name
        self.intents = intents


class DummySpw:
    def __init__(self, spw_id: int, name: str) -> None:
        self.id = spw_id
        self.name = name


class DummyMS:
    def __init__(self, name: str, spws: list[DummySpw]) -> None:
        self.name = name
        self.basename = name
        self.data_types_per_source_and_spw = {}
        self.start_time = {'m0': {'value': 0.0}, 'refer': 'UTC', 'type': 'epoch'}
        self.fields = [DummyField('Target1', {'TARGET'})]
        self.sources = [SimpleNamespace(name='Target1')]
        self.spectralspec_spwmap = {'science': [s.id for s in spws]}
        self._spws = spws

    def get_spectral_windows(self, science_windows_only: bool = False) -> list[DummySpw]:
        return self._spws

    def get_spectral_window(self, spw_id: int) -> DummySpw:
        for spw in self._spws:
            if spw.id == spw_id:
                return spw
        raise KeyError(spw_id)

    @property
    def intents(self) -> set[str]:
        intents = set()
        for field in self.fields:
            intents.update(field.intents)
        return intents


class TestObservingRun(unittest.TestCase):
    """Test ObservingRun implementation."""

    def test_add_measurement_set(self) -> None:
        run = ObservingRun()
        ms = DummyMS('test.ms', [DummySpw(0, 'SPW0')])

        with patch(
            'pipeline.domain.observingrun.utils.get_epoch_as_datetime'
        ) as mock_get_dt:
            mock_get_dt.return_value = datetime.datetime.utcfromtimestamp(0)
            run.add_measurement_set(ms)

        self.assertEqual(len(run.measurement_sets), 1)
        self.assertIn('SPW0', run.virtual_science_spw_names)

    def test_get_ms_by_name(self) -> None:
        run = ObservingRun()
        ms = DummyMS('test.ms', [DummySpw(0, 'SPW0')])
        with patch(
            'pipeline.domain.observingrun.utils.get_epoch_as_datetime'
        ) as mock_get_dt:
            mock_get_dt.return_value = datetime.datetime.utcfromtimestamp(0)
            run.add_measurement_set(ms)

        self.assertIs(run.get_ms(name='test.ms'), ms)

    def test_get_measurement_sets_by_intent(self) -> None:
        run = ObservingRun()
        ms = DummyMS('test.ms', [DummySpw(0, 'SPW0')])
        with patch(
            'pipeline.domain.observingrun.utils.get_epoch_as_datetime'
        ) as mock_get_dt:
            mock_get_dt.return_value = datetime.datetime.utcfromtimestamp(0)
            run.add_measurement_set(ms)

        results = run.get_measurement_sets(intents='TARGET')
        self.assertEqual(results, [ms])

    def test_get_real_spwsel(self) -> None:
        run = ObservingRun()
        ms = DummyMS('test.ms', [DummySpw(3, 'SPW3')])

        with patch(
            'pipeline.domain.observingrun.utils.get_epoch_as_datetime'
        ) as mock_get_dt:
            mock_get_dt.return_value = datetime.datetime.utcfromtimestamp(0)
            run.add_measurement_set(ms)

        virtual_id = run.get_virtual_spw_id_by_name('SPW3')
        self.assertIsNotNone(virtual_id)

        selection = run.get_real_spwsel([str(virtual_id)], ['test.ms'])
        self.assertEqual(selection, ['3'])

        selection_with_channels = run.get_real_spwsel([f'{virtual_id}:2~8'], ['test.ms'])
        self.assertEqual(selection_with_channels, ['3:2~8'])

    def test_real2real_spw_id(self) -> None:
        run = ObservingRun()
        source_ms = DummyMS('source.ms', [DummySpw(2, 'SPW_SHARED')])
        target_ms = DummyMS('target.ms', [DummySpw(9, 'SPW_SHARED')])

        with patch(
            'pipeline.domain.observingrun.utils.get_epoch_as_datetime'
        ) as mock_get_dt:
            mock_get_dt.return_value = datetime.datetime.utcfromtimestamp(0)
            run.add_measurement_set(source_ms)
            run.add_measurement_set(target_ms)

        mapped_spw = run.real2real_spw_id(2, source_ms, target_ms)
        self.assertEqual(mapped_spw, 9)
