"""Unit tests for Polarization prototype (Phase 5)."""

import json
import unittest

import numpy as np

from pipeline.domain.polarization import Polarization


class TestPolarization(unittest.TestCase):
    """Test Polarization implementation."""

    def setUp(self) -> None:
        self.pol_data = {
            'id': 1,
            'num_corr': 2,
            'corr_type': np.array([9, 12]),
            'corr_product': np.array([[0, 0], [1, 1]]),
        }

    def test_creation(self) -> None:
        pol = Polarization(**self.pol_data)

        self.assertEqual(pol.id, 1)
        self.assertEqual(pol.num_corr, 2)
        self.assertEqual(pol.corr_type_string, ['XX', 'YY'])

    def test_serialization_to_dict(self) -> None:
        pol = Polarization(**self.pol_data)
        serialized = pol.to_dict()

        self.assertEqual(serialized['id'], 1)
        self.assertEqual(serialized['corr_type'], [9, 12])

    def test_serialization_to_json(self) -> None:
        pol = Polarization(**self.pol_data)
        json_str = pol.to_json()
        parsed = json.loads(json_str)

        self.assertEqual(parsed['num_corr'], 2)
        self.assertEqual(parsed['corr_product'], [[0, 0], [1, 1]])
