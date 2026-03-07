"""Unit tests for FluxMeasurement prototype (Phase 5)."""

import json
import unittest

from pipeline.domain.measures import FluxDensity, FluxDensityUnits
from pipeline.domain.fluxmeasurement import FluxMeasurement


class TestFluxMeasurement(unittest.TestCase):
    """Test FluxMeasurement implementation."""

    def test_creation_with_scalars(self) -> None:
        flux = FluxMeasurement(spw_id='1', I=1.2, Q=0.1, U=0.2, V=0.3)

        self.assertEqual(flux.spw_id, 1)
        self.assertIsInstance(flux.I, FluxDensity)
        self.assertEqual(float(flux.I.to_units(FluxDensityUnits.JANSKY)), 1.2)

    def test_positional_constructor(self) -> None:
        flux = FluxMeasurement(1, 1.2, 0.1, 0.2, 0.3, 0.0, 0.0, 0.0, origin='test')

        self.assertEqual(flux.spw_id, 1)
        self.assertEqual(float(flux.I.to_units(FluxDensityUnits.JANSKY)), 1.2)
        self.assertEqual(flux.origin, 'test')

    def test_serialization_to_dict(self) -> None:
        flux = FluxMeasurement(spw_id=1, I=1.0, Q=0.0, U=0.0, V=0.0)
        serialized = flux.to_dict()

        self.assertEqual(serialized['spw_id'], 1)
        self.assertEqual(serialized['I'], 1.0)

    def test_serialization_to_json(self) -> None:
        flux = FluxMeasurement(spw_id=1, I=1.0, Q=0.0, U=0.0, V=0.0)
        json_str = flux.to_json()
        parsed = json.loads(json_str)

        self.assertEqual(parsed['spw_id'], 1)
        self.assertEqual(parsed['I'], 1.0)
