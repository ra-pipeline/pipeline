"""Unit tests for the hifv/tasks/finalcals/renderer.py module."""

from __future__ import annotations

from unittest.mock import MagicMock

from pipeline.hifv.tasks.finalcals.renderer import T2_4MDetailsVLAApplycalRenderer


def _mock_field(field_id, name):
    field = MagicMock(id=field_id)
    field.name = name
    return field


def test_field_flags_for_ms_deduplicates_field_names():
    """Test field_flags_for_ms gives one row per field name when field IDs share a name."""
    fields = {
        'PHASE': [_mock_field(0, '"J1234+5678"'), _mock_field(1, 'J1234+5678'), _mock_field(2, 'J0000+0000')],
        'TARGET': [_mock_field(3, 'T1')],
    }
    ms = MagicMock()
    ms.get_fields.side_effect = lambda intent: fields[intent]
    band_stats = {
        'L': {
            'J1234+5678': {'spw': {0: (0, 10, 100), 1: (5, 20, 100)}},
            'J0000+0000': {'spw': {0: (0, 0, 50)}},
            'T1': {'spw': {0: (1, 2, 10)}},
        }
    }

    field_flags = T2_4MDetailsVLAApplycalRenderer.field_flags_for_ms(ms, band_stats)

    assert field_flags['Complex Gain Calibrators'] == [
        ('J1234+5678', {'L': (5, 30, 200)}),
        ('J0000+0000', {'L': (0, 0, 50)}),
    ]
    assert field_flags['Science Targets'] == [('T1', {'L': (1, 2, 10)})]
