"""Tests for ALMA import flux selection and service status."""

from __future__ import annotations

from io import BytesIO
from unittest import mock

import pytest

from pipeline.hifa.tasks.importdata import almaimportdata
from pipeline.infrastructure.launcher import Context


@pytest.fixture
def context(tmp_path, monkeypatch, request):
    """Create an import context in the test's temporary directory."""
    monkeypatch.chdir(tmp_path)
    return Context(name=request.node.name)


@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.fluxes.import_flux', return_value=['combined_result'])
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.fluxes.export_flux_from_result')
@mock.patch(
    'pipeline.hifa.tasks.importdata.almaimportdata.dbfluxes.check_service',
    return_value=('FIRSTURL', 'https://primary.test/sc/flux'),
)
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.dbfluxes.get_setjy_results', return_value=(['result'], 'OK'))
def test_get_fluxes_primary_success(mock_get_setjy, mock_check_service, mock_export, mock_import, context):
    """Use the endpoint selected by the primary probe."""
    # Create a mock observing run with measurement_sets list
    observing_run = mock.Mock()
    observing_run.measurement_sets = []

    inputs = almaimportdata.ALMAImportDataInputs(context=context, dbservice=True)
    obj = almaimportdata.SerialALMAImportData(inputs=inputs)

    result = obj._get_fluxes(context, observing_run)

    assert result[0] == 'FIRSTURL', 'Should use primary flux service'
    assert result[1] == ['combined_result'], 'Should return combined results'
    assert result[2] == 'OK', 'Should return QA status'
    mock_get_setjy.assert_called_once_with(observing_run.measurement_sets, client=mock.ANY)
    assert mock_get_setjy.call_args.kwargs['client'].service_url == 'https://primary.test/sc/flux'


@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.fluxes.import_flux', return_value=['combined_result'])
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.fluxes.export_flux_from_result')
@mock.patch(
    'pipeline.hifa.tasks.importdata.almaimportdata.dbfluxes.check_service',
    return_value=('BACKUPURL', 'https://backup.test/sc/flux'),
)
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.dbfluxes.get_setjy_results', return_value=(['result'], 'OK'))
def test_get_fluxes_backup_success(mock_get_setjy, mock_check_service, mock_export, mock_import, context):
    """Use the endpoint selected by the backup probe."""
    observing_run = mock.Mock()
    observing_run.measurement_sets = []

    inputs = almaimportdata.ALMAImportDataInputs(context=context, dbservice=True)
    obj = almaimportdata.SerialALMAImportData(inputs=inputs)

    result = obj._get_fluxes(context, observing_run)

    assert result[0] == 'BACKUPURL', 'Should use backup flux service'
    assert result[1] == ['combined_result'], 'Should return combined results'
    assert result[2] == 'OK', 'Should return QA status'
    mock_get_setjy.assert_called_once_with(observing_run.measurement_sets, client=mock.ANY)
    assert mock_get_setjy.call_args.kwargs['client'].service_url == 'https://backup.test/sc/flux'


@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.fluxes.import_flux', return_value=['combined_result'])
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.fluxes.export_flux_from_result')
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.fluxes.get_setjy_results', return_value=['local_result'])
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.dbfluxes.check_service', return_value=('FAIL', None))
def test_get_fluxes_both_fail_fallbacks(
    mock_check_service,
    mock_local_get_setjy,
    mock_export,
    mock_import,
    context,
):
    """When both URLs fail, fallback to local Source.xml and continue."""
    observing_run = mock.Mock()
    observing_run.measurement_sets = []

    inputs = almaimportdata.ALMAImportDataInputs(context=context, dbservice=True)
    obj = almaimportdata.SerialALMAImportData(inputs=inputs)

    result = obj._get_fluxes(context, observing_run)

    # Expect fallback path
    assert result[0] == 'FAIL', 'Should mark flux service as FAIL'
    assert result[1] == ['combined_result'], 'Should still return combined results'
    assert result[2] is None, 'QA status should be None in fallback'

    # Verify local fallback used
    mock_local_get_setjy.assert_called_once_with(observing_run.measurement_sets)


@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.fluxes.import_flux', return_value=['combined_result'])
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.fluxes.export_flux_from_result')
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.fluxes.get_setjy_results', return_value=['local_result'])
def test_get_fluxes_dbservice_false(mock_get_setjy, mock_export, mock_import, context):
    """Read local fluxes when online catalogue lookup is disabled."""
    observing_run = mock.Mock()
    observing_run.measurement_sets = []

    inputs = almaimportdata.ALMAImportDataInputs(context=context, dbservice=False)
    obj = almaimportdata.SerialALMAImportData(inputs=inputs)

    result = obj._get_fluxes(context, observing_run)

    assert result[0] is None, 'Flux service should be None when dbservice=False'
    assert result[1] == ['combined_result'], 'Should return combined results from local source'
    assert result[2] is None, 'QA status should be None when using local source'
    mock_get_setjy.assert_called_once_with(observing_run.measurement_sets), 'Should use local flux'


def test_get_fluxes_reports_backup_after_query_failover(context: Context) -> None:
    """Record backup usage when an actual query fails over after the initial probe."""
    primary_url = 'https://primary.test/sc/flux'
    backup_url = 'https://backup.test/sc/flux'
    observing_run = mock.Mock(measurement_sets=[])
    inputs = almaimportdata.ALMAImportDataInputs(context=context, dbservice=True)
    obj = almaimportdata.SerialALMAImportData(inputs=inputs)

    def get_setjy_results(mses: list, *, client: almaimportdata.dbfluxes.FluxServiceClient) -> tuple[list, list]:
        client.query(almaimportdata.dbfluxes.TEST_OBS_TIME, '1e11', 'TestSrc')
        return [], []

    with (
        mock.patch.object(almaimportdata.dbfluxes, 'get_flux_urls', return_value=(primary_url, backup_url)),
        mock.patch.object(almaimportdata.dbfluxes, 'check_service', return_value=('FIRSTURL', primary_url)),
        mock.patch.object(almaimportdata.dbfluxes, 'get_setjy_results', side_effect=get_setjy_results),
        mock.patch.object(
            almaimportdata.dbfluxes, 'fluxservice', side_effect=[OSError('primary unavailable'), {}]
        ) as query,
        mock.patch.object(almaimportdata.fluxes, 'export_flux_from_result'),
        mock.patch.object(almaimportdata.fluxes, 'import_flux', return_value=['combined_result']),
    ):
        result = obj._get_fluxes(context, observing_run)

    assert result == ('BACKUPURL', ['combined_result'], [])
    assert [call.args[0] for call in query.call_args_list] == [primary_url, backup_url]


@pytest.mark.parametrize('backup_usable', [False, True])
def test_get_fluxes_handles_unusable_response_after_successful_probe(context: Context, backup_usable: bool) -> None:
    """Use backup or local measurements when an actual response fails validation."""
    primary_url = 'https://primary.test/sc/flux'
    backup_url = 'https://backup.test/sc/flux'
    valid_response = (
        b'<VOTABLE><FIELD name="StatusCode"/><FIELD name="FluxDensity"/><FIELD name="SpectralIndex"/>'
        b'<TR><TD>0</TD><TD>2.0</TD><TD>-0.5</TD></TR></VOTABLE>'
    )
    ms = mock.Mock()
    ms.name = 'test_small.ms'
    source = mock.Mock()
    source.name = 'TestSrc'
    source.fields = [mock.Mock(id=0)]
    spw = mock.Mock(id=1)
    spw.centre_frequency.to_units.return_value = 1.0e11
    ms.get_spectral_windows.return_value = [spw]
    ms.get_spectral_window.return_value = spw
    local_measurement = mock.Mock(spw_id=1)
    observing_run = mock.Mock(measurement_sets=[ms])
    inputs = almaimportdata.ALMAImportDataInputs(context=context, dbservice=True)
    obj = almaimportdata.SerialALMAImportData(inputs=inputs)
    original_observing_run = context.observing_run

    with (
        mock.patch.object(almaimportdata.dbfluxes, 'get_flux_urls', return_value=(primary_url, backup_url)),
        mock.patch.object(
            almaimportdata.dbfluxes.urllib.request,
            'urlopen',
            side_effect=[
                BytesIO(valid_response),
                BytesIO(b'<VOTABLE/>'),
                BytesIO(valid_response if backup_usable else b'<VOTABLE/>'),
            ],
        ) as urlopen,
        mock.patch.object(
            almaimportdata.dbfluxes.utils, 'get_epoch_as_datetime', return_value=almaimportdata.dbfluxes.TEST_OBS_TIME
        ),
        mock.patch.object(almaimportdata.fluxes, 'read_fluxes_nodb', return_value={source: [local_measurement]}),
        mock.patch.object(almaimportdata.fluxes, 'export_flux_from_result') as export,
        mock.patch.object(almaimportdata.fluxes, 'import_flux', return_value=['combined_result']),
    ):
        result = obj._get_fluxes(context, observing_run)

    assert result == ('BACKUPURL' if backup_usable else 'FIRSTURL', ['combined_result'], [])
    assert [call.args[0].full_url.split('?')[0] for call in urlopen.call_args_list] == [primary_url] * 2 + [backup_url]
    exported_measurement = export.call_args.args[0][0].measurements[0][0]
    assert (exported_measurement is local_measurement) == (not backup_usable)
    assert context.observing_run is original_observing_run
