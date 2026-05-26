"""Unit tests for UnitFormat helpers."""

import unittest

from pipeline.domain.unitformat import UnitFormat


class TestUnitFormat(unittest.TestCase):
    """Test UnitFormat implementation."""

    def test_formatting(self) -> None:
        fmt = UnitFormat()
        fmt.addUnitOfMagnitude(1, '{0:.1f} m')
        fmt.addUnitOfMagnitude(1000, '{0:.1f} km')

        self.assertEqual(fmt.format(1500), '1.5 km')

    def test_prefer_integers(self) -> None:
        fmt = UnitFormat(prefer_integers=True)
        fmt.addUnitOfMagnitude(1, '{0:.0f} s')
        fmt.addUnitOfMagnitude(60, '{0:.1f} mins')

        self.assertEqual(fmt.format(100), '100 s')
