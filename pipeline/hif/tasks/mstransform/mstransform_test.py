"""Unit tests for hif_mstransform SubMS integration (PIPE-3250)."""

import datetime
import os
import unittest.mock as mock
import pytest

from pipeline.domain import DataType, MeasurementSet, ObservingRun, SubMS
from pipeline.hif.tasks.mstransform.mstransform import (
    Mstransform,
    MstransformInputs,
    MstransformResults,
    SerialMstransform,
)
from pipeline.infrastructure import launcher, utils


@pytest.fixture
def mock_context(tmp_path, monkeypatch):
    """Create a mock pipeline Context with an ObservingRun containing a mock MS."""

    def mock_spw_arg_to_id(name, arg, spws):
        if arg in (None, '', '*'):
            return [(s.id, 0, s.num_channels - 1, 1) for s in spws]
        ids = [int(x) for x in str(arg).split(',') if x.strip()]
        return [(s.id, 0, s.num_channels - 1, 1) for s in spws if s.id in ids]

    monkeypatch.setattr(utils, 'spw_arg_to_id', mock_spw_arg_to_id)
    monkeypatch.setattr(utils, 'field_arg_to_id', lambda name, arg, fields: [f.id for f in fields])
    monkeypatch.setattr(utils, 'get_epoch_as_datetime', lambda epoch: datetime.datetime(2026, 1, 1, 0, 0, 0))

    context = launcher.Context()
    context.output_dir = str(tmp_path)
    context.callibrary = mock.MagicMock()

    obsrun = ObservingRun()
    ms = MeasurementSet(name=str(tmp_path / 'uid___A002_X123_X456.ms'), session='session_1')
    ms.origin_ms = ms.name
    ms.data_column[DataType.REGCAL_CONTLINE_ALL] = 'DATA'

    class MockAntenna:
        def __init__(self, ant_id, name):
            self.id = ant_id
            self.name = name

    class MockAntennaArray:
        def __init__(self, name, antennas):
            self.name = name
            self.antennas = antennas

    ant1 = MockAntenna(0, 'DV01')
    ant2 = MockAntenna(1, 'DV02')
    ms.antenna_array = MockAntennaArray('ALMA', [ant1, ant2])

    class MockSource:
        def __init__(self, source_id, name):
            self.id = source_id
            self.name = name
            self.is_eph_obj = False

    class MockField:
        def __init__(self, field_id, name, source):
            self.id = field_id
            self.name = name
            self.source = source
            self.intents = {'TARGET'}
            self.valid_spws = {16, 18, 20}

    source = MockSource(1, 'TargetSource')
    field = MockField(0, 'TargetSource', source)
    ms.fields = [field]

    class MockSpectralWindow:
        def __init__(self, spw_id, name, num_channels=2000):
            self.id = spw_id
            self.name = name
            self.num_channels = num_channels
            self.intents = {'TARGET'}

    spw16 = MockSpectralWindow(16, 'SPW_16')
    spw18 = MockSpectralWindow(18, 'SPW_18')
    spw20 = MockSpectralWindow(20, 'SPW_20')
    ms.spectral_windows = [spw16, spw18, spw20]

    obsrun.measurement_sets = [ms]
    obsrun.virtual_science_spw_ids = {16: 'SPW_16', 18: 'SPW_18', 20: 'SPW_20'}
    obsrun.virtual_science_spw_names = {'SPW_16': 0, 'SPW_18': 1, 'SPW_20': 2}
    context.observing_run = obsrun

    return context


def test_mstransform_inputs_to_casa_args(mock_context):
    """Test that MstransformInputs strips custom pipeline parameters from CASA arguments."""
    ms = mock_context.observing_run.measurement_sets[0]
    inputs = MstransformInputs(
        context=mock_context,
        vis=ms.name,
        outputvis=str(mock_context.output_dir + '/output.ms'),
        per_spw=True,
        spw='16,18',
        parallel=True,
    )

    casa_args = inputs.to_casa_args()
    assert 'per_spw' not in casa_args
    assert 'parallel' not in casa_args
    assert 'input_data_type' not in casa_args
    assert 'output_data_type' not in casa_args
    assert casa_args['reindex'] is False


def test_mstransform_get_task_args_list_per_spw(mock_context):
    """Test that Mstransform decomposes multi-SPW into individual per-SPW tasks."""
    ms = mock_context.observing_run.measurement_sets[0]
    inputs = MstransformInputs(
        context=mock_context,
        vis=ms.name,
        input_data_type=DataType.REGCAL_CONTLINE_ALL,
        output_data_type=DataType.IM_LINE_SCIENCE,
        per_spw=True,
        spw='16,18,20',
    )
    task = Mstransform(inputs)

    with (
        mock.patch.object(task, '_frames_consistent', return_value=True),
        mock.patch.object(task, '_conversion_possible', return_value=True),
    ):
        args_list = task._get_task_args_list()

    assert len(args_list) == 3
    spws = [a['spw'] for a in args_list]
    assert spws == ['16', '18', '20']
    for a in args_list:
        assert f'.spw{a["spw"]}' in a['outputvis']


def test_serial_mstransform_analyse_per_spw(mock_context, tmp_path):
    """Test that SerialMstransform.analyse produces a SubMS without loading from disk when per_spw=True."""
    ms = mock_context.observing_run.measurement_sets[0]
    outputvis = str(tmp_path / 'uid___A002_X123_X456_targets.ms.spw16')
    os.makedirs(outputvis, exist_ok=True)

    inputs = MstransformInputs(
        context=mock_context,
        vis=ms.name,
        spw='16',
        field='TargetSource',
        per_spw=True,
        outputvis=outputvis,
        output_data_type=DataType.IM_LINE_SCIENCE,
    )
    task = SerialMstransform(inputs)
    result = MstransformResults(vis=ms.name, outputvis=outputvis, output_data_type=DataType.IM_LINE_SCIENCE)

    with mock.patch('pipeline.infrastructure.tablereader.ObservingRunReader.get_observing_run') as mock_reader:
        task.analyse(result)
        # Verify ObservingRunReader was NOT called because per_spw uses lightweight SubMS
        mock_reader.assert_not_called()

    assert len(result.sub_mses) == 1
    assert len(result.mses) == 0

    sub_ms = result.sub_mses[0]
    assert isinstance(sub_ms, SubMS)
    assert sub_ms.name == os.path.abspath(outputvis)
    assert sub_ms.parent_ms is ms
    assert sub_ms.source_name == 'TargetSource'
    assert sub_ms.real_spw_id == 16
    assert sub_ms.virtual_spw_id == 0
    assert sub_ms.data_type == DataType.IM_LINE_SCIENCE


def test_mstransform_results_merge_with_context_subms(mock_context, tmp_path):
    """Test that MstransformResults creates a logical parent MS and attaches SubMS slices."""
    ms = mock_context.observing_run.measurement_sets[0]
    subvis16 = str(tmp_path / 'uid___A002_X123_X456_targets.spw16.ms')
    subvis18 = str(tmp_path / 'uid___A002_X123_X456_targets.spw18.ms')
    base_outputvis = str(tmp_path / 'uid___A002_X123_X456_targets.ms')

    sub16 = SubMS(
        name=subvis16,
        parent_ms=ms,
        source_name='TargetSource',
        real_spw_id=16,
        virtual_spw_id=0,
        data_type=DataType.IM_LINE_SCIENCE,
        base_outputvis=base_outputvis,
    )
    sub18 = SubMS(
        name=subvis18,
        parent_ms=ms,
        source_name='TargetSource',
        real_spw_id=18,
        virtual_spw_id=1,
        data_type=DataType.IM_LINE_SCIENCE,
        base_outputvis=base_outputvis,
    )

    result = MstransformResults(vis=ms.name, outputvis=subvis16, output_data_type=DataType.IM_LINE_SCIENCE)
    result.sub_mses = [sub16, sub18]
    result.inputs = {'output_dir': str(tmp_path)}

    result.merge_with_context(mock_context)

    # 1. ObservingRun contains raw MS and logical targets MS
    assert len(mock_context.observing_run.measurement_sets) == 2
    assert mock_context.observing_run.measurement_sets[0] is ms
    logical_targets_ms = mock_context.observing_run.measurement_sets[1]
    assert logical_targets_ms.is_logical is True
    assert logical_targets_ms.name == base_outputvis
    assert logical_targets_ms.origin_ms == ms.name

    # 2. Both SubMSes are registered in logical parent MS
    assert len(logical_targets_ms.sub_mses) == 2
    assert logical_targets_ms.has_subms() is True
    assert logical_targets_ms.has_subms(DataType.IM_LINE_SCIENCE) is True
    assert sub16.parent_ms is logical_targets_ms
    assert sub18.parent_ms is logical_targets_ms

    # 3. get_ms finds logical targets MS and SubMS by name and basename
    assert mock_context.observing_run.get_ms(base_outputvis) is logical_targets_ms
    assert mock_context.observing_run.get_ms(subvis16) is sub16
    assert mock_context.observing_run.get_ms(os.path.basename(subvis18)) is sub18

    # 4. Top-level query returns logical parent MS
    top_mses = mock_context.observing_run.get_measurement_sets_of_type(
        dtypes=[DataType.IM_LINE_SCIENCE], msonly=True
    )
    assert top_mses == [logical_targets_ms]

    # 5. ObservingRun queries with source and spw resolve to SubMS
    chunks, dt = mock_context.observing_run.get_measurement_sets_of_type(
        dtypes=[DataType.IM_LINE_SCIENCE], msonly=False, source='TargetSource', spw='16'
    )
    assert dt == DataType.IM_LINE_SCIENCE
    assert list(chunks.keys()) == [sub16]

    # 6. Flagging template file created for logical targets MS
    flag_template = os.path.join(str(tmp_path), 'uid___A002_X123_X456_targets.flagtargetstemplate.txt')
    assert os.path.exists(flag_template)

    # 7. Callibrary registration is skipped for SubMS slices
    assert mock_context.callibrary.add.call_count == 0


def test_mstransform_results_merge_with_context_detached_copy(mock_context, tmp_path):
    """Test that SubMS created on a detached copy of parent_ms creates logical parent correctly."""
    import copy

    ms = mock_context.observing_run.measurement_sets[0]
    detached_ms = copy.deepcopy(ms)

    subvis = str(tmp_path / 'uid___A002_X123_X456_targets.spw16.ms')
    base_outputvis = str(tmp_path / 'uid___A002_X123_X456_targets.ms')
    sub = SubMS(
        name=subvis,
        parent_ms=detached_ms,
        source_name='TargetSource',
        real_spw_id=16,
        virtual_spw_id=0,
        data_type=DataType.IM_LINE_SCIENCE,
        base_outputvis=base_outputvis,
    )

    result = MstransformResults(vis=ms.name, outputvis=subvis, output_data_type=DataType.IM_LINE_SCIENCE)
    result.sub_mses = [sub]
    result.inputs = {'output_dir': str(tmp_path)}

    result.merge_with_context(mock_context)

    logical_targets_ms = mock_context.observing_run.get_ms(base_outputvis)
    assert sub in logical_targets_ms.sub_mses
    assert sub.parent_ms is logical_targets_ms
    assert mock_context.observing_run.get_ms(subvis) is sub
