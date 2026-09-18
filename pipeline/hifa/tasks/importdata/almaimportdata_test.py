from unittest import mock

import pytest

from pipeline.infrastructure.launcher import Context
from pipeline.hifa.tasks.importdata import almaimportdata


@pytest.fixture
def context(tmp_path, monkeypatch, request):
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
    # Create a mock observing run with measurement_sets list
    observing_run = mock.Mock()
    observing_run.measurement_sets = []

    inputs = almaimportdata.ALMAImportDataInputs(context=context, dbservice=True)
    obj = almaimportdata.SerialALMAImportData(inputs=inputs)

    result = obj._get_fluxes(context, observing_run)

    assert result[0] == 'FIRSTURL', 'Should use primary flux service'
    assert result[1] == ['combined_result'], 'Should return combined results'
    assert result[2] == 'OK', 'Should return QA status'
    mock_get_setjy.assert_called_once_with(observing_run.measurement_sets, service_url='https://primary.test/sc/flux')


@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.fluxes.import_flux', return_value=['combined_result'])
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.fluxes.export_flux_from_result')
@mock.patch(
    'pipeline.hifa.tasks.importdata.almaimportdata.dbfluxes.check_service',
    return_value=('BACKUPURL', 'https://backup.test/sc/flux'),
)
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.dbfluxes.get_setjy_results', return_value=(['result'], 'OK'))
def test_get_fluxes_backup_success(mock_get_setjy, mock_check_service, mock_export, mock_import, context):
    observing_run = mock.Mock()
    observing_run.measurement_sets = []

    inputs = almaimportdata.ALMAImportDataInputs(context=context, dbservice=True)
    obj = almaimportdata.SerialALMAImportData(inputs=inputs)

    result = obj._get_fluxes(context, observing_run)

    assert result[0] == 'BACKUPURL', 'Should use backup flux service'
    assert result[1] == ['combined_result'], 'Should return combined results'
    assert result[2] == 'OK', 'Should return QA status'
    mock_get_setjy.assert_called_once_with(observing_run.measurement_sets, service_url='https://backup.test/sc/flux')


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
    observing_run = mock.Mock()
    observing_run.measurement_sets = []

    inputs = almaimportdata.ALMAImportDataInputs(context=context, dbservice=False)
    obj = almaimportdata.SerialALMAImportData(inputs=inputs)

    result = obj._get_fluxes(context, observing_run)

    assert result[0] is None, 'Flux service should be None when dbservice=False'
    assert result[1] == ['combined_result'], 'Should return combined results from local source'
    assert result[2] is None, 'QA status should be None when using local source'
    mock_get_setjy.assert_called_once_with(observing_run.measurement_sets), 'Should use local flux'
