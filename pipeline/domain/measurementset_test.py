from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock, MagicMock

import numpy as np
import pytest

from pipeline.domain.measurementset import MeasurementSet
from pipeline.infrastructure import casa_tools


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
            'type': 'direction'
        }

        epoch = {
            'm0': {'value': 58089.82, 'unit': 'd'},
            'refer': 'UTC',
            'type': 'epoch'
        }

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

        epoch = {
            'm0': {'value': 58089.82, 'unit': 'd'},
            'refer': 'UTC',
            'type': 'epoch'
        }

        result = MeasurementSet.compute_az_el_to_field(ms, None, epoch)
        assert result is None or isinstance(result, list)

    def test_compute_az_el_for_ms_uses_func(self):
        """Test compute_az_el_for_ms applies aggregation function correctly."""
        ms = Mock(spec=MeasurementSet)
        ms.antenna_array = Mock()
        ms.antenna_array.name = 'VLA'
        ms.get_scans = Mock(return_value=[])

        mock_scan = Mock()
        mock_scan.fields = [Mock()]
        mock_scan.fields[0].mdirection = {
            'm0': {'value': np.radians(180.0), 'unit': 'rad'},
            'm1': {'value': np.radians(40.0), 'unit': 'rad'},
            'refer': 'J2000',
            'type': 'direction'
        }
        mock_scan.start_time = {
            'm0': {'value': 58089.82, 'unit': 'd'},
            'refer': 'UTC',
            'type': 'epoch'
        }
        mock_scan.end_time = {
            'm0': {'value': 58089.83, 'unit': 'd'},
            'refer': 'UTC',
            'type': 'epoch'
        }

        ms.scans = [mock_scan]

        az_min, el_min = MeasurementSet.compute_az_el_for_ms(ms, min)
        az_max, el_max = MeasurementSet.compute_az_el_for_ms(ms, max)

        assert 0 <= az_min <= 360
        assert 0 <= az_max <= 360
        assert 0 <= el_min <= 90
        assert 0 <= el_max <= 90
