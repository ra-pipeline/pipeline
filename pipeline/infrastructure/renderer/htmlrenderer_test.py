from types import SimpleNamespace

import pytest

from pipeline.infrastructure.renderer.htmlrenderer import format_correlation_bits
from pipeline.infrastructure.renderer.rendererutils import get_subms_badge_label


@pytest.mark.parametrize(
    'correlator_name, correlation_bits, expected',
    [
        ('ALMA_BASELINE', 'BITS_4x4', 'BITS_4x4'),
        ('ALMA_ACA', 'BITS_4x4', 'BITS_4x4'),
        ('ALMA_BASELINE', 'UNKNOWN', 'Unknown'),
        ('ALMA_ACA', 'UNKNOWN', 'Unknown'),
        ('ALMA_BASELINE', None, 'Unknown'),
        ('ALMA_ACA', None, 'BITS_4x4'),
        ('ALMA_BASELINE', '', 'Unknown'),
        ('ALMA_ACA', '', 'BITS_4x4'),
    ],
)
def test_format_correlation_bits(correlator_name, correlation_bits, expected):
    ms = SimpleNamespace(correlator_name=correlator_name)
    spw = SimpleNamespace(correlation_bits=correlation_bits)

    assert format_correlation_bits(ms, spw) == expected


@pytest.mark.parametrize(
    'sub_mses, expected',
    [
        ([], 'Logical'),
        (None, 'Logical'),
        ([SimpleNamespace(real_spw_id=16, source_name=None)], 'Logical (1 SpW Slice)'),
        (
            [
                SimpleNamespace(real_spw_id=16, source_name=None),
                SimpleNamespace(real_spw_id=18, source_name=None),
                SimpleNamespace(real_spw_id=20, source_name=None),
                SimpleNamespace(real_spw_id=22, source_name=None),
            ],
            'Logical (4 SpW Slices)',
        ),
        ([SimpleNamespace(real_spw_id=None, source_name='SourceA')], 'Logical (1 Source Slice)'),
        (
            [
                SimpleNamespace(real_spw_id=None, source_name='SourceA'),
                SimpleNamespace(real_spw_id=None, source_name='SourceB'),
            ],
            'Logical (2 Source Slices)',
        ),
        (
            [SimpleNamespace(real_spw_id=16, source_name='SourceA')],
            'Logical (1 Slice)',
        ),
        (
            [
                SimpleNamespace(real_spw_id=7, source_name='SourceA'),
                SimpleNamespace(real_spw_id=16, source_name='SourceA'),
                SimpleNamespace(real_spw_id=23, source_name='SourceA'),
                SimpleNamespace(real_spw_id=25, source_name='SourceA'),
            ],
            'Logical (4 Slices)',
        ),
    ],
)
def test_get_subms_badge_label(sub_mses, expected):
    assert get_subms_badge_label(sub_mses) == expected

