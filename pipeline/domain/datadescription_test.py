"""Unit tests for DataDescription prototype."""

import json
import unittest
from unittest.mock import Mock

from pipeline.domain.datadescription import DataDescription


class TestDataDescription(unittest.TestCase):
    """Test DataDescription implementation."""

    def setUp(self) -> None:
        self.spw = Mock()
        self.spw.id = 3
        self.data = {
            'id': 5,
            'spw': self.spw,
            'pol_id': 1,
            'obs_time': None,
            'chan_freq': [1.0, 2.0],
            'corr_axis': ['XX', 'YY'],
        }

    def test_creation(self) -> None:
        dd = DataDescription(**self.data)

        self.assertEqual(dd.id, 5)
        self.assertEqual(dd.spw.id, 3)
        self.assertEqual(dd.pol_id, 1)

    def test_positional_constructor(self) -> None:
        dd = DataDescription(self.data['id'], self.spw, self.data['pol_id'])
        self.assertEqual(dd.id, 5)
        self.assertEqual(dd.spw.id, 3)
        self.assertEqual(dd.pol_id, 1)

    def test_polarizations(self) -> None:
        dd = DataDescription(**self.data)

        self.assertIn('X', dd.polarizations)
        self.assertEqual(dd.num_polarizations, 2)

    def test_serialization_to_dict(self) -> None:
        dd = DataDescription(**self.data)
        serialized = dd.to_dict()

        self.assertEqual(serialized['id'], 5)
        self.assertEqual(serialized['spw_id'], 3)
        self.assertNotIn('spw', serialized)

    def test_serialization_to_json(self) -> None:
        dd = DataDescription(**self.data)
        json_str = dd.to_json()
        parsed = json.loads(json_str)

        self.assertEqual(parsed['pol_id'], 1)
        self.assertEqual(parsed['spw_id'], 3)
