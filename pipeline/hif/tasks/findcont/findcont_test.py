from types import SimpleNamespace

import numpy as np
import pytest

from . import findcont
from . import qa as findcont_qa
from . import resultobjects


class FakeMS:
    def __init__(self, name, baselines_m):
        self.name = name
        self.antenna_array = SimpleNamespace(
            name='ALMA',
            baselines_m=np.asarray(baselines_m, dtype=float),
        )


class FakeObservingRun:
    def __init__(self, mses):
        self._mses = mses

    def get_ms(self, vis):
        return self._mses[vis]


class FakeContext:
    def __init__(self, mses):
        self.observing_run = FakeObservingRun(mses)


class FakeHeuristics:
    def __init__(self, array_desc):
        self._array_desc = array_desc

    def arrays(self, vislist):
        return self._array_desc


def test_default_mode_is_coarse():
    assert findcont.FindContInputs.hm_findcontmode.default == 'coarse'


def test_l80_uses_all_baselines_from_target_vislist(monkeypatch):
    mses = {
        'ms1': FakeMS('ms1', [1.0, 2.0]),
        'ms2': FakeMS('ms2', [3.0, 4.0, 5.0]),
    }
    context = FakeContext(mses)
    heuristics = FakeHeuristics('12m')

    seen = {}
    original_percentile = np.percentile

    def record_percentile(values, percentile):
        seen['values'] = np.asarray(values, dtype=float)
        return original_percentile(np.asarray(values, dtype=float), percentile)

    ms1_baselines = mses['ms1'].antenna_array.baselines_m
    ms2_baselines = mses['ms2'].antenna_array.baselines_m
    expected = np.percentile(np.concatenate([ms1_baselines, ms2_baselines]), 80)

    monkeypatch.setattr(findcont.np, 'percentile', record_percentile)
    params = findcont._coarse_findcont_parameters(context, heuristics, ['ms1', 'ms2'], ['1arcsec'], [100, 120])

    assert seen['values'].tolist() == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert params['cell'] == ['2arcsec']
    assert params['imsize'] == [64, 64]
    assert expected == pytest.approx(4.2)


def test_invalid_findcont_mode_raises_value_error():
    context = FakeContext({})

    with pytest.raises(ValueError, match='Value not in allowed value set'):
        findcont.FindContInputs(context=context, hm_findcontmode='bogus')


def test_coarse_parameters_for_7m_apply_floor_and_no_taper(monkeypatch):
    monkeypatch.setattr(findcont.casa_tools.synthesisutils, 'getOptimumSize', lambda size: size)

    mses = {'aca.ms': FakeMS('aca.ms', [1.0, 2.0, 3.0])}
    context = FakeContext(mses)
    heuristics = FakeHeuristics('7m')

    params = findcont._coarse_findcont_parameters(context, heuristics, ['aca.ms'], ['1arcsec'], [50, 50])

    assert params['weighting'] == 'briggs'
    assert params['robust'] == 1.0
    assert params['perchanweightdensity'] is False
    assert params['mosweight'] is False
    assert params['cell'] == ['1.25arcsec']
    assert params['imsize'] == [64, 64]
    assert params['uvtaper'] is None


def test_coarse_parameters_for_12m_scale_cell_imsize_and_taper(monkeypatch):
    monkeypatch.setattr(findcont.casa_tools.synthesisutils, 'getOptimumSize', lambda size: size)
    monkeypatch.setattr(findcont.np, 'percentile', lambda values, percentile: 200.0)

    mses = {'12m.ms': FakeMS('12m.ms', [1.0, 2.0, 3.0])}
    context = FakeContext(mses)
    heuristics = FakeHeuristics('12m')

    params = findcont._coarse_findcont_parameters(context, heuristics, ['12m.ms'], ['1arcsec'], [100, 120])

    assert params['weighting'] == 'briggs'
    assert params['robust'] == 1.0
    assert params['perchanweightdensity'] is False
    assert params['mosweight'] is False
    assert params['cell'] == ['3arcsec']
    assert params['imsize'] == [64, 64]
    assert len(params['uvtaper']) == 1
    assert params['uvtaper'][0].endswith('arcsec')
    assert float(params['uvtaper'][0].replace('arcsec', '')) == pytest.approx(7.5, abs=0.2)


def test_coarse_parameters_for_12m_above_floor_scales_imsize(monkeypatch):
    monkeypatch.setattr(findcont.casa_tools.synthesisutils, 'getOptimumSize', lambda size: size)
    monkeypatch.setattr(findcont.np, 'percentile', lambda values, percentile: 150.0)

    mses = {'12m.ms': FakeMS('12m.ms', [1.0, 2.0, 3.0])}
    context = FakeContext(mses)
    heuristics = FakeHeuristics('12m')

    params = findcont._coarse_findcont_parameters(context, heuristics, ['12m.ms'], ['1arcsec'], [200, 240])

    assert params['weighting'] == 'briggs'
    assert params['robust'] == 1.0
    assert params['perchanweightdensity'] is False
    assert params['mosweight'] is False
    assert params['cell'] == ['2.8arcsec']
    assert params['imsize'] == [71, 85]
    assert len(params['uvtaper']) == 1
    assert params['uvtaper'][0].endswith('arcsec')


def test_findcont_qa_adds_blue_note_for_coarse_fallback():
    result = resultobjects.FindContResult({}, {}, {}, 1, 1, [], {})
    result.coarse_mode_fallbacks = [{'field': 'foo', 'spw': '0', 'message': 'boom'}]

    findcont_qa.FindContQAHandler().handle(None, result)

    assert any(score.score == pytest.approx(0.9) for score in result.qa.pool)
    assert any('Coarse findcont mode fell back' in score.longmsg for score in result.qa.pool)
