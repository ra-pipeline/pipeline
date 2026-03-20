from __future__ import annotations

from datetime import datetime
from unittest.mock import Mock, patch

import numpy as np
import pytest

from pipeline.domain.field import Field


class TestSetZdTelmjd:
    """Tests for set_zd_telmjd method."""

    def test_set_zd_telmjd_basic(self):
        """Test set_zd_telmjd calculates and sets zd and telmjd."""
        direction = {
            'm0': {'value': 4.18879, 'unit': 'rad'},
            'm1': {'value': 0.58534, 'unit': 'rad'},
            'refer': 'J2000',
            'type': 'direction'
        }
        field = Field(
            field_id=0,
            name='test_field',
            source_id=0,
            time=np.array([0.0, 3600.0]),
            direction=direction
        )

        assert field._zd is None
        assert field._telmjd is None

        with patch('pipeline.domain.field.casa_tools') as mock_casa:
            mock_casa.quanta.convert.return_value = {'value': 45.0, 'unit': 'deg'}
            field.set_zd_telmjd('VLA')

        assert field._zd is not None
        assert field._telmjd is not None
        assert 'value' in field._zd
        assert 'unit' in field._zd

    def test_set_zd_telmjd_uses_observatory(self):
        """Test set_zd_telmjd accepts observatory parameter."""
        direction = {
            'm0': {'value': 4.18879, 'unit': 'rad'},
            'm1': {'value': 0.58534, 'unit': 'rad'},
            'refer': 'J2000',
            'type': 'direction'
        }
        field = Field(
            field_id=0,
            name='test_field',
            source_id=0,
            time=np.array([0.0, 3600.0]),
            direction=direction
        )

        with patch('pipeline.domain.field.utils') as mock_utils:
            mock_utils.obs_midtime.return_value = {
                'm0': {'value': 58089.82, 'unit': 'd'},
                'refer': 'UTC',
                'type': 'epoch'
            }
            mock_utils.compute_zenith_distance.return_value = {'value': 0.785, 'unit': 'rad'}

            with patch('pipeline.domain.field.casa_tools') as mock_casa:
                mock_casa.quanta.convert.return_value = {'value': 45.0, 'unit': 'deg'}
                field.set_zd_telmjd('ALMA')

            mock_utils.obs_midtime.assert_called_once()
            mock_utils.compute_zenith_distance.assert_called_once()
