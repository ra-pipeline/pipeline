from types import SimpleNamespace

import numpy as np
import pytest

import pipeline.infrastructure.pipelineqa as pqa

from . import qa


@pytest.mark.parametrize(
    'amplitudes, expected',
    [
        ([8.0, 9.0, 10.0, 11.0, 12.0], 0.2),
        ([1.0, 1.0, 1.0, 1.0, 1.0], 0.0),
    ],
)
def test_compute_amp_time_variation(amplitudes, expected):
    assert qa._compute_amp_time_variation(amplitudes) == pytest.approx(expected)


def test_compute_amp_time_variation_rejects_zero_median():
    with pytest.raises(ValueError, match='median amplitude'):
        qa._compute_amp_time_variation([0.0, 0.0, 0.0])


@pytest.mark.parametrize(
    'ampvar, expected',
    [
        (0.0, 1.0),
        (0.0325, 0.915),
        (0.13, 0.66),
        (0.195, 0.5),
        (0.26, 0.34),
        (0.52, 0.34),
    ],
)
def test_score_amp_time_variation(ampvar, expected):
    assert qa._score_amp_time_variation(ampvar) == pytest.approx(expected)


def test_get_amp_time_spw_candidates_ignores_combined_entries():
    snr_info = [
        ('Combined (17, 19)', 150.0),
        ('17', 35.0),
        ('19', 55.0),
        ('21', None),
        ('not-a-spw', 99.0),
    ]

    assert qa._get_amp_time_spw_candidates(snr_info) == [19, 17]


def test_get_amp_time_spw_candidates_accepts_dict_snr_info():
    snr_info = {
        'Combined (17, 19, 21, 23)': 449.7,
        '17': 274.8,
        '19': 299.1,
        '21': 0,
        '23': 192.9,
        '29': None,
    }

    assert qa._get_amp_time_spw_candidates(snr_info) == [19, 17, 23, 21]


def test_get_amp_time_variation_for_candidates_retries_after_failure():
    calls = []

    def calculate(spw_id):
        calls.append(spw_id)
        if spw_id == 19:
            raise ValueError('cannot calculate AmpVar')
        return 0.08

    spw_id, ampvar = qa._get_amp_time_variation_for_candidates([19, 17], calculate)

    assert calls == [19, 17]
    assert spw_id == 17
    assert ampvar == pytest.approx(0.08)


def test_get_amp_time_variation_for_candidates_reports_total_failure():
    def calculate(spw_id):
        raise ValueError(f'spw {spw_id} failed')

    with pytest.raises(qa.AmpTimeVariationCalculationError, match='could not be calculated'):
        qa._get_amp_time_variation_for_candidates([19, 17], calculate)


def test_get_non_sso_flux_calibrator_fields_filters_ephemeris_sources():
    non_sso_flux = SimpleNamespace(
        id=0,
        name='J0000-0000',
        intents={'AMPLITUDE'},
        source=SimpleNamespace(is_eph_obj=False),
    )
    sso_flux = SimpleNamespace(
        id=1,
        name='Jupiter',
        intents={'AMPLITUDE'},
        source=SimpleNamespace(is_eph_obj=True),
    )
    phase_cal = SimpleNamespace(
        id=2,
        name='J1111-1111',
        intents={'PHASE'},
        source=SimpleNamespace(is_eph_obj=False),
    )
    ms = SimpleNamespace(get_fields=lambda intent=None: [non_sso_flux, sso_flux, phase_cal])

    assert qa._get_non_sso_flux_calibrator_fields(ms) == [non_sso_flux]


def test_get_non_sso_flux_calibrator_fields_returns_multiple_flux_calibrators():
    flux_a = SimpleNamespace(
        id=0,
        name='J0000-0000',
        intents={'AMPLITUDE'},
        source=SimpleNamespace(is_eph_obj=False),
    )
    flux_b = SimpleNamespace(
        id=1,
        name='J0101-0101',
        intents={'AMPLITUDE'},
        source=SimpleNamespace(is_eph_obj=False),
    )
    ms = SimpleNamespace(get_fields=lambda intent=None: [flux_b, flux_a])

    assert qa._get_non_sso_flux_calibrator_fields(ms) == [flux_a, flux_b]


def test_get_amp_time_snr_info_uses_amplitude_spwmap_for_field():
    flux_field = SimpleNamespace(name='J0000-0000', intents={'AMPLITUDE'})
    spwmap = SimpleNamespace(snr_info=[('19', 55.0), ('17', 35.0)])
    ms = SimpleNamespace(spwmaps={('AMPLITUDE', 'J0000-0000'): spwmap})

    assert qa._get_amp_time_snr_info(ms, flux_field) == spwmap.snr_info


def test_get_amp_time_snr_info_falls_back_to_bandpass_spwmap_for_amp_bandpass_field():
    flux_field = SimpleNamespace(name='J0000-0000', intents={'AMPLITUDE', 'BANDPASS'})
    spwmap = SimpleNamespace(snr_info=[('21', 70.0), ('19', 55.0)])
    ms = SimpleNamespace(spwmaps={('BANDPASS', 'J0000-0000'): spwmap})

    assert qa._get_amp_time_snr_info(ms, flux_field) == spwmap.snr_info


def test_read_amp_time_calibrated_amplitudes_for_selected_field_and_spw(monkeypatch):
    field = SimpleNamespace(id=3, name='J0000-0000')
    ms = SimpleNamespace(basename='uid.ms', name='uid.ms')
    read_calls = []

    def read_channel_averaged_data_from_ms(ms_arg, field_id, spw_id, intent, items):
        read_calls.append((ms_arg, field_id, spw_id, intent, items))
        return {
            'corrected_data': np.array(
                [
                    [[1.0 + 0.0j, 2.0 + 0.0j, 3.0 + 4.0j]],
                    [[2.0 + 0.0j, 4.0 + 0.0j, 0.0 + 6.0j]],
                ]
            ),
            'flag': np.array(
                [
                    [[False, True, False]],
                    [[False, False, False]],
                ]
            ),
            'time': np.array([100.0, 100.0, 110.0]),
            'antenna1': np.array([0, 0, 1]),
            'antenna2': np.array([1, 2, 2]),
        }

    monkeypatch.setattr(
        qa,
        'mstools',
        SimpleNamespace(read_channel_averaged_data_from_ms=read_channel_averaged_data_from_ms),
        raising=False,
    )

    result = qa._read_amp_time_calibrated_amplitudes(ms, field, 17)

    assert read_calls == [
        (
            ms,
            3,
            17,
            'AMPLITUDE',
            ['corrected_data', 'flag', 'time', 'antenna1', 'antenna2'],
        )
    ]
    np.testing.assert_allclose(result.amplitudes, [1.0, 2.0, 4.0, 5.0, 6.0])
    np.testing.assert_allclose(result.times, [100.0, 100.0, 100.0, 110.0, 110.0])
    np.testing.assert_array_equal(result.antenna1, [0, 0, 0, 1, 1])
    np.testing.assert_array_equal(result.antenna2, [1, 1, 2, 2, 2])


def test_average_amp_time_calibrated_amplitudes_by_integration():
    read_result = qa.AmpTimeCalibratedAmplitudes(
        amplitudes=np.array([1.0, 2.0, 4.0, 5.0, 6.0]),
        times=np.array([100.0, 100.0, 100.0, 110.0, 110.0]),
        antenna1=np.array([0, 0, 0, 1, 1]),
        antenna2=np.array([1, 1, 2, 2, 2]),
    )

    result = qa._average_amp_time_calibrated_amplitudes_by_integration(read_result)

    np.testing.assert_allclose(result, [7.0 / 3.0, 5.5])


def test_calculate_amp_time_variation_for_field_retries_spws(monkeypatch):
    field = SimpleNamespace(id=3, name='J0000-0000')
    ms = SimpleNamespace(basename='uid.ms')
    read_calls = []

    def read_amp_time_calibrated_amplitudes(ms_arg, field_arg, spw_id):
        read_calls.append(spw_id)
        if spw_id == 19:
            raise ValueError('no data for spw 19')
        return qa.AmpTimeCalibratedAmplitudes(
            amplitudes=np.array([8.0, 12.0, 9.0, 11.0, 10.0]),
            times=np.array([100.0, 110.0, 120.0, 130.0, 140.0]),
            antenna1=np.array([0, 0, 0, 0, 0]),
            antenna2=np.array([1, 1, 1, 1, 1]),
        )

    monkeypatch.setattr(qa, '_read_amp_time_calibrated_amplitudes', read_amp_time_calibrated_amplitudes)

    spw_id, ampvar = qa._calculate_amp_time_variation_for_field(ms, field, [19, 17])

    assert read_calls == [19, 17]
    assert spw_id == 17
    assert ampvar == pytest.approx(0.2)


def test_make_amp_time_variation_qa_score_reports_selected_spw_field_and_metric():
    field = SimpleNamespace(id=3, name='J0000-0000')
    ms = SimpleNamespace(basename='uid.ms')

    score = qa._make_amp_time_variation_qa_score(ms, field, 17, 0.08)

    assert score.score == pytest.approx(qa._score_amp_time_variation(0.08))
    assert score.shortmsg == 'Flux calibrator amplitude vs. time spread'
    assert score.longmsg == (
        'uid.ms: Based on the SPW with the highest S/N (spw=17), '
        'the Amplitude vs. time spread for the flux calibrator J0000-0000 is 8.0% over the scan'
    )
    assert score.origin.metric_name == 'score_gfluxscale_amp_time_variation'
    assert score.origin.metric_score == pytest.approx(8.0)
    assert score.origin.metric_units == '%'
    assert score.applies_to.vis == {'uid.ms'}
    assert score.applies_to.field == {3}
    assert score.applies_to.spw == {17}


def test_make_amp_time_variation_fallback_qa_score_reports_failure_message():
    field = SimpleNamespace(id=3, name='J0000-0000')
    ms = SimpleNamespace(basename='uid.ms')

    score = qa._make_amp_time_variation_fallback_qa_score(ms, field)

    assert score.score == pytest.approx(0.9)
    assert score.shortmsg == 'Flux calibrator amplitude vs. time spread could not be calculated'
    assert score.longmsg == (
        'uid.ms: the Amplitude vs. time spread for the flux calibrator J0000-0000 could not be calculated'
    )
    assert score.origin.metric_name == 'score_gfluxscale_amp_time_variation'
    assert score.origin.metric_score == 'N/A'
    assert score.origin.metric_units == '%'
    assert score.applies_to.vis == {'uid.ms'}
    assert score.applies_to.field == {3}
    assert score.applies_to.spw == set()


def test_gcorfluxscale_qa_handler_appends_amp_time_score_per_non_sso_calibrator(monkeypatch):
    missing_score = object()
    low_snr_score = object()
    k_spw_score = object()
    amp_time_score = object()
    fallback_score = object()
    success_field = SimpleNamespace(id=3, name='J0000-0000')
    fallback_field = SimpleNamespace(id=4, name='J0101-0101')
    ms = SimpleNamespace(basename='uid.ms')
    result = SimpleNamespace(
        inputs={'vis': 'uid.ms', 'transfer': 'science', 'transintent': 'TARGET'},
        measurements={},
        qa=SimpleNamespace(pool=[]),
    )
    context = SimpleNamespace(observing_run=SimpleNamespace(get_ms=lambda vis: ms))
    calls = []

    monkeypatch.setattr(
        qa.GcorFluxscaleQAHandler,
        '_missing_derived_fluxes',
        staticmethod(lambda ms_arg, field_arg, intent_arg, measurements_arg: missing_score),
    )
    monkeypatch.setattr(
        qa.GcorFluxscaleQAHandler,
        '_low_snr_fluxes',
        staticmethod(lambda ms_arg, measurements_arg: low_snr_score),
    )
    monkeypatch.setattr(qa, 'score_kspw', lambda context_arg, result_arg: [k_spw_score])
    monkeypatch.setattr(qa, '_get_non_sso_flux_calibrator_fields', lambda ms_arg: [success_field, fallback_field])
    monkeypatch.setattr(qa, '_get_amp_time_snr_info', lambda ms_arg, field_arg: [('19', 55.0), ('17', 35.0)])
    monkeypatch.setattr(qa, '_get_amp_time_spw_candidates', lambda snr_info: [19, 17])

    def calculate_amp_time_variation_for_field(ms_arg, field_arg, spw_candidates):
        calls.append((field_arg.name, spw_candidates))
        if field_arg is fallback_field:
            raise qa.AmpTimeVariationCalculationError('could not be calculated')
        return 17, 0.08

    def make_amp_time_variation_qa_score(ms_arg, field_arg, spw_id, ampvar):
        assert field_arg is success_field
        assert spw_id == 17
        assert ampvar == pytest.approx(0.08)
        return amp_time_score

    def make_amp_time_variation_fallback_qa_score(ms_arg, field_arg):
        assert field_arg is fallback_field
        return fallback_score

    monkeypatch.setattr(qa, '_calculate_amp_time_variation_for_field', calculate_amp_time_variation_for_field)
    monkeypatch.setattr(qa, '_make_amp_time_variation_qa_score', make_amp_time_variation_qa_score)
    monkeypatch.setattr(qa, '_make_amp_time_variation_fallback_qa_score', make_amp_time_variation_fallback_qa_score)

    qa.GcorFluxscaleQAHandler().handle(context, result)

    assert calls == [('J0000-0000', [19, 17]), ('J0101-0101', [19, 17])]
    assert result.qa.pool == [missing_score, low_snr_score, k_spw_score, amp_time_score, fallback_score]


def test_qa_pool_representative_uses_minimum_visible_numeric_score():
    pool = pqa.QAScorePool()
    existing_gfluxscale_score = pqa.QAScore(0.75, longmsg='existing gfluxscale score')
    good_amp_time_score = pqa.QAScore(0.915, longmsg='good AmpTime score')
    warning_amp_time_score = pqa.QAScore(0.5, longmsg='warning AmpTime score')
    fallback_amp_time_score = pqa.QAScore(0.9, longmsg='fallback AmpTime score')

    pool.pool.extend([existing_gfluxscale_score, good_amp_time_score, warning_amp_time_score, fallback_amp_time_score])

    assert pool.representative is warning_amp_time_score
