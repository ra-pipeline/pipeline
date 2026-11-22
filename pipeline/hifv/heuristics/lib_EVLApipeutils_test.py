"""Unit tests for per-baseband delay helpers in pipeline/hifv/heuristics/lib_EVLApipeutils.py."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pipeline.hifv.heuristics.bandpass import do_bandpass
from pipeline.hifv.heuristics.lib_EVLApipeutils import (
    build_gaintable_spwmap,
    get_vla_baseband_spw_groups,
    get_vla_baseband_spwmap,
)
from pipeline.hifv.tasks.circfeedpolcal.circfeedpolcal import Circfeedpolcal, CircfeedpolcalInputs
from pipeline.hifv.tasks.finalcals.finalcals import Finalcals, FinalcalsInputs
from pipeline.hifv.tasks.semiFinalBPdcals.qa import semiFinalBPdcalsQAHandler
from pipeline.hifv.tasks.semiFinalBPdcals.semiFinalBPdcals import semiFinalBPdcals, semiFinalBPdcalsInputs
from pipeline.hifv.tasks.testBPdcals.testBPdcals import testBPdcals, testBPdcalsInputs
from pipeline.infrastructure.launcher import Context


def _make_mock_ms(all_spw_ids: list[int], baseband_groups: list[list[int]]) -> MagicMock:
    """Create a minimal mock MeasurementSet for baseband SPW tests."""
    mock_ms = MagicMock()
    mock_ms.name = 'test_small.ms'
    mock_ms.get_spectral_windows.return_value = [SimpleNamespace(id=i, specline_window=True) for i in all_spw_ids]
    mock_ms.get_vla_baseband_spws.return_value = baseband_groups
    return mock_ms


def test_get_vla_baseband_spw_groups_filters_and_sorts():
    """Test filtering and sorting of baseband SPW groups."""
    mock_ms = _make_mock_ms([0, 1, 2, 3, 4, 5, 6, 7], [[3, 2], [5, 4], [7, 6]])

    assert get_vla_baseband_spw_groups(mock_ms, spw='2,3,4,5') == [[2, 3], [4, 5]]
    assert get_vla_baseband_spw_groups(mock_ms) == [[2, 3], [4, 5], [6, 7]]


def test_get_vla_baseband_spw_groups_fallback():
    """Test fallback when get_vla_baseband_spws returns empty."""
    mock_ms = _make_mock_ms([0, 1, 2], [])
    assert get_vla_baseband_spw_groups(mock_ms, spw='2,0,1') == [[0, 1, 2]]


def test_get_vla_baseband_spwmap_non_contiguous():
    """Test spwmap construction with non-contiguous and non-science SPWs."""
    # SPWs 0, 1 are non-science; basebands are [2, 3, 4] and [7, 6, 5]
    mock_ms = _make_mock_ms([0, 1, 2, 3, 4, 5, 6, 7], [[2, 3, 4], [7, 6, 5]])
    assert get_vla_baseband_spwmap(mock_ms) == [0, 1, 2, 2, 2, 5, 5, 5]


def test_get_vla_baseband_spwmap_empty():
    """Test spwmap returns empty list when MS has no spectral windows."""
    mock_ms = _make_mock_ms([], [])
    assert get_vla_baseband_spwmap(mock_ms) == []


def test_get_vla_baseband_spwmap_fallback_with_spw():
    """Test spwmap fallback maps selected SPWs to their lowest SPW ID."""
    mock_ms = _make_mock_ms([0, 1, 2, 3, 4], [])
    assert get_vla_baseband_spwmap(mock_ms, spw='2,3,4') == [0, 1, 2, 2, 2]


def test_build_gaintable_spwmap():
    """Test per-table spwmap list construction."""
    mock_ms = _make_mock_ms([0, 1, 2, 3], [[0, 1], [2, 3]])
    k_spwmap = [0, 0, 2, 2]
    tables = ['prior.tbl', 'delay.tbl', 'bpd.tbl']

    assert build_gaintable_spwmap(mock_ms, tables, 'delay.tbl') == [[], k_spwmap, []]
    assert build_gaintable_spwmap(mock_ms, tables, 'missing.tbl') == []
    assert build_gaintable_spwmap(mock_ms, tables, None) == []

    empty_ms = _make_mock_ms([], [])
    assert build_gaintable_spwmap(empty_ms, tables, 'delay.tbl') == []


def _make_mock_context(mock_ms: MagicMock) -> MagicMock:
    """Create a minimal mock Context for delaycal task tests."""
    msinfo = SimpleNamespace(
        delay_field_select_string='0',
        delay_scan_select_string='1,2',
    )
    context = MagicMock(spec=Context)
    context.observing_run = MagicMock()
    context.observing_run.get_ms.return_value = mock_ms
    context.evla = {'msinfo': {mock_ms.name: msinfo}}
    context.callibrary = MagicMock()
    context.callibrary.active.get_caltable.return_value = []
    return context


@patch('pipeline.hifv.heuristics.lib_EVLApipeutils.casa_tasks.gaincal')
@patch('pipeline.hifv.heuristics.lib_EVLApipeutils.uvrange', return_value='')
def test_testbpdcals_ktype_delaycal_per_baseband(mock_uvrange, mock_gaincal, tmp_path):
    """Test testBPdcals._do_ktype_delaycal runs gaincal per baseband with combine='scan,spw'."""
    mock_ms = _make_mock_ms([0, 1, 2, 3], [[0, 1], [2, 3]])
    context = _make_mock_context(mock_ms)
    inputs = testBPdcalsInputs(context=context, vis='test_small.ms')
    task = testBPdcals(inputs)
    task.parang = True
    task.setjy_results = []
    caltable = str(tmp_path / 'testdelay.tbl')

    def fake_execute(job):
        (tmp_path / 'testdelay.tbl').mkdir(exist_ok=True)

    task._executor = MagicMock(execute=MagicMock(side_effect=fake_execute))
    task._do_ktype_delaycal(caltable=caltable, addcaltable='', RefAntOutput=['ea01'], spw='0,1,2,3')

    assert mock_gaincal.call_count == 2
    first_call = mock_gaincal.call_args_list[0].kwargs
    second_call = mock_gaincal.call_args_list[1].kwargs
    assert first_call['spw'] == '0,1'
    assert first_call['combine'] == 'scan,spw'
    assert first_call['gaintype'] == 'K'
    assert first_call['append'] is False
    assert second_call['spw'] == '2,3'
    assert second_call['combine'] == 'scan,spw'
    assert second_call['append'] is True


@patch('pipeline.hifv.heuristics.lib_EVLApipeutils.casa_tasks.gaincal')
@patch('pipeline.hifv.heuristics.lib_EVLApipeutils.uvrange', return_value='')
def test_semifinalbpdcals_ktype_delaycal_per_baseband(mock_uvrange, mock_gaincal, tmp_path):
    """Test semiFinalBPdcals._do_ktype_delaycal runs gaincal per baseband with combine='scan,spw'."""
    mock_ms = _make_mock_ms([0, 1, 2, 3], [[0, 1], [2, 3]])
    context = _make_mock_context(mock_ms)
    inputs = semiFinalBPdcalsInputs(context=context, vis='test_small.ms')
    task = semiFinalBPdcals(inputs)
    task.parang = True
    task.setjy_results = []
    caltable = str(tmp_path / 'semifinaldelay.tbl')

    def fake_execute(job):
        (tmp_path / 'semifinaldelay.tbl').mkdir(exist_ok=True)

    task._executor = MagicMock(execute=MagicMock(side_effect=fake_execute))
    task._do_ktype_delaycal(caltable=caltable, addcaltable='', RefAntOutput=['ea01'], spw='0,1,2,3')

    assert mock_gaincal.call_count == 2
    assert mock_gaincal.call_args_list[0].kwargs['spw'] == '0,1'
    assert mock_gaincal.call_args_list[0].kwargs['combine'] == 'scan,spw'
    assert mock_gaincal.call_args_list[1].kwargs['spw'] == '2,3'
    assert mock_gaincal.call_args_list[1].kwargs['append'] is True


@patch('pipeline.hifv.heuristics.lib_EVLApipeutils.casa_tasks.gaincal')
@patch('pipeline.hifv.heuristics.lib_EVLApipeutils.uvrange', return_value='')
def test_finalcals_ktype_delaycal_per_baseband(mock_uvrange, mock_gaincal, tmp_path):
    """Test Finalcals._do_ktype_delaycal runs gaincal per baseband with combine='scan,spw'."""
    mock_ms = _make_mock_ms([0, 1, 2, 3], [[0, 1], [2, 3]])
    context = _make_mock_context(mock_ms)
    inputs = FinalcalsInputs(context=context, vis='test_small.ms')
    task = Finalcals(inputs)
    task.parang = True
    task.setjy_results = []
    caltable = str(tmp_path / 'finaldelay.tbl')

    def fake_execute(job):
        (tmp_path / 'finaldelay.tbl').mkdir(exist_ok=True)

    task._executor = MagicMock(execute=MagicMock(side_effect=fake_execute))
    task._do_ktype_delaycal(caltable=caltable, addcaltable='', refAnt='ea01', spw='0,1,2,3')

    assert mock_gaincal.call_count == 2
    assert mock_gaincal.call_args_list[0].kwargs['spw'] == '0,1'
    assert mock_gaincal.call_args_list[0].kwargs['combine'] == 'scan,spw'
    assert mock_gaincal.call_args_list[1].kwargs['spw'] == '2,3'
    assert mock_gaincal.call_args_list[1].kwargs['append'] is True


@patch('pipeline.hifv.tasks.semiFinalBPdcals.qa.LOG')
def test_semifinalbpdcals_qa_check_spw_flagged_delay_per_baseband(mock_log):
    """Test QA SPW check for Delay only expects representative baseband SPWs."""
    mock_ms = _make_mock_ms([0, 1, 2, 3], [[0, 1], [2, 3]])
    handler = semiFinalBPdcalsQAHandler()

    # Only representative SPWs (0 and 2) are present in a per-baseband K-table
    table = {'spw': {0: {0: {'fraction': 0.0}}, 2: {0: {'fraction': 0.0}}}}
    handler._check_spw_flagged(table, 'C', mock_ms, 'Delay')
    mock_log.warning.assert_not_called()

    # Missing representative SPW 2 should warn once
    table_missing = {'spw': {0: {0: {'fraction': 0.0}}}}
    handler._check_spw_flagged(table_missing, 'C', mock_ms, 'Delay')
    mock_log.warning.assert_called_once()


@patch('pipeline.hifv.tasks.semiFinalBPdcals.qa.LOG')
def test_semifinalbpdcals_qa_check_spw_flagged_empty_baseband_groups(mock_log):
    """Test QA SPW check falls back to checking all SPWs if baseband groups are empty."""
    mock_ms = _make_mock_ms([0, 1], [])
    handler = semiFinalBPdcalsQAHandler()

    handler._check_spw_flagged({'spw': {0: {0: {'fraction': 0.0}}}}, 'C', mock_ms, 'Delay')
    mock_log.warning.assert_called_once()


def _make_full_mock_context(mock_ms: MagicMock) -> MagicMock:
    """Create a mock Context with bandpass/testgainscans info for spwmap propagation tests."""
    mock_ms.get_vla_tst_bpass_spw.return_value = '0,1,2,3'
    mock_ms.get_scans.return_value = [SimpleNamespace(fields=(SimpleNamespace(id=0),))]
    msinfo = SimpleNamespace(
        delay_field_select_string='0',
        delay_scan_select_string='1,2',
        bandpass_field_select_string='0',
        bandpass_scan_select_string='1,2',
        testgainscans='1,2',
        calibrator_scan_select_string='1,2',
    )
    context = MagicMock(spec=Context)
    context.observing_run = MagicMock()
    context.observing_run.get_ms.return_value = mock_ms
    context.evla = {'msinfo': {mock_ms.name: msinfo}}
    context.callibrary = MagicMock()
    context.callibrary.active.get_caltable.return_value = ['prior.tbl']
    context.results = [SimpleNamespace(read=lambda: SimpleNamespace(setjy_results=[]))]
    return context


@patch('pipeline.hifv.tasks.testBPdcals.testBPdcals.casa_tasks.applycal')
@patch('pipeline.hifv.tasks.testBPdcals.testBPdcals.casa_tasks.gaincal')
@patch('pipeline.hifv.tasks.testBPdcals.testBPdcals.uvrange', return_value='')
def test_testbpdcals_spwmap_propagation(mock_uvrange, mock_gaincal, mock_applycal, tmp_path):
    """Test testBPdcals passes per-table spwmap for ktypecaltable in bpdgains and applycal."""
    mock_ms = _make_mock_ms([0, 1, 2, 3], [[0, 1], [2, 3]])
    context = _make_full_mock_context(mock_ms)
    task = testBPdcals(testBPdcalsInputs(context=context, vis='test_small.ms'))
    task.parang = True
    task.setjy_results = []
    task._executor = MagicMock()

    ktbl = str(tmp_path / 'k.tbl')
    bpd = str(tmp_path / 'bpd.tbl')
    bp = str(tmp_path / 'bp.tbl')
    for p in (ktbl, bpd, bp):
        (tmp_path / p.split('/')[-1]).mkdir()

    task._do_gtype_bpdgains(
        caltable=str(tmp_path / 'out.tbl'), addcaltable=ktbl, RefAntOutput=['ea01'], spwlist=['0', '1', '2', '3']
    )
    assert mock_gaincal.call_args.kwargs['spwmap'] == [[], [0, 0, 2, 2]]

    task._do_applycal(ktypecaltable=ktbl, bpdgain_touse=bpd, bpcaltable=bp, interp=[''], spw='0,1,2,3')
    assert mock_applycal.call_args.kwargs['spwmap'] == [[], [0, 0, 2, 2], [], []]


@patch('pipeline.hifv.tasks.semiFinalBPdcals.semiFinalBPdcals.casa_tasks.applycal')
@patch('pipeline.hifv.tasks.semiFinalBPdcals.semiFinalBPdcals.casa_tasks.gaincal')
@patch('pipeline.hifv.tasks.semiFinalBPdcals.semiFinalBPdcals.uvrange', return_value='')
def test_semifinalbpdcals_spwmap_propagation(mock_uvrange, mock_gaincal, mock_applycal, tmp_path):
    """Test semiFinalBPdcals passes per-table spwmap for ktypecaltable in bpdgains and applycal."""
    mock_ms = _make_mock_ms([0, 1, 2, 3], [[0, 1], [2, 3]])
    context = _make_full_mock_context(mock_ms)
    task = semiFinalBPdcals(semiFinalBPdcalsInputs(context=context, vis='test_small.ms'))
    task.parang = True
    task.setjy_results = []
    task._executor = MagicMock()

    ktbl = str(tmp_path / 'k.tbl')
    bp = str(tmp_path / 'bp.tbl')
    (tmp_path / 'k.tbl').mkdir()
    (tmp_path / 'bp.tbl').mkdir()

    task._do_gtype_bpdgains(
        caltable=str(tmp_path / 'out.tbl'), addcaltable=ktbl, RefAntOutput=['ea01'], spwlist=['0', '1', '2', '3']
    )
    assert mock_gaincal.call_args.kwargs['spwmap'] == [[], [0, 0, 2, 2]]

    task._do_applycal(ktypecaltable=ktbl, bpcaltable=bp, interp=[''], spw='0,1,2,3')
    assert mock_applycal.call_args.kwargs['spwmap'] == [[], [0, 0, 2, 2], []]


@patch('pipeline.hifv.tasks.finalcals.finalcals.casa_tasks.applycal')
@patch('pipeline.hifv.tasks.finalcals.finalcals.casa_tasks.gaincal')
@patch('pipeline.hifv.tasks.finalcals.finalcals.uvrange', return_value='')
def test_finalcals_spwmap_propagation(mock_uvrange, mock_gaincal, mock_applycal, tmp_path):
    """Test Finalcals passes per-table spwmap for ktypecaltable in bpdgains, avgphasegaincal, and applycal."""
    mock_ms = _make_mock_ms([0, 1, 2, 3], [[0, 1], [2, 3]])
    context = _make_full_mock_context(mock_ms)
    context.callibrary.active.get_caltable.return_value = []
    task = Finalcals(FinalcalsInputs(context=context, vis='test_small.ms'))
    task.parang = True
    task.setjy_results = []
    task._executor = MagicMock()

    ktbl = str(tmp_path / 'k.tbl')
    bp = str(tmp_path / 'bp.tbl')
    avgp = str(tmp_path / 'avgp.tbl')
    for name in ('k.tbl', 'bp.tbl', 'avgp.tbl'):
        (tmp_path / name).mkdir()

    task._do_gtype_bpdgains(
        caltable=str(tmp_path / 'out.tbl'), addcaltable=ktbl, refAnt='ea01', spwlist=['0', '1', '2', '3']
    )
    assert mock_gaincal.call_args.kwargs['spwmap'] == [[0, 0, 2, 2]]

    task._do_avgphasegaincal(caltable=avgp, refAnt='ea01', ktypecaltable=ktbl, bpcaltable=bp, spw='0,1,2,3')
    assert mock_gaincal.call_args.kwargs['spwmap'] == [[0, 0, 2, 2], []]

    task._do_applycal(ktypecaltable=ktbl, bpcaltable=bp, avgphasegaincaltable=avgp, interp='', spw='0,1,2,3')
    assert mock_applycal.call_args.kwargs['spwmap'] == [[0, 0, 2, 2], [], []]


@patch('pipeline.hifv.heuristics.bandpass.casa_tasks.bandpass')
@patch('pipeline.hifv.heuristics.bandpass.uvrange', return_value='')
def test_do_bandpass_spwmap_propagation(mock_uvrange, mock_bandpass, tmp_path):
    """Test do_bandpass passes per-table spwmap for ktypecaltable."""
    mock_ms = _make_mock_ms([0, 1, 2, 3], [[0, 1], [2, 3]])
    context = _make_full_mock_context(mock_ms)
    executor = MagicMock()

    ktbl = str(tmp_path / 'k.tbl')
    bpd = str(tmp_path / 'bpd.tbl')
    (tmp_path / 'k.tbl').mkdir()
    (tmp_path / 'bpd.tbl').mkdir()

    do_bandpass(
        vis='test_small.ms',
        caltable=str(tmp_path / 'bp.tbl'),
        context=context,
        RefAntOutput=['ea01'],
        spw='0,1,2,3',
        ktypecaltable=ktbl,
        bpdgain_touse=bpd,
        solint='inf',
        append=False,
        executor=executor,
        solnorm=False,
        bpsolint_mode='off',
        band='C',
    )
    assert mock_bandpass.call_args.kwargs['spwmap'] == [[], [0, 0, 2, 2], []]


def test_circfeedpolcal_do_spwmap_delegates_to_baseband_spwmap():
    """Test Circfeedpolcal.do_spwmap handles non-contiguous SPWs via get_vla_baseband_spwmap."""
    mock_ms = _make_mock_ms([0, 1, 2, 3, 4], [[1, 2], [3, 4]])
    context = _make_mock_context(mock_ms)
    task = Circfeedpolcal(CircfeedpolcalInputs(context=context, vis='test_small.ms'))
    assert task.do_spwmap() == [0, 1, 1, 3, 3]
