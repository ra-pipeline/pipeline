import os

import pytest

from pipeline.domain import (
    DataType,
    MeasurementSet,
    ObservingRun,
    SubMS,
)


@pytest.fixture
def mock_observing_run(monkeypatch):
    """Create a mock ObservingRun with a parent MeasurementSet and attached SubMS slices."""
    import datetime

    from pipeline.infrastructure import utils

    monkeypatch.setattr(
        utils, 'spw_arg_to_id', lambda name, arg, spws: [(s.id, 0, s.num_channels - 1, 1) for s in spws]
    )
    monkeypatch.setattr(utils, 'field_arg_to_id', lambda name, arg, fields: [f for f in fields])
    monkeypatch.setattr(utils, 'get_epoch_as_datetime', lambda epoch: datetime.datetime(2026, 1, 1, 0, 0, 0))

    obs_run = ObservingRun()

    # Create parent MS
    ms = MeasurementSet(name='/path/to/uid___A002_X123_X456.ms', session='session_1')
    ms.origin_ms = ms.name

    # Mock antennas
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

    # Mock spectral windows (real SPWs 16 and 18)
    class MockSpectralWindow:
        def __init__(self, spw_id, name, num_channels=2000):
            self.id = spw_id
            self.name = name
            self.num_channels = num_channels
            self.intents = {'TARGET'}

    spw16 = MockSpectralWindow(16, 'ALMA_RB_03#BB_1#SW_01#FULL_RES')
    spw18 = MockSpectralWindow(18, 'ALMA_RB_03#BB_2#SW_01#FULL_RES')
    ms.spectral_windows = [spw16, spw18]

    # Mock fields & sources
    class MockSource:
        def __init__(self, source_id, name):
            self.id = source_id
            self.name = name

    class MockField:
        def __init__(self, field_id, name, source):
            self.id = field_id
            self.name = name
            self.source = source
            self.intents = {'TARGET'}

    source_target = MockSource(0, 'TargetA')
    field0 = MockField(0, 'TargetA_0', source_target)
    ms.fields = [field0]
    ms.sources = [source_target]

    class MockScan:
        def __init__(self):
            self.id = 1
            self.start_time = {'m0': {'value': 59000.0, 'unit': 'd'}, 'refer': 'UTC'}
            self.fields = [field0]
            self.spws = [spw16, spw18]
            self.intents = {'TARGET'}

    ms.scans = [MockScan()]

    # Base data column for parent MS
    ms.data_column[DataType.REGCAL_CONTLINE_ALL] = 'DATA'
    ms.data_types_per_source_and_spw[('TargetA', 16)] = [DataType.REGCAL_CONTLINE_ALL]
    ms.data_types_per_source_and_spw[('TargetA', 18)] = [DataType.REGCAL_CONTLINE_ALL]

    # Virtual SPW mappings in observing run
    obs_run.virtual_science_spw_ids = {0: spw16.name, 1: spw18.name}
    obs_run.virtual_science_spw_names = {spw16.name: 0, spw18.name: 1}

    obs_run.add_measurement_set(ms)
    return obs_run, ms


def test_subms_initialization_and_delegation(mock_observing_run):
    _, parent_ms = mock_observing_run

    subms = SubMS(
        name='/path/to/uid___A002_X123_X456.TargetA.spw16.ms',
        parent_ms=parent_ms,
        source_name='TargetA',
        real_spw_id=16,
        virtual_spw_id=0,
        field_ids=[0],
        data_type=DataType.IM_LINE_SCIENCE,
        data_column='DATA',
    )

    # Verify slice attributes
    assert subms.basename == 'uid___A002_X123_X456.TargetA.spw16.ms'
    assert subms.source_name == 'TargetA'
    assert subms.real_spw_id == 16
    assert subms.virtual_spw_id == 0
    assert subms.data_type == DataType.IM_LINE_SCIENCE
    assert subms.get_data_column(DataType.IM_LINE_SCIENCE) == 'DATA'
    assert subms.get_data_column(DataType.RAW) is None

    # Verify delegation to parent MS
    assert subms.session == 'session_1'
    assert subms.origin_ms == parent_ms.origin_ms
    assert len(subms.antennas) == 2
    assert subms.antenna_array == parent_ms.antenna_array

    # Verify filtered accessors
    fields = subms.get_fields()
    assert len(fields) == 1
    assert fields[0].name == 'TargetA_0'

    spws = subms.get_spectral_windows()
    assert len(spws) == 1
    assert spws[0].id == 16


def test_measurementset_subms_registration(mock_observing_run):
    _, parent_ms = mock_observing_run

    sub16 = SubMS(
        name='/path/to/uid___A002_X123_X456.TargetA.spw16.ms',
        parent_ms=parent_ms,
        source_name='TargetA',
        real_spw_id=16,
        virtual_spw_id=0,
        data_type=DataType.IM_LINE_SCIENCE,
    )
    sub18 = SubMS(
        name='/path/to/uid___A002_X123_X456.TargetA.spw18.ms',
        parent_ms=parent_ms,
        source_name='TargetA',
        real_spw_id=18,
        virtual_spw_id=1,
        data_type=DataType.IM_LINE_SCIENCE,
    )

    assert not parent_ms.has_subms()

    parent_ms.add_subms(sub16)
    parent_ms.add_subms(sub18)

    assert parent_ms.has_subms()
    assert parent_ms.has_subms(DataType.IM_LINE_SCIENCE)
    assert not parent_ms.has_subms(DataType.BASELINED)

    # Test filtering in get_subms
    all_subs = parent_ms.get_subms()
    assert len(all_subs) == 2

    spw16_subs = parent_ms.get_subms(spw=16)
    assert len(spw16_subs) == 1
    assert spw16_subs[0].real_spw_id == 16

    vspw1_subs = parent_ms.get_subms(spw=1)  # Virtual SPW ID query
    assert len(vspw1_subs) == 1
    assert vspw1_subs[0].virtual_spw_id == 1

    # Test get_vis
    assert parent_ms.get_vis(source='TargetA', spw=16) == sub16.name
    assert parent_ms.get_vis(source='Unknown') == parent_ms.name


def test_observing_run_subms_resolution(mock_observing_run):
    obs_run, parent_ms = mock_observing_run

    sub16 = SubMS(
        name='/path/to/uid___A002_X123_X456.TargetA.spw16.ms',
        parent_ms=parent_ms,
        source_name='TargetA',
        real_spw_id=16,
        virtual_spw_id=0,
        data_type=DataType.IM_LINE_SCIENCE,
    )
    parent_ms.add_subms(sub16)

    # 1. get_ms should find SubMS by name and basename
    found_by_name = obs_run.get_ms(sub16.name)
    assert found_by_name is sub16

    found_by_basename = obs_run.get_ms(sub16.basename)
    assert found_by_basename is sub16

    # 2. get_measurement_sets_of_type without source/spw returns parent MS
    res_parent = obs_run.get_measurement_sets_of_type([DataType.IM_LINE_SCIENCE], msonly=True)
    assert len(res_parent) == 1
    assert res_parent[0] is parent_ms

    # 3. get_measurement_sets_of_type with source & spw returns child SubMS
    res_sub = obs_run.get_measurement_sets_of_type([DataType.IM_LINE_SCIENCE], msonly=True, source='TargetA', spw='0')
    assert len(res_sub) == 1
    assert res_sub[0] is sub16

    # 4. Explicit return_chunks flag
    res_chunks_forced = obs_run.get_measurement_sets_of_type(
        [DataType.IM_LINE_SCIENCE], msonly=True, return_chunks=True
    )
    assert len(res_chunks_forced) == 1
    assert res_chunks_forced[0] is sub16

    res_parent_forced = obs_run.get_measurement_sets_of_type(
        [DataType.IM_LINE_SCIENCE], msonly=True, source='TargetA', spw='0', return_chunks=False
    )
    assert len(res_parent_forced) == 1
    assert res_parent_forced[0] is parent_ms

    # 5. SPW ID translations accepting SubMS directly
    assert obs_run.virtual2real_spw_id(0, sub16) == 16
    assert obs_run.real2virtual_spw_id(16, sub16) == 0

    # 6. get_measurement_sets_of_type with vis filtering
    # 6a. vis specified as parent MS basename
    res_vis_parent = obs_run.get_measurement_sets_of_type(
        [DataType.IM_LINE_SCIENCE], msonly=True, source='TargetA', spw='0', vis=[parent_ms.basename]
    )
    assert len(res_vis_parent) == 1
    assert res_vis_parent[0] is sub16

    # 6b. vis specified as SubMS basename
    res_vis_sub = obs_run.get_measurement_sets_of_type([DataType.IM_LINE_SCIENCE], msonly=True, vis=[sub16.basename])
    assert len(res_vis_sub) == 1
    assert res_vis_sub[0] is sub16

    # 6c. vis specified as unrelated MS
    res_vis_unrelated = obs_run.get_measurement_sets_of_type(
        [DataType.IM_LINE_SCIENCE], msonly=True, source='TargetA', spw='0', vis=['other.ms']
    )
    assert len(res_vis_unrelated) == 0

    # 7. Signature compatibility of SubMS get_fields and get_spectral_windows
    fields_by_id = sub16.get_fields(field_id=0)
    assert len(fields_by_id) == 1
    fields_by_name = sub16.get_fields(name='TargetA_0')
    assert len(fields_by_name) == 1
    spws_all = sub16.get_spectral_windows()
    assert len(spws_all) == 1
    assert spws_all[0].id == 16


def test_subms_pickling_and_serialization():
    """Test that SubMS and parent MS serialize/deserialize via pickle without recursion error."""
    import pickle

    from pipeline.hif.tasks.mstransform.mstransform import MstransformResults

    parent_ms = MeasurementSet(name='/path/to/uid___A002_X123_X456.ms', session='session_1')
    parent_ms.origin_ms = parent_ms.name

    sub = SubMS(
        name='/path/to/uid___A002_X123_X456.TargetA.spw16.ms',
        parent_ms=parent_ms,
        source_name='TargetA',
        real_spw_id=16,
        virtual_spw_id=0,
        data_type=DataType.IM_LINE_SCIENCE,
    )
    parent_ms.add_subms(sub)

    # 1. Pickle and unpickle SubMS alone
    sub_data = pickle.dumps(sub)
    loaded_sub = pickle.loads(sub_data)
    assert loaded_sub.name == sub.name
    assert loaded_sub.source_name == 'TargetA'
    assert loaded_sub.session == 'session_1'
    with pytest.raises(AttributeError):
        _ = loaded_sub.non_existent_attribute

    # 2. Pickle and unpickle parent MS with circular SubMS reference
    ms_data = pickle.dumps(parent_ms)
    loaded_ms = pickle.loads(ms_data)
    assert len(loaded_ms.sub_mses) == 1
    loaded_child = loaded_ms.sub_mses[0]
    assert loaded_child.parent_ms is loaded_ms
    assert loaded_child.session == 'session_1'

    # 3. Pickle and unpickle MstransformResults containing SubMS
    res = MstransformResults(vis=parent_ms.name, outputvis=sub.name)
    res.sub_mses.append(sub)
    res_data = pickle.dumps(res)
    loaded_res = pickle.loads(res_data)
    assert len(loaded_res.sub_mses) == 1
    assert loaded_res.sub_mses[0].source_name == 'TargetA'


def test_subms_robustness_and_spw_ranges(mock_observing_run):
    """Test SPW range parsing, fields without sources, and get_real_spw_id_by_name with SubMS."""
    obs_run, parent_ms = mock_observing_run

    sub16 = SubMS(
        name='/path/to/uid___A002_X123_X456.TargetA.spw16.ms',
        parent_ms=parent_ms,
        source_name='TargetA',
        real_spw_id=16,
        virtual_spw_id=0,
        data_type=DataType.IM_LINE_SCIENCE,
    )
    parent_ms.add_subms(sub16)

    # 1. SPW range filtering in get_subms
    range_subs = parent_ms.get_subms(spw='15~17')
    assert len(range_subs) == 1
    assert range_subs[0] is sub16

    range_subs_none = parent_ms.get_subms(spw='20~25')
    assert len(range_subs_none) == 0

    # 2. SPW range filtering in SubMS.get_data_column / get_data_type
    assert sub16.get_data_column(DataType.IM_LINE_SCIENCE, spw='15~17') == 'DATA'
    assert sub16.get_data_column(DataType.IM_LINE_SCIENCE, spw='20~25') is None
    assert sub16.get_data_type('DATA', spw='15~17') == DataType.IM_LINE_SCIENCE
    assert sub16.get_data_type('DATA', spw='20~25') is None

    # 3. ObservingRun virtual SPW range query
    chunks = obs_run.get_measurement_sets_of_type([DataType.IM_LINE_SCIENCE], source='TargetA', spw='0~1', msonly=True)
    assert chunks == [sub16]

    # 4. Field without source in SubMS.get_fields
    class MockFieldNoSource:
        def __init__(self, field_id, name):
            self.id = field_id
            self.name = name
            self.source = None

    parent_ms.fields.append(MockFieldNoSource(99, 'NoSourceField'))
    fields = sub16.get_fields()
    # Should safely filter without AttributeError
    assert all(f.id != 99 for f in fields)

    # 5. get_real_spw_id_by_name directly with SubMS
    spw_name = parent_ms.get_spectral_window(16).name
    assert obs_run.get_real_spw_id_by_name(spw_name, sub16) == 16


def test_create_logical_targets_ms(mock_observing_run):
    """Test synthesis of logical MeasurementSet parent for partitioned SubMS slices."""
    obs_run, raw_ms = mock_observing_run

    sub16 = SubMS(
        name='/path/to/uid___A002_X123_X456_targets.spw16.ms',
        parent_ms=raw_ms,
        source_name='TargetA',
        real_spw_id=16,
        virtual_spw_id=0,
        field_ids=[0],
        data_type=DataType.REGCAL_CONTLINE_SCIENCE,
    )
    sub18 = SubMS(
        name='/path/to/uid___A002_X123_X456_targets.spw18.ms',
        parent_ms=raw_ms,
        source_name='TargetA',
        real_spw_id=18,
        virtual_spw_id=1,
        field_ids=[0],
        data_type=DataType.REGCAL_CONTLINE_SCIENCE,
    )

    raw_ms.acs_software_version = '28ab550e9d'
    raw_ms.acs_software_build_version = 'ONLINE-CYCLE10-B-34-2024-04-17-05-00-00'

    logical_ms = MeasurementSet.create_logical_targets_ms(
        raw_ms=raw_ms,
        name='/path/to/uid___A002_X123_X456_targets.ms',
        sub_mses=[sub16, sub18],
        data_type=DataType.REGCAL_CONTLINE_SCIENCE,
    )

    # 1. Verification of logical status and provenance
    assert logical_ms.is_logical is True
    assert logical_ms.name == '/path/to/uid___A002_X123_X456_targets.ms'
    assert logical_ms.basename == 'uid___A002_X123_X456_targets.ms'
    assert logical_ms.origin_ms == raw_ms.name
    assert logical_ms.session == raw_ms.session

    # 2. Metadata inheritance
    assert logical_ms.acs_software_version == '28ab550e9d'
    assert logical_ms.acs_software_build_version == 'ONLINE-CYCLE10-B-34-2024-04-17-05-00-00'
    assert sub16.acs_software_version == '28ab550e9d'
    assert sub16.acs_software_build_version == 'ONLINE-CYCLE10-B-34-2024-04-17-05-00-00'
    assert logical_ms.antenna_array == raw_ms.antenna_array
    assert len(logical_ms.antennas) == 2
    assert len(logical_ms.fields) == 1
    assert logical_ms.fields[0].name == 'TargetA_0'
    assert len(logical_ms.spectral_windows) == 2
    spw_ids = [s.id for s in logical_ms.spectral_windows]
    assert spw_ids == [16, 18]

    # 3. Child SubMS relationship and re-parenting
    assert logical_ms.has_subms() is True
    assert logical_ms.has_subms(DataType.REGCAL_CONTLINE_SCIENCE) is True
    assert not logical_ms.has_subms(DataType.RAW)
    assert len(logical_ms.sub_mses) == 2
    assert sub16.parent_ms is logical_ms
    assert sub18.parent_ms is logical_ms
    # sub_ms.origin_ms resolves through logical_ms to raw_ms
    assert sub16.origin_ms == raw_ms.name
    assert sub18.origin_ms == raw_ms.name

    # 4. Registration into ObservingRun
    obs_run.add_measurement_set(logical_ms)
    assert len(obs_run.measurement_sets) == 2
    assert obs_run.measurement_sets[1] is logical_ms

    # 5. Queries via ObservingRun
    assert obs_run.get_ms(logical_ms.name) is logical_ms
    assert obs_run.get_ms(sub16.name) is sub16
    assert obs_run.get_ms(os.path.basename(sub18.name)) is sub18

    # Top-level query returns logical parent MS
    top_mses = obs_run.get_measurement_sets_of_type([DataType.REGCAL_CONTLINE_SCIENCE], msonly=True)
    assert top_mses == [logical_ms]

    # Target + SPW query returns specific SubMS slice
    slice_16 = obs_run.get_measurement_sets_of_type(
        [DataType.REGCAL_CONTLINE_SCIENCE], source='TargetA', spw='0', msonly=True
    )
    assert slice_16 == [sub16]

    slice_18 = obs_run.get_measurement_sets_of_type(
        [DataType.REGCAL_CONTLINE_SCIENCE], source='TargetA', spw='1', msonly=True
    )
    assert slice_18 == [sub18]

    # 6. Test get_subms_path and get_subms_paths
    assert logical_ms.get_subms_path(spw=16) == sub16.name
    assert logical_ms.get_subms_paths(spw='16,18') == [sub16.name, sub18.name]
    assert logical_ms.get_subms_paths(spw='16:0~127') == [sub16.name]
    assert sub16.get_subms_path() == sub16.name
    assert sub16.get_subms_paths() == [sub16.name]
    assert sub16.has_subms() is False
    assert sub16.get_subms() == [sub16]
