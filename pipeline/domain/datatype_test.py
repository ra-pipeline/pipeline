"""Unit tests for DataType enumeration."""

import unittest

from pipeline.domain.datatype import DataType


class TestDataType(unittest.TestCase):
    """Test DataType implementation."""

    def test_specmode_datatypes(self) -> None:
        datatypes = DataType.get_specmode_datatypes('TARGET', 'mfs')

        self.assertEqual(datatypes[0], DataType.SELFCAL_CONTLINE_SCIENCE)
        self.assertIn(DataType.RAW, datatypes)

    def test_short_desc(self) -> None:
        desc = DataType.get_short_datatype_desc('RAW')
        self.assertIn('RAW', desc)
