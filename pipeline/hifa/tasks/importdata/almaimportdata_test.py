from unittest import mock

from pipeline.infrastructure.launcher import Context
from pipeline.hifa.tasks.importdata import almaimportdata


@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.fluxes.import_flux', return_value=['combined_result'])
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.fluxes.export_flux_from_result')
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.urllib.request.urlopen')
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.dbfluxes.get_setjy_results', return_value=(['result'], 'OK'))
def test_get_fluxes_primary_success(mock_get_setjy, mock_urlopen, mock_export, mock_import):
    context = Context(name='test_get_fluxes_primary_success')
    # Create a mock observing run with measurement_sets list
    observing_run = mock.Mock()
    observing_run.measurement_sets = []

    inputs = almaimportdata.ALMAImportDataInputs(context=context, dbservice=True)
    obj = almaimportdata.SerialALMAImportData(inputs=inputs)

    result = obj._get_fluxes(context, observing_run)

    assert result[0] == 'FIRSTURL', "Should use primary flux service"
    assert result[1] == ['combined_result'], "Should return combined results"
    assert result[2] == 'OK', "Should return QA status"


@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.fluxes.import_flux', return_value=['combined_result'])
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.fluxes.export_flux_from_result')
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.dbfluxes.get_setjy_results', return_value=(['result'], 'OK'))
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.LOG')
def test_get_fluxes_backup_success(mock_log, mock_get_setjy, mock_export, mock_import):
    context = Context(name='test_get_fluxes_backup_success')
    observing_run = mock.Mock()
    observing_run.measurement_sets = []

    inputs = almaimportdata.ALMAImportDataInputs(context=context, dbservice=True)
    obj = almaimportdata.SerialALMAImportData(inputs=inputs)

    with mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.urllib.request.urlopen', 
                    side_effect=[Exception('Primary failed'), None]):
        result = obj._get_fluxes(context, observing_run)

        assert result[0] == 'BACKUPURL', "Should use backup flux service"
        assert result[1] == ['combined_result'], "Should return combined results"
        assert result[2] == 'OK', "Should return QA status"
        mock_log.warning.assert_called_once(), "Should log warning about primary failure"


@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.fluxes.import_flux', return_value=['combined_result'])
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.fluxes.export_flux_from_result')
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.fluxes.get_setjy_results', return_value=['local_result'])
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.urllib.request.urlopen', side_effect=Exception)
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.LOG')
def test_get_fluxes_both_fail_fallbacks(mock_log, mock_urlopen, mock_local_get_setjy, mock_export, mock_import):
    """When both URLs fail, fallback to local Source.xml and continue."""
    context = Context(name='test_get_fluxes_both_fail_fallbacks')
    observing_run = mock.Mock()
    observing_run.measurement_sets = []

    inputs = almaimportdata.ALMAImportDataInputs(context=context, dbservice=True)
    obj = almaimportdata.SerialALMAImportData(inputs=inputs)

    result = obj._get_fluxes(context, observing_run)

    # Expect fallback path
    assert result[0] == 'FAIL', "Should mark flux service as FAIL"
    assert result[1] == ['combined_result'], "Should still return combined results"
    assert result[2] is None, "QA status should be None in fallback"

    # Verify local fallback used and warning logged
    mock_local_get_setjy.assert_called_once_with(observing_run.measurement_sets)
    assert mock_log.warning.call_count == 2, "Should log two warnings (primary and backup failures)"


@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.fluxes.import_flux', return_value=['combined_result'])
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.fluxes.export_flux_from_result')
@mock.patch('pipeline.hifa.tasks.importdata.almaimportdata.fluxes.get_setjy_results', return_value=['local_result'])
def test_get_fluxes_dbservice_false(mock_get_setjy, mock_export, mock_import):
    context = Context(name='test_get_fluxes_dbservice_false')
    observing_run = mock.Mock()
    observing_run.measurement_sets = []

    inputs = almaimportdata.ALMAImportDataInputs(context=context, dbservice=False)
    obj = almaimportdata.SerialALMAImportData(inputs=inputs)

    result = obj._get_fluxes(context, observing_run)

    assert result[0] is None, "Flux service should be None when dbservice=False"
    assert result[1] == ['combined_result'], "Should return combined results from local source"
    assert result[2] is None, "QA status should be None when using local source"
    mock_get_setjy.assert_called_once_with(observing_run.measurement_sets), "Should use local flux"
