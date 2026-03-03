"""Unit tests for Field prototype (Phase 5)."""

import json
import unittest
from types import SimpleNamespace

import numpy as np

from pipeline.domain.field import Field, upgrade_field


class TestField(unittest.TestCase):
    """Test Field implementation."""

    def setUp(self) -> None:
        self.field_data = {
            'id': 2,
            'name': 'Target1',
            'source_id': 10,
            'time': np.array([1.0, 2.0, 3.0]),
            'direction': {
                'refer': 'J2000',
                'm0': {'value': 0.1, 'unit': 'rad'},
                'm1': {'value': -0.2, 'unit': 'rad'},
            },
        }

    def test_creation_from_dict(self) -> None:
        fld = Field(**self.field_data)

        self.assertEqual(fld.id, 2)
        self.assertEqual(fld.source_id, 10)
        self.assertEqual(fld.name, 'Target1')

    def test_identifier(self) -> None:
        fld = Field(**self.field_data)
        self.assertEqual(fld.identifier, 'Target1')

    def test_serialization_to_dict(self) -> None:
        fld = Field(**self.field_data)
        serialized = fld.to_dict()

        self.assertEqual(serialized['id'], 2)
        self.assertEqual(serialized['name'], 'Target1')
        self.assertNotIn('intents', serialized)

    def test_serialization_to_json(self) -> None:
        fld = Field(**self.field_data)
        json_str = fld.to_json()
        parsed = json.loads(json_str)

        self.assertEqual(parsed['name'], 'Target1')
        self.assertNotIn('intents', parsed)

    def test_set_source_type(self) -> None:
        fld = Field(**self.field_data)
        fld.set_source_type('source,flux')

        self.assertIn('TARGET', fld.intents)
        self.assertIn('AMPLITUDE', fld.intents)

    def test_migration_from_legacy_object(self) -> None:
        legacy = SimpleNamespace(
            id=2,
            source_id=10,
            time=self.field_data['time'],
            _name='Target1',
            mdirection=self.field_data['direction'],
            intents=set(),
            states=set(),
            valid_spws=set(),
            flux_densities=set(),
            zd=None,
            telmjd=None,
        )

        migrated = Field.from_field_object(legacy)

        self.assertEqual(migrated.id, legacy.id)
        self.assertEqual(migrated.name, legacy._name)

    def test_upgrade_helper(self) -> None:
        fld = Field(**self.field_data)
        upgraded = upgrade_field(fld)

        self.assertIs(upgraded, fld)
