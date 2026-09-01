"""Unit tests for the pipeline/hifv/heuristics/bandpass.py module."""
import pytest
from unittest.mock import MagicMock, Mock

from pipeline.hifv.heuristics.bandpass import is_high_frequency_band
from pipeline.hifv.tasks.testBPdcals.testBPdcals import testBPdcalsInputs
from pipeline.hifv.tasks.semiFinalBPdcals.semiFinalBPdcals import semiFinalBPdcalsInputs
from pipeline.hifv.tasks.finalcals.finalcals import FinalcalsInputs
from pipeline.infrastructure.launcher import Context


@pytest.mark.parametrize(
    "band, expected",
    [
        # High bands (Ku and above)
        ('U', True),
        ('K', True),
        ('A', True),
        ('Q', True),
        ('Ku', True),
        ('KU', True),
        ('Ka', True),
        ('KA', True),
        ('u', True),
        ('k', True),
        ('a', True),
        ('q', True),
        # Low bands (X and below)
        ('4', False),
        ('P', False),
        ('L', False),
        ('S', False),
        ('C', False),
        ('X', False),
        ('x', False),
        ('c', False),
        ('s', False),
        ('l', False),
        ('p', False),
    ]
)
def test_is_high_frequency_band_by_name(band, expected):
    """Test is_high_frequency_band classification by band name."""
    assert is_high_frequency_band(band) == expected


def test_is_high_frequency_band_by_spw_frequency():
    """Test is_high_frequency_band fallback using SPW reference frequencies."""
    mock_ms = MagicMock()

    # Low frequency SPW (5 GHz - C band)
    low_spw = MagicMock()
    low_spw.ref_frequency.value = 5.0e9

    # High frequency SPW (15 GHz - Ku band)
    high_spw = MagicMock()
    high_spw.ref_frequency.value = 15.0e9

    def get_spw(spwid):
        if spwid == 0:
            return low_spw
        elif spwid == 1:
            return high_spw
        raise ValueError(f"Unknown SPW {spwid}")

    mock_ms.get_spectral_window.side_effect = get_spw

    # Unclassified band name
    assert is_high_frequency_band(None, m=mock_ms, spw_list=[0]) is False
    assert is_high_frequency_band('UNKNOWN', m=mock_ms, spw_list=[0]) is False
    assert is_high_frequency_band(None, m=mock_ms, spw_list=[1]) is True
    assert is_high_frequency_band('UNKNOWN', m=mock_ms, spw_list=[1]) is True


def test_task_inputs_bpsolint_mode_defaults():
    """Test that bpsolint_mode defaults to 'auto' across task inputs classes."""
    context = Mock(spec=Context)

    test_inputs = testBPdcalsInputs(context=context, vis='test.ms')
    assert test_inputs.bpsolint_mode == 'auto'

    semifinal_inputs = semiFinalBPdcalsInputs(context=context, vis='test.ms')
    assert semifinal_inputs.bpsolint_mode == 'auto'

    final_inputs = FinalcalsInputs(context=context, vis='test.ms')
    assert final_inputs.bpsolint_mode == 'auto'


@pytest.mark.parametrize("mode", ['auto', 'on', 'off'])
def test_task_inputs_bpsolint_mode_custom(mode):
    """Test setting custom bpsolint_mode values on task inputs classes."""
    context = Mock(spec=Context)

    test_inputs = testBPdcalsInputs(context=context, vis='test.ms', bpsolint_mode=mode)
    assert test_inputs.bpsolint_mode == mode

    semifinal_inputs = semiFinalBPdcalsInputs(context=context, vis='test.ms', bpsolint_mode=mode)
    assert semifinal_inputs.bpsolint_mode == mode

    final_inputs = FinalcalsInputs(context=context, vis='test.ms', bpsolint_mode=mode)
    assert final_inputs.bpsolint_mode == mode

