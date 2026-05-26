"""Unit tests for Antenna prototype.

Tests demonstrate:
1. Data model validation
2. Backward compatibility with legacy API
3. Serialization/deserialization
4. Migration from legacy objects
"""

import json
import unittest
from unittest.mock import Mock, patch

from pipeline.domain.antenna import Antenna, upgrade_antenna


class TestAntenna(unittest.TestCase):
    """Test Antenna implementation."""

    def setUp(self):
        """Set up test data."""
        self.antenna_data = {
            'id': 0,
            'name': 'DV01',
            'station': 'J504',
            'diameter': 12.0,
            'position': {
                'm0': {'value': -1.2345, 'unit': 'rad'},  # longitude
                'm1': {'value': 0.5678, 'unit': 'rad'},   # latitude
                'm2': 2087650.0,  # height in meters
            },
            'offset': {
                'm0': {'value': 10.0, 'unit': 'm'},
                'm1': {'value': 20.0, 'unit': 'm'},
                'm2': {'value': 30.0, 'unit': 'm'},
            },
        }

    def test_creation_from_dict(self):
        """Test creating Antenna from dictionary."""
        ant = Antenna(**self.antenna_data)

        self.assertEqual(ant.id, 0)
        self.assertEqual(ant.name, 'DV01')
        self.assertEqual(ant.station, 'J504')
        self.assertEqual(ant.diameter, 12.0)
        self.assertEqual(ant.position['m0']['value'], -1.2345)

    def test_creation_positional(self) -> None:
        ant = Antenna(
            self.antenna_data['id'],
            self.antenna_data['name'],
            self.antenna_data['station'],
            self.antenna_data['position'],
            self.antenna_data['offset'],
            self.antenna_data['diameter'],
        )
        self.assertEqual(ant.id, 0)
        self.assertEqual(ant.name, 'DV01')
        self.assertEqual(ant.station, 'J504')
        self.assertEqual(ant.diameter, 12.0)

    def test_identifier_with_name(self):
        """Test identifier property when name is present."""
        ant = Antenna(**self.antenna_data)
        self.assertEqual(ant.identifier, 'DV01')

    def test_identifier_without_name(self):
        """Test identifier property when name is empty."""
        data = self.antenna_data.copy()
        data['name'] = ''
        ant = Antenna(**data)
        self.assertEqual(ant.identifier, '#0')

    def test_computed_fields(self):
        """Test computed properties (longitude, latitude, height)."""
        ant = Antenna(**self.antenna_data)

        self.assertEqual(ant.longitude['value'], -1.2345)
        self.assertEqual(ant.latitude['value'], 0.5678)
        self.assertEqual(ant.height, 2087650.0)

    def test_direction_property(self):
        """Test direction property that calls casa_tools."""
        ant = Antenna(**self.antenna_data)

        with patch('pipeline.domain.antenna.casa_tools.measures') as mock_measures:
            mock_measures.direction.return_value = {'refer': 'J2000', 'm0': 0, 'm1': 0}

            direction = ant.direction

            # Verify casa_tools was called correctly
            mock_measures.direction.assert_called_once()
            call_args = mock_measures.direction.call_args
            self.assertEqual(call_args[1]['v0']['value'], -1.2345)
            self.assertEqual(call_args[1]['v1']['value'], 0.5678)

    def test_repr_format(self):
        """Test __repr__ matches legacy format."""
        ant = Antenna(**self.antenna_data)
        repr_str = repr(ant)

        # Should contain class name and key attributes
        self.assertIn('Antenna', repr_str)
        self.assertIn('DV01', repr_str)
        self.assertIn('J504', repr_str)
        self.assertIn('12.0', repr_str)

    def test_str_format(self):
        """Test __str__ format."""
        ant = Antenna(**self.antenna_data)

        with patch('pipeline.domain.antenna.casa_tools.quanta') as mock_quanta:
            mock_quanta.tos.side_effect = ['1h 23m 45.6s', '-02d 34m 56s']

            str_repr = str(ant)

            self.assertIn('Antenna', str_repr)
            self.assertIn('DV01', str_repr)
            self.assertIn('1h 23m 45.6s', str_repr)
            self.assertIn('-02d 34m 56s', str_repr)

    def test_serialization_to_dict(self):
        """Test serialization to dictionary."""
        ant = Antenna(**self.antenna_data)
        serialized = ant.to_dict()

        # Should include data fields
        self.assertEqual(serialized['id'], 0)
        self.assertEqual(serialized['name'], 'DV01')
        self.assertEqual(serialized['station'], 'J504')
        self.assertEqual(serialized['diameter'], 12.0)

        # Should NOT include computed fields
        self.assertNotIn('longitude', serialized)
        self.assertNotIn('latitude', serialized)

    def test_serialization_to_json(self):
        """Test serialization to JSON."""
        ant = Antenna(**self.antenna_data)
        json_str = ant.to_json()

        # Should be valid JSON
        parsed = json.loads(json_str)
        self.assertEqual(parsed['id'], 0)
        self.assertEqual(parsed['name'], 'DV01')

        # Should NOT include computed fields in JSON
        self.assertNotIn('longitude', parsed)
        self.assertNotIn('latitude', parsed)

    def test_deserialization_from_dict(self):
        """Test deserialization from dictionary."""
        ant = Antenna.from_dict(self.antenna_data)

        self.assertEqual(ant.id, 0)
        self.assertEqual(ant.name, 'DV01')
        self.assertEqual(ant.diameter, 12.0)

    def test_deserialization_from_json(self):
        """Test deserialization from JSON."""
        json_str = json.dumps(self.antenna_data)
        ant = Antenna.from_json(json_str)

        self.assertEqual(ant.id, 0)
        self.assertEqual(ant.name, 'DV01')

    def test_round_trip_serialization(self):
        """Test round-trip: object -> dict -> object."""
        ant1 = Antenna(**self.antenna_data)
        serialized = ant1.to_dict()
        ant2 = Antenna.from_dict(serialized)

        self.assertEqual(ant1.id, ant2.id)
        self.assertEqual(ant1.name, ant2.name)
        self.assertEqual(ant1.station, ant2.station)
        self.assertEqual(ant1.diameter, ant2.diameter)

    def test_migration_from_legacy_object(self):
        """Test migration from legacy Antenna object."""
        # Create a mock legacy Antenna
        legacy = Mock()
        legacy.id = 0
        legacy.name = 'DV01'
        legacy.station = 'J504'
        legacy.diameter = 12.0
        legacy.position = self.antenna_data['position']
        legacy.offset = self.antenna_data['offset']

        # Upgrade to Antenna
        ant = Antenna.from_antenna_object(legacy)

        self.assertEqual(ant.id, legacy.id)
        self.assertEqual(ant.name, legacy.name)
        self.assertEqual(ant.station, legacy.station)

    def test_upgrade_antenna_with_antenna_object(self):
        """Test upgrade helper with already-upgraded object."""
        ant1 = Antenna(**self.antenna_data)
        ant2 = upgrade_antenna(ant1)

        # Should return same object
        self.assertIs(ant1, ant2)

    def test_upgrade_antenna_with_legacy_object(self):
        """Test upgrade helper with legacy object."""
        legacy = Mock()
        legacy.id = 0
        legacy.name = 'DV01'
        legacy.station = 'J504'
        legacy.diameter = 12.0
        legacy.position = self.antenna_data['position']
        legacy.offset = self.antenna_data['offset']

        ant = upgrade_antenna(legacy)

        self.assertIsInstance(ant, Antenna)
        self.assertEqual(ant.name, 'DV01')

    def test_upgrade_antenna_with_invalid_object(self):
        """Test upgrade helper with invalid object."""
        result = upgrade_antenna("not an antenna")
        self.assertIsNone(result)

    def test_validation_missing_required_field(self):
        """Test that validation catches required fields."""
        bad_data = {
            'id': 0,
            'name': 'DV01',
            # Missing 'position' - required field
            'diameter': 12.0,
        }

        with self.assertRaises(Exception):  # ValidationError
            Antenna(**bad_data)

    def test_empty_name_handling(self):
        """Test that empty name is handled correctly."""
        data = self.antenna_data.copy()
        data['name'] = ''
        ant = Antenna(**data)

        self.assertEqual(ant.name, '')
        self.assertEqual(ant.identifier, '#0')  # Falls back to ID

    def test_multiple_antennas_independent(self):
        """Test that multiple Antenna instances are independent."""
        data1 = self.antenna_data.copy()
        data1['id'] = 0
        data1['name'] = 'DV01'

        data2 = self.antenna_data.copy()
        data2['id'] = 1
        data2['name'] = 'DV02'

        ant1 = Antenna(**data1)
        ant2 = Antenna(**data2)

        self.assertNotEqual(ant1.id, ant2.id)
        self.assertNotEqual(ant1.name, ant2.name)
        self.assertEqual(ant1.identifier, 'DV01')
        self.assertEqual(ant2.identifier, 'DV02')


if __name__ == '__main__':
    unittest.main()
