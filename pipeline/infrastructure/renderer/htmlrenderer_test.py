from types import SimpleNamespace

import pytest

from pipeline.infrastructure.renderer.htmlrenderer import format_correlation_bits


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
