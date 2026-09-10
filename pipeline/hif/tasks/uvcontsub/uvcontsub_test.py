"""Unit tests for UVcontSub logical MS and SubMS support."""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from pipeline.domain import DataType, MeasurementSet, SubMS
from pipeline.hif.tasks.uvcontsub.uvcontsub import (
    SerialUVcontSub,
    UVcontSubInputs,
    UVcontSubResults,
)
from pipeline.infrastructure.launcher import Context
from pipeline.infrastructure.utils import nested_dict


class MockAntennaArray:
    def __init__(self, name='ALMA'):
        self.name = name
        self.antennas = []


def test_prepare_logical_ms(tmp_path):
    """Test _prepare_logical_ms delegates uvcontsub to SubMS slices with adapted fitspec."""
    subms1_path = str(tmp_path / "uid___targets.src1.spw0.ms")
    subms2_path = str(tmp_path / "uid___targets.src1.spw1.ms")
    os.makedirs(subms1_path)
    os.makedirs(subms2_path)

    parent_ms = SimpleNamespace(
        name=str(tmp_path / "uid___targets.ms"),
        basename="uid___targets.ms",
        is_logical=True,
        session='session_1',
        antenna_array=MockAntennaArray('ALMA'),
        get_original_intent=lambda intents: ['OBSERVE_TARGET#ON_SOURCE'],
        get_fields=lambda *args, **kwargs: [SimpleNamespace(id=1, name='SRC1')],
    )

    subms1 = SubMS(
        name=subms1_path,
        parent_ms=parent_ms,
        source_name='SRC1',
        real_spw_id=16,
        virtual_spw_id=0,
        field_ids=[1],
        data_type=DataType.REGCAL_CONTLINE_SCIENCE,
    )
    subms2 = SubMS(
        name=subms2_path,
        parent_ms=parent_ms,
        source_name='SRC1',
        real_spw_id=18,
        virtual_spw_id=1,
        field_ids=[1],
        data_type=DataType.REGCAL_CONTLINE_SCIENCE,
    )

    parent_ms.get_subms = lambda: [subms1, subms2]
    parent_ms.has_subms = lambda: True

    context = Context()
    context.output_dir = str(tmp_path)
    context.observing_run.get_ms = lambda name: parent_ms

    inputs = UVcontSubInputs(context, vis=parent_ms.name, output_dir=str(tmp_path))

    task = SerialUVcontSub(inputs)
    task._executor = MagicMock()
    task._executor.execute.return_value = {'status': 'done'}

    fitspec = nested_dict()
    fitspec['1']['16'] = {'chan': '0~10;110~120', 'fitorder': 1}
    fitspec['1']['18'] = {'chan': '5~25;90~115', 'fitorder': 0}

    fields = {'SRC1': True}
    real_spws = {'16': True, '18': True}
    field_intent_spw_list = [
        {'field': 'SRC1', 'intent': 'TARGET', 'spw': '16'},
        {'field': 'SRC1', 'intent': 'TARGET', 'spw': '18'},
    ]
    ms_frame_freq_fitorder_dict = {
        'SRC1': {
            '16': {'freq': '100GHz', 'fitorder': 1},
            '18': {'freq': '102GHz', 'fitorder': 0},
        }
    }

    result = task._prepare_logical_ms(
        datacolumn='data',
        intent='TARGET',
        fitspec=fitspec,
        fields=fields,
        real_spws=real_spws,
        field_intent_spw_list=field_intent_spw_list,
        ms_frame_freq_fitorder_dict=ms_frame_freq_fitorder_dict,
    )

    assert isinstance(result, UVcontSubResults)
    assert len(result.sub_mses) == 2
    assert task._executor.execute.call_count == 2

    # Check first slice parameters
    call_args_list = task._executor.execute.call_args_list
    job0 = call_args_list[0][0][0]
    assert job0.kw['spw'] == '0'
    assert '0' in job0.kw['fitspec']['1']
    assert job0.kw['fitspec']['1']['0']['chan'] == '0~10;110~120'
    assert result.sub_mses[0].data_type == DataType.REGCAL_LINE_SCIENCE
    assert result.sub_mses[0].name.endswith('_targets_line.src1.spw0.ms')

    # Check second slice parameters
    job1 = call_args_list[1][0][0]
    assert job1.kw['spw'] == '0'
    assert '0' in job1.kw['fitspec']['1']
    assert job1.kw['fitspec']['1']['0']['chan'] == '5~25;90~115'
    assert result.sub_mses[1].data_type == DataType.REGCAL_LINE_SCIENCE
    assert result.sub_mses[1].name.endswith('_targets_line.src1.spw1.ms')


def test_analyse_logical_ms(tmp_path):
    """Test analyse verifies SubMS existence without calling ObservingRunReader."""
    subms_dir = tmp_path / "uid___targets_line.src1.spw0.ms"
    subms_dir.mkdir()

    parent_ms = SimpleNamespace(
        name=str(tmp_path / "uid___targets.ms"),
        basename="uid___targets.ms",
        is_logical=True,
        session='session_1',
    )

    context = Context()
    context.output_dir = str(tmp_path)
    context.observing_run.get_ms = lambda name: parent_ms

    inputs = UVcontSubInputs(context, vis=parent_ms.name, output_dir=str(tmp_path))
    task = SerialUVcontSub(inputs)

    result = UVcontSubResults()
    result.mitigation_error = False
    result.skip_stage = False
    result.outputvis = str(tmp_path / "uid___targets_line.ms")
    subms = SubMS(
        name=str(subms_dir),
        parent_ms=None,
        source_name='SRC1',
        real_spw_id=16,
        data_type=DataType.REGCAL_LINE_SCIENCE,
    )
    result.sub_mses = [subms]

    with patch('pipeline.infrastructure.tablereader.ObservingRunReader.get_observing_run') as mock_reader:
        analysed = task.analyse(result)
        mock_reader.assert_not_called()
        assert analysed is result
        assert len(analysed.sub_mses) == 1


def test_merge_with_context_logical_ms(tmp_path):
    """Test merge_with_context registers logical parent MS and child SubMS partitions."""
    raw_eb = MeasurementSet(name=str(tmp_path / "uid___raw.ms"), session='session_1')
    raw_eb.antenna_array = MockAntennaArray('ALMA')
    raw_eb.spectral_windows = []
    raw_eb.fields = []
    raw_eb.sources = []
    raw_eb.data_descriptions = []
    raw_eb.scans = []

    context = Context()
    context.output_dir = str(tmp_path)
    context.observing_run.measurement_sets = [raw_eb]

    def mock_get_ms(name):
        for m in context.observing_run.measurement_sets:
            if m.name == name or m.basename == os.path.basename(name):
                return m
        raise KeyError(name)

    context.observing_run.get_ms = mock_get_ms

    def mock_add_ms(ms):
        context.observing_run.measurement_sets.append(ms)

    context.observing_run.add_measurement_set = mock_add_ms
    context.callibrary = MagicMock()

    subms1_path = str(tmp_path / "uid___targets_line.src1.spw0.ms")
    base_outputvis = str(tmp_path / "uid___targets_line.ms")

    subms1 = SubMS(
        name=subms1_path,
        parent_ms=raw_eb,
        source_name='SRC1',
        real_spw_id=16,
        virtual_spw_id=0,
        field_ids=[1],
        data_type=DataType.REGCAL_LINE_SCIENCE,
        base_outputvis=base_outputvis,
    )

    result = UVcontSubResults()
    result.vis = str(tmp_path / "uid___targets.ms")
    result.outputvis = base_outputvis
    result.sub_mses = [subms1]
    result.inputs = {'output_dir': str(tmp_path), 'vis': result.vis}

    result.merge_with_context(context)

    # Check logical parent MS was registered in context
    logical_ms = context.observing_run.get_ms(base_outputvis)
    assert logical_ms is not None
    assert logical_ms.is_logical
    assert logical_ms.has_subms()
    assert len(logical_ms.get_subms()) == 1
    assert logical_ms.get_subms()[0].name == subms1_path

    # Check flagging template file was created
    flagtemplate = tmp_path / "uid___targets_line.flagtargetstemplate.txt"
    assert flagtemplate.exists()

    # Check callibrary was registered
    context.callibrary.add.assert_called()
