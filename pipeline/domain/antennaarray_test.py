"""Unit tests for AntennaArray prototype (Phase 5)."""

import unittest
from unittest.mock import patch

from pipeline.domain.antennaarray import AntennaArray


class DummyAntenna:
    def __init__(
        self,
        antenna_id: int,
        name: str,
        offsets: dict[str, dict[str, float]],
    ) -> None:
        self.id = antenna_id
        self.name = name
        self.offset = offsets
        self.longitude = 0.0
        self.latitude = 0.0


class TestAntennaArray(unittest.TestCase):
    """Test AntennaArray implementation."""

    def setUp(self) -> None:
        self.ant1 = DummyAntenna(
            0,
            'DV01',
            {
                'longitude offset': {'value': 0.0},
                'latitude offset': {'value': 0.0},
                'elevation offset': {'value': 0.0},
            },
        )
        self.ant2 = DummyAntenna(
            1,
            'DV02',
            {
                'longitude offset': {'value': 3.0},
                'latitude offset': {'value': 4.0},
                'elevation offset': {'value': 0.0},
            },
        )
        self.position = {
            'm0': {'value': 0.0},
            'm1': {'value': 0.0},
            'm2': {'value': 0.0},
        }

    def test_baselines(self) -> None:
        def getvalue(arg):
            if isinstance(arg, dict):
                return [arg['value']]
            return arg

        with patch(
            'pipeline.domain.antennaarray.casa_tools.quanta'
        ) as mock_quanta:
            mock_quanta.getvalue.side_effect = getvalue

            array = AntennaArray(
                name='ALMA',
                position=self.position,
                antennas=[self.ant1, self.ant2],
            )

        self.assertEqual(array.baselines_m.size, 1)
        self.assertAlmostEqual(array.baselines_m[0], 5.0)
        self.assertIsNotNone(array.baseline_min)
        self.assertIsNotNone(array.baseline_max)

    def test_get_antenna(self) -> None:
        def getvalue(arg):
            if isinstance(arg, dict):
                return [arg['value']]
            return arg

        with patch(
            'pipeline.domain.antennaarray.casa_tools.quanta'
        ) as mock_quanta:
            mock_quanta.getvalue.side_effect = getvalue

            array = AntennaArray(
                name='ALMA',
                position=self.position,
                antennas=[self.ant1, self.ant2],
            )

        self.assertEqual(array.get_antenna(id=1).name, 'DV02')
        self.assertEqual(array.get_antenna(name='DV01').id, 0)

    def test_positional_constructor(self) -> None:
        def getvalue(arg):
            if isinstance(arg, dict):
                return [arg['value']]
            return arg

        with patch('pipeline.domain.antennaarray.casa_tools.quanta') as mock_quanta:
            mock_quanta.getvalue.side_effect = getvalue

            array = AntennaArray('ALMA', self.position, [self.ant1, self.ant2])

        self.assertEqual(array.name, 'ALMA')
        self.assertEqual(len(array.antennas), 2)
