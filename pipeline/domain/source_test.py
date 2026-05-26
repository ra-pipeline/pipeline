"""Unit tests for Source prototype."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pipeline.domain.source import Source, upgrade_source


class TestSource(unittest.TestCase):
    """Test Source implementation."""

    def setUp(self) -> None:
        self.source_data = {
            'id': 1,
            'name': 'J0102+5824',
            'direction': {
                'refer': 'J2000',
                'm0': {'value': 1.234, 'unit': 'rad'},
                'm1': {'value': -0.321, 'unit': 'rad'},
            },
            'proper_motion': {
                'longitude': {'value': 1.0, 'unit': 'rad/yr'},
                'latitude': {'value': 2.0, 'unit': 'rad/yr'},
            },
            'is_eph_obj': False,
            'table_name': '',
            'avg_spacing': '',
        }

    def test_creation_from_dict(self) -> None:
        src = Source(**self.source_data)

        self.assertEqual(src.id, 1)
        self.assertEqual(src.name, 'J0102+5824')
        self.assertEqual(src.frame, 'J2000')

    def test_positional_constructor(self) -> None:
        src = Source(
            self.source_data['id'],
            self.source_data['name'],
            self.source_data['direction'],
            self.source_data['proper_motion'],
            self.source_data['is_eph_obj'],
            self.source_data['table_name'],
            self.source_data['avg_spacing'],
        )
        self.assertEqual(src.id, 1)
        self.assertEqual(src.name, 'J0102+5824')
        self.assertEqual(src.frame, 'J2000')

    def test_source_id_alias(self) -> None:
        src = Source(source_id=1, **{k: v for k, v in self.source_data.items() if k != 'id'})
        self.assertEqual(src.id, 1)

    def test_ephemeris_flags_and_org_direction_runtime(self) -> None:
        src = Source(**self.source_data)
        self.assertFalse(src.is_known_eph_obj)

        src.is_known_eph_obj = True
        src.org_direction = {'refer': 'J2000', 'm0': {'value': 0.0, 'unit': 'rad'}, 'm1': {'value': 0.0, 'unit': 'rad'}}
        self.assertTrue(src.is_known_eph_obj)
        self.assertIsNotNone(src.org_direction)

    def test_longitude_latitude(self) -> None:
        src = Source(**self.source_data)

        self.assertEqual(src.longitude['value'], 1.234)
        self.assertEqual(src.latitude['value'], -0.321)

    def test_proper_motion_string(self) -> None:
        src = Source(**self.source_data)

        with patch('pipeline.domain.source.casa_tools.quanta') as mock_quanta:
            mock_quanta.getvalue.side_effect = [1.0, 2.0]
            mock_quanta.getunit.return_value = 'rad/yr'

            pm = src.proper_motion

            self.assertEqual(pm, '1.000e+00 2.000e+00 rad/yr')

    def test_serialization_to_dict(self) -> None:
        src = Source(**self.source_data)
        serialized = src.to_dict()

        self.assertEqual(serialized['id'], 1)
        self.assertIn('proper_motion', serialized)
        self.assertNotIn('fields', serialized)

    def test_serialization_to_json(self) -> None:
        src = Source(**self.source_data)
        json_str = src.to_json()
        parsed = json.loads(json_str)

        self.assertEqual(parsed['name'], 'J0102+5824')
        self.assertIn('proper_motion', parsed)

    def test_migration_from_legacy_object(self) -> None:
        legacy = SimpleNamespace(
            id=1,
            name='J0102+5824',
            direction=self.source_data['direction'],
            _proper_motion=self.source_data['proper_motion'],
            is_eph_obj=False,
            is_known_eph_obj=True,
            org_direction={'refer': 'J2000', 'm0': {'value': 0.0, 'unit': 'rad'}, 'm1': {'value': 0.0, 'unit': 'rad'}},
            ephemeris_table='',
            avg_spacing='',
            fields=[],
        )

        migrated = Source.from_source_object(legacy)

        self.assertEqual(migrated.id, legacy.id)
        self.assertEqual(migrated.name, legacy.name)
        self.assertTrue(migrated.is_known_eph_obj)
        self.assertIsNotNone(migrated.org_direction)

    def test_upgrade_helper(self) -> None:
        src = Source(**self.source_data)
        upgraded = upgrade_source(src)

        self.assertIs(upgraded, src)
