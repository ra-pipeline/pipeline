"""Focused tests for PIPE-2956.

These tests pin down the parameter-plumbing contract for ``examineCrossPolSum``
and the multi-scan correlation averaging behavior. They use synthetic reader
output rather than full CASA/MS machinery.
"""

import inspect
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from numpy.ma import ids

from pipeline.extern import XmlObjectifier
from pipeline.hif.cli.hif_correctedampflag import hif_correctedampflag
from pipeline.hif.tasks.correctedampflag import correctedampflag
from pipeline.hif.tasks.correctedampflag.correctedampflag import Correctedampflag, CorrectedampflagInputs
from pipeline.infrastructure import argmapper
from pipeline.infrastructure.launcher import Context

PARAM = 'examineCrossPolSum'


def test_inputs_default_resolves_to_false():
    """Test whether the default is False."""
    context = Mock(spec=Context)
    inputs = CorrectedampflagInputs(context=context, vis=None)
    assert getattr(inputs, PARAM) is False


def test_inputs_explicit_true_resolves_to_true():
    """Test whether the parameter can explicitly be set to True."""
    context = Mock(spec=Context)
    inputs = CorrectedampflagInputs(context=context, vis=None, **{PARAM: True})
    assert getattr(inputs, PARAM) is True


def test_inputs_explicit_false_resolves_to_false():
    """Test whether the parameter can explicitly be set to False."""
    context = Mock(spec=Context)
    inputs = CorrectedampflagInputs(context=context, vis=None, **{PARAM: False})
    assert getattr(inputs, PARAM) is False


def test_cli_signature_includes_param():
    """Test whether the parameter is included in the function signature."""
    params = inspect.signature(hif_correctedampflag).parameters
    assert PARAM in params
    assert params[PARAM].default is None


def test_argmapper_preserves_boolean_param():
    """Test whether the CLI-to-inputs mapper accepts and preserves the parameter."""
    converted = argmapper.convert_args(Correctedampflag, {PARAM: True})
    assert converted[PARAM] is True


@pytest.mark.parametrize(
    'text,expected',
    [
        ('true', True),
        ('false', False),
    ],
)
def test_executeppr_getParameters_returns_boolean_param(text, expected):
    """Test whether the PPR parameter reader returns the cast boolean value."""
    from pipeline.infrastructure import executeppr

    ppr_params = XmlObjectifier.XmlObject(
        xmlString=f"""
        <ParameterSet>
            <Parameter>
                <Keyword>{PARAM}</Keyword>
                <Value>{text}</Value>
            </Parameter>
        </ParameterSet>
    """
    ).ParameterSet

    num_params, params = executeppr._getParameters(ppr_params)

    assert num_params == 1
    assert params[PARAM] is expected


def _make_task(examineCrossPolSum=False):
    """Helper to create a Correctedampflag task with the given examineCrossPolSum value."""
    context = Mock(spec=Context)
    inputs = CorrectedampflagInputs(
        context=context,
        vis='synthetic.ms',
        intent='BANDPASS',
        field='cal',
        spw='0',
        examineCrossPolSum=examineCrossPolSum,
    )
    return Correctedampflag(inputs)


def _make_ms(nscans):
    """Helper to create a minimal MS with the given number of scans."""
    return SimpleNamespace(
        basename='synthetic.ms',
        name='synthetic.ms',
        antennas=[SimpleNamespace(id=i, name=f'CM{i:02d}') for i in range(4)],
        get_scans=Mock(return_value=[SimpleNamespace(id=i) for i in range(nscans)]),
    )


def _make_data(corr_values):
    """Helper to build a minimal channel-averaged MS reader payload.

    ``corr_values`` is shaped as correlation x row. The production reader keeps
    a singleton channel axis, so this helper mirrors that shape.
    """
    corr_values = np.asarray(corr_values, dtype=float)
    nrows = corr_values.shape[1]
    assert nrows <= 8
    return {
        'corrected_data': corr_values[:, np.newaxis, :],
        'model_data': np.zeros_like(corr_values[:, np.newaxis, :]),
        'antenna1': np.array([0, 0, 1, 1, 2, 2, 3, 3])[:nrows],
        'antenna2': np.array([1, 2, 2, 3, 3, 0, 0, 1])[:nrows],
        'flag': np.zeros_like(corr_values[:, np.newaxis, :], dtype=bool),
        'time': np.arange(nrows, dtype=float),
        'uvdist': np.linspace(10.0, 80.0, nrows),
    }


def _record_evaluated_correlations(
    monkeypatch,
    corr_type,
    data,
    nscans=2,
    examine_cross_pol_sum=False,
):
    """Helper to record the evaluated correlations from a Correctedampflag task."""
    evaluated = []

    def record_heuristic(*args, **kwargs):
        evaluated.append(kwargs.get('icorr', args[3]))
        return []

    monkeypatch.setattr(
        correctedampflag.mstools,
        'read_channel_averaged_data_from_ms',
        Mock(return_value=data),
    )
    monkeypatch.setattr(
        correctedampflag.commonhelpermethods,
        'get_corr_products',
        Mock(return_value=corr_type),
    )
    monkeypatch.setattr(
        Correctedampflag,
        '_evaluate_antbased_heuristics',
        staticmethod(record_heuristic),
    )
    monkeypatch.setattr(
        Correctedampflag,
        '_create_flags_for_ultrahigh_baselines_timestamps',
        staticmethod(lambda *args, **kwargs: []),
    )

    task = _make_task(examine_cross_pol_sum)
    flags = task._evaluate_heuristic_for_baseline_set(
        _make_ms(nscans=nscans),
        intent='BANDPASS',
        field='cal',
        spwid=0,
        antenna_id_to_name={i: f'CM{i:02d}' for i in range(4)},
    )

    assert flags == []
    return evaluated


@pytest.mark.parametrize(
    'corr_type,corr_values,examine_cross_pol_sum,expected',
    [
        (
            ['XX', 'YY'],
            [
                [100, 0, 0, 0, 0, 0, 0, 0],
                [100, 0, 0, 0, 0, 0, 0, 0],
            ],
            True,
            [0],
        ),
        (
            ['XX', 'XY', 'YX', 'YY'],
            [
                [100, 0, 0, 0, 0, 0, 0, 0],
                [0, 200, 0, 0, 0, 0, 0, 0],
                [0, 200, 0, 0, 0, 0, 0, 0],
                [100, 0, 0, 0, 0, 0, 0, 0],
            ],
            False,
            [0],
        ),
        (
            ['XX', 'XY', 'YX', 'YY'],
            [
                [100, 0, 0, 0, 0, 0, 0, 0],
                [0, 200, 0, 0, 0, 0, 0, 0],
                [0, 200, 0, 0, 0, 0, 0, 0],
                [100, 0, 0, 0, 0, 0, 0, 0],
            ],
            True,
            [0, 1],
        ),
    ],
    ids=['two_corr_optin', 'four_corr_default', 'four_corr_optin'],
)
def test_multiscan_correlation_averaging_paths(
    monkeypatch,
    corr_type,
    corr_values,
    examine_cross_pol_sum,
    expected,
):
    """Test that the Correctedampflag task evaluates the correct correlations."""
    # Values are intentionally outlier-like so execution reaches the
    # downstream antenna-heuristic seam observed by this test.
    evaluated = _record_evaluated_correlations(
        monkeypatch,
        corr_type,
        _make_data(corr_values),
        examine_cross_pol_sum=examine_cross_pol_sum,
    )

    assert evaluated == expected


def test_single_scan_evaluates_all_correlations_independently(monkeypatch):
    """Test that the Correctedampflag task evaluates the correct correlations for single-scan data."""
    data = _make_data([
        [100, 0, 0, 0, 0, 0, 0, 0],
        [0, 200, 0, 0, 0, 0, 0, 0],
        [0, 0, 300, 0, 0, 0, 0, 0],
        [0, 0, 0, 400, 0, 0, 0, 0],
    ])

    evaluated = _record_evaluated_correlations(
        monkeypatch,
        ['XX', 'XY', 'YX', 'YY'],
        data,
        nscans=1,
        examine_cross_pol_sum=False,
    )

    assert evaluated == [0, 1, 2, 3]
