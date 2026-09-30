from __future__ import annotations

from unittest import mock
import pytest

from pipeline.infrastructure.launcher import Context
from pipeline.h.tasks.mstransform import mstransform as h_mst
from pipeline.hif.tasks.mstransform import mstransform as hif_mst


@pytest.fixture
def context(tmp_path, monkeypatch, request):
    monkeypatch.chdir(tmp_path)
    ctx = Context(name=request.node.name)
    mock_ms = mock.MagicMock()
    mock_ms.name = 'synthetic.ms'
    mock_ms.basename = 'synthetic.ms'
    mock_ms.antenna_array.name = 'ALMA'
    mock_ms.start_time = {'m0': {'value': 54054.0, 'unit': 'd'}, 'refer': 'UTC', 'type': 'epoch'}
    ctx.observing_run.measurement_sets.append(mock_ms)
    return ctx




def test_base_mstransform_inputs_defaults(context):
    """Test default values and properties of base MstransformInputs."""
    inputs = h_mst.MstransformInputs(
        context=context,
        vis='synthetic.ms',
    )
    assert inputs.chanbin == 1
    assert inputs.timebin == '0s'
    assert inputs.datacolumn == ''
    assert inputs.field == ''
    assert inputs.intent == ''
    assert inputs.spw == ''
    assert inputs.outframe == ''
    assert inputs.regridms is None
    assert inputs.mode == 'channel'
    assert inputs.start == ''
    assert inputs.width == ''
    assert inputs.nchan == -1
    assert inputs.per_spw is False
    assert inputs.parallel is False
    assert inputs.outputvis == 'synthetic_targets.ms'


def test_base_mstransform_inputs_to_casa_args(context):
    """Test parameter conversion in to_casa_args for base MstransformInputs."""
    inputs = h_mst.MstransformInputs(
        context=context,
        vis='synthetic.ms',
        chanbin=2,
        timebin='10s',
        per_spw=True,
        parallel=True,
    )
    casa_args = inputs.to_casa_args()
    assert casa_args['reindex'] is False
    assert casa_args['chanaverage'] is True
    assert casa_args['timeaverage'] is True
    assert 'parallel' not in casa_args
    assert 'per_spw' not in casa_args


def test_base_mstransform_expand_task_args_per_spw(context):
    """Test task arguments expansion when per_spw is enabled."""
    inputs = h_mst.MstransformInputs(
        context=context,
        vis='synthetic.ms',
        spw='1, 2, 3',
        per_spw=True,
    )
    task = h_mst.Mstransform(inputs)
    initial_args = [inputs.as_dict()]
    expanded = task._expand_task_args(initial_args)

    assert len(expanded) == 3
    assert expanded[0]['spw'] == '1'
    assert expanded[0]['outputvis'] == 'synthetic_targets.spw1.ms'
    assert expanded[1]['spw'] == '2'
    assert expanded[1]['outputvis'] == 'synthetic_targets.spw2.ms'
    assert expanded[2]['spw'] == '3'
    assert expanded[2]['outputvis'] == 'synthetic_targets.spw3.ms'


def test_base_mstransform_expand_task_args_without_per_spw(context):
    """Test task arguments expansion when per_spw is False."""
    inputs = h_mst.MstransformInputs(
        context=context,
        vis='synthetic.ms',
        spw='1, 2',
        per_spw=False,
    )
    task = h_mst.Mstransform(inputs)
    initial_args = [inputs.as_dict()]
    expanded = task._expand_task_args(initial_args)

    assert len(expanded) == 1
    assert expanded[0]['spw'] == '1, 2'
    assert expanded[0]['outputvis'] == 'synthetic_targets.ms'


def test_hif_mstransform_inheritance():
    """Verify that hif_mstransform classes inherit from base h_mstransform classes."""
    assert issubclass(hif_mst.MstransformInputs, h_mst.MstransformInputs)
    assert issubclass(hif_mst.SerialMstransform, h_mst.SerialMstransform)
    assert issubclass(hif_mst.MstransformResults, h_mst.MstransformResults)
    assert issubclass(hif_mst.Mstransform, h_mst.Mstransform)


def test_hif_mstransform_to_casa_args(context):
    """Test that hif_mstransform strips its domain-specific arguments."""
    inputs = hif_mst.MstransformInputs(
        context=context,
        vis='synthetic.ms',
        field='Field1',
        spw='16',
        input_data_type=mock.Mock(),
        output_data_type=mock.Mock(),
        all_eph_obj=True,
    )
    casa_args = inputs.to_casa_args()
    assert 'input_data_type' not in casa_args
    assert 'output_data_type' not in casa_args
    assert 'all_eph_obj' not in casa_args
    assert 'parallel' not in casa_args
    assert 'per_spw' not in casa_args


def test_base_mstransform_empty_results_qa_and_renderer(context):
    """Test that QA handlers and weblog renderer handle empty results without exceptions."""
    from pipeline.h.tasks.mstransform import qa, renderer

    empty_result = h_mst.MstransformResults(vis=None, outputvis=None)
    empty_result.inputs = {'vis': None, 'outputvis': None}

    # QA Handler should not crash when outputvis is None
    qa_handler = qa.MstransformQAHandler()
    qa_handler.handle(context, empty_result)
    assert len(empty_result.qa.pool) == 0

    # QA List Handler should not crash when vis is None
    list_qa_handler = qa.MstransformListQAHandler()
    results_list = [empty_result]
    results_list_mock = mock.MagicMock()
    results_list_mock.__iter__.return_value = results_list
    results_list_mock.qa.pool = []
    list_qa_handler.handle(context, results_list_mock)

    # Renderer table generation should return empty rows
    table_rows = renderer.make_mstransform_table(context, [empty_result])
    assert table_rows == []


def test_serial_mstransform_static_history():
    """Verify that _update_history is a callable static method on SerialMstransform."""
    assert callable(h_mst.SerialMstransform._update_history)
    # Should execute without error when called directly on the class
    h_mst.SerialMstransform._update_history('vis.ms', 'out.ms')

