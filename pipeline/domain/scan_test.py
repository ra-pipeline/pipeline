"""Unit tests for Scan prototype."""

import datetime
import unittest
from unittest.mock import patch

from pipeline.domain.scan import Scan


class DummyQuanta:
    def div(self, value, divisor):
        if isinstance(value, dict):
            return {'value': value['value'] / divisor, 'unit': value.get('unit', 's')}
        return value / divisor

    def sub(self, left, right):
        return {'value': left['value'] - right['value'], 'unit': left.get('unit', 's')}

    def add(self, left, right):
        return {'value': left['value'] + right['value'], 'unit': left.get('unit', 's')}

    def lt(self, left, right):
        return left['value'] < right['value']

    def gt(self, left, right):
        return left['value'] > right['value']

    def unit(self, value):
        return {'value': float(value.rstrip('s')), 'unit': 's'}


class DummyMeasures:
    def getvalue(self, epoch):
        return {'m0': epoch['m0']}

    def epoch(self, v0, rf):
        return {'m0': v0, 'refer': rf, 'type': 'epoch'}

    def getref(self, epoch):
        return epoch['refer']


class TestScan(unittest.TestCase):
    """Test Scan implementation."""

    def setUp(self) -> None:
        self.scan_times = {
            0: [
                (
                    {'m0': {'value': 10.0, 'unit': 's'}, 'refer': 'UTC', 'type': 'epoch'},
                    {'value': 4.0, 'unit': 's'},
                ),
                (
                    {'m0': {'value': 20.0, 'unit': 's'}, 'refer': 'UTC', 'type': 'epoch'},
                    {'value': 4.0, 'unit': 's'},
                ),
            ]
        }

    def test_time_properties(self) -> None:
        with patch('pipeline.domain.scan.casa_tools.quanta', DummyQuanta()):
            with patch('pipeline.domain.scan.casa_tools.measures', DummyMeasures()):
                with patch('pipeline.domain.scan.utils.get_epoch_as_datetime') as mock_get_dt:
                    mock_get_dt.side_effect = (
                        lambda epoch: datetime.datetime.utcfromtimestamp(epoch['m0']['value'])
                    )

                    scan = Scan(id=1, scan_times=self.scan_times)

        self.assertEqual(scan.mean_interval(0).total_seconds(), 4.0)
        self.assertEqual(scan.exposure_time(0).total_seconds(), 14.0)
        self.assertEqual(scan.time_on_source.total_seconds(), 14.0)
