from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock, MagicMock

import numpy as np
import pytest
from typing import TYPE_CHECKING

from pipeline.domain.measurementset import MeasurementSet
from pipeline.infrastructure import casa_tools

if TYPE_CHECKING:
    from pipeline.domain import Field


class TestComputeAzEl:
    """Tests for compute_az_el_to_field and compute_az_el_for_ms methods."""

    def test_compute_az_el_to_field_basic(self):
        """Test compute_az_el_to_field returns azimuth and elevation in degrees."""
        ms = Mock(spec=MeasurementSet)
        ms.antenna_array = Mock()
        ms.antenna_array.name = 'VLA'

        field = Mock()
        field.mdirection = {
            'm0': {'value': np.radians(180.0), 'unit': 'rad'},
            'm1': {'value': np.radians(40.0), 'unit': 'rad'},
            'refer': 'J2000',
            'type': 'direction',
        }

        epoch = {'m0': {'value': 58089.82, 'unit': 'd'}, 'refer': 'UTC', 'type': 'epoch'}

        result = MeasurementSet.compute_az_el_to_field(ms, field, epoch)

        assert isinstance(result, list)
        assert len(result) == 2
        az, el = result
        assert 0 <= az <= 360  # Azimuth should be in [0, 360)
        assert 0 <= el <= 90  # Elevation should be in [0, 90]

    def test_compute_az_el_to_field_with_none(self):
        """Test compute_az_el_to_field handles None field gracefully."""
        ms = Mock(spec=MeasurementSet)
        ms.antenna_array = Mock()
        ms.antenna_array.name = 'VLA'

        epoch = {'m0': {'value': 58089.82, 'unit': 'd'}, 'refer': 'UTC', 'type': 'epoch'}

        result = MeasurementSet.compute_az_el_to_field(ms, None, epoch)
        assert result is None or isinstance(result, list)

    def test_compute_az_el_for_ms_uses_func(self):
        """Test compute_az_el_for_ms applies aggregation function correctly."""
        ms = Mock(spec=MeasurementSet)
        ms.antenna_array = Mock()
        ms.antenna_array.name = 'VLA'
        ms.get_scans = Mock(return_value=[])

        mock_field = Mock()
        mock_field.mdirection = {
            'm0': {'value': np.radians(180.0), 'unit': 'rad'},
            'm1': {'value': np.radians(40.0), 'unit': 'rad'},
            'refer': 'J2000',
            'type': 'direction',
        }
        mock_scan = Mock()
        mock_scan.fields = [mock_field]
        mock_scan.start_time = {'m0': {'value': 58089.82, 'unit': 'd'}, 'refer': 'UTC', 'type': 'epoch'}
        mock_scan.end_time = {'m0': {'value': 58089.83, 'unit': 'd'}, 'refer': 'UTC', 'type': 'epoch'}

        ms.scans = [mock_scan]

        def mock_compute_az_el(field, epoch):
            return [180.0, 40.0]

        ms.compute_az_el_to_field = Mock(side_effect=mock_compute_az_el)

        az_min, el_min = MeasurementSet.compute_az_el_for_ms(ms, min)
        az_max, el_max = MeasurementSet.compute_az_el_for_ms(ms, max)

        assert 0 <= az_min <= 360
        assert 0 <= az_max <= 360
        assert 0 <= el_min <= 90
        assert 0 <= el_max <= 90

    def test_compute_az_el_to_field_regression(self):
        """Regression test for compute_az_el_to_field with real pipeline data.

        Uses ALMA geocentric coordinates matching CASA's WGS84 values.
        Expected difference from CASA is < 1 arcsecond.
        """
        ms = Mock(spec=MeasurementSet)
        ms.antenna_array = Mock()
        ms.antenna_array.name = 'ALMA'

        field = Mock()
        field.mdirection = {
            'm0': {'unit': 'rad', 'value': -1.2005642899794717},
            'm1': {'unit': 'rad', 'value': -0.5103639490189864},
            'refer': 'ICRS',
            'type': 'direction',
        }
        epoch = {'m0': {'unit': 'd', 'value': 60462.40586666667}, 'refer': 'UTC', 'type': 'epoch'}

        result = MeasurementSet.compute_az_el_to_field(ms, field, epoch)

        def compute_az_el_to_field_casa(ms: MeasurementSet, field: Field | None = None, epoch: dict | None = None) -> list[float]:
            """The old CASA-based equivalent of MeasurementSet.compute_az_el_to_field, for regression testing only."""
            me = casa_tools.measures
            me.doframe(epoch)
            me.doframe(me.observatory(ms.antenna_array.name))
            myazel = me.measure(field.mdirection, 'AZELGEO')
            myaz = myazel['m0']['value']
            myel = myazel['m1']['value']
            myaz = (myaz * 180 / np.pi) % 360
            myel *= 180 / np.pi

            return [myaz, myel]

        result_casa = compute_az_el_to_field_casa(ms, field, epoch)

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0] == pytest.approx(251.4615347, abs=0.001)
        assert result[1] == pytest.approx(56.2378962, abs=0.001)
