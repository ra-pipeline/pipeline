"""Offline tests for flux catalogue requests, failover, and local fallback."""

from __future__ import annotations

import collections
import copy
import datetime
import ssl
import urllib.error
from http.client import IncompleteRead
from io import BytesIO
from unittest import mock

import pytest

from pipeline.domain import FluxMeasurement, measures
from pipeline.hifa.tasks.importdata import dbfluxes

PRIMARY_URL = 'https://primary.test/sc/flux'
BACKUP_URL = 'https://backup.test/sc/flux'
CATALOGUE_XML = b"""<VOTABLE><RESOURCE><TABLE>
<FIELD name="StatusCode"/><FIELD name="FluxDensity"/><FIELD name="SpectralIndex"/>
<FIELD name="Nearest Measurement Date"/><FIELD name="Version"/>
<DATA><TABLEDATA><TR><TD>0</TD><TD>2.0</TD><TD>-0.5</TD><TD>1</TD><TD>test</TD></TR></TABLEDATA></DATA>
</TABLE></RESOURCE></VOTABLE>"""
type FluxData = tuple[mock.Mock, mock.Mock, collections.defaultdict[mock.Mock, list[FluxMeasurement]]]


@pytest.fixture(autouse=True)
def offline_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use synthetic endpoints and reject unexpected network access."""
    monkeypatch.setattr(dbfluxes, 'get_flux_urls', lambda: (PRIMARY_URL, BACKUP_URL))
    monkeypatch.setattr(
        dbfluxes.urllib.request, 'urlopen', mock.Mock(side_effect=AssertionError('Unexpected HTTP request'))
    )


@pytest.fixture
def flux_data() -> FluxData:
    """Provide a science window and its local flux measurement."""
    spw = mock.Mock(id=1)
    spw.centre_frequency.to_units.return_value = 1.0e11
    source = mock.Mock()
    source.name = 'TestSrc'
    source.fields = [mock.Mock(id=0)]
    ms = mock.Mock()
    ms.name = 'test_small.ms'
    ms.sources = [source]
    ms.start_time = mock.sentinel.start_time
    ms.get_spectral_windows.return_value = [spw]
    ms.get_spectral_window.return_value = spw
    measurement = FluxMeasurement(1, measures.FluxDensity(1.0, measures.FluxDensityUnits.JANSKY))
    return ms, source, collections.defaultdict(list, {source: [measurement]})


def test_fluxservice_reads_source_catalogue_columns_by_field_name():
    """Read named columns independently of their position in the catalogue schema."""
    xml_response = b"""<?xml version="1.0"?>
<VOTABLE>
  <RESOURCE>
    <TABLE>
      <FIELD datatype="int" width="1" name="StatusCode"></FIELD>
      <FIELD datatype="char" name="SourceName" arraysize="16"/>
      <FIELD unit="Hz" datatype="double" width="10" name="Frequency"/>
      <FIELD datatype="char" name="Date" arraysize="32"/>
      <FIELD unit="Jansky" datatype="double" width="10" name="FluxDensity"/>
      <FIELD unit="Jansky" datatype="double" width="10" name="FluxDensityError"/>
      <FIELD unit="Unitless" datatype="double" width="10" name="SpectralIndex"/>
      <FIELD unit="Unitless" datatype="double" width="10" name="SpectralIndexError"/>
      <FIELD unit="Unitless" datatype="double" width="10" name="Curvature"/>
      <FIELD unit="Unitless" datatype="double" width="10" name="CurvatureError"/>
      <FIELD datatype="int" width="10" name="DataConditions"></FIELD>
      <FIELD datatype="float" width="10" name="Nearest Measurement Date"></FIELD>
      <FIELD datatype="char" name="Verbose" arraysize="256000"/>
      <FIELD datatype="char" name="Version" arraysize="20"></FIELD>
      <DATA>
        <TABLEDATA>
          <TR>
            <TD>0</TD>
            <TD>J1427-4206</TD>
            <TD>86837309056.169219970703125</TD>
            <TD>27-March-2013</TD>
            <TD>1.234</TD>
            <TD>0.056</TD>
            <TD>-0.789</TD>
            <TD>0.012</TD>
            <TD>0.345</TD>
            <TD>0.067</TD>
            <TD>9001</TD>
            <TD>12.5</TD>
            <TD>extra source catalogue details</TD>
            <TD>2026AUG</TD>
          </TR>
        </TABLEDATA>
      </DATA>
    </TABLE>
  </RESOURCE>
</VOTABLE>
"""
    obs_time = datetime.datetime(2013, 3, 27, 7, 53, 3, 168000, tzinfo=datetime.timezone.utc)

    with mock.patch(
        'pipeline.hifa.tasks.importdata.dbfluxes.urllib.request.urlopen', return_value=BytesIO(xml_response)
    ):
        fluxdict = dbfluxes.fluxservice(
            'https://example.test/sc/flux',
            obs_time,
            '86837309056.169219970703125',
            'J1427-4206',
        )

    assert fluxdict['statuscode'] == '0'
    assert fluxdict['sourcename'] == 'J1427-4206'
    assert fluxdict['dbfrequency'] == '86837309056.169219970703125'
    assert fluxdict['date'] == '27-March-2013'
    assert fluxdict['fluxdensity'] == '1.234'
    assert fluxdict['fluxdensityerror'] == '0.056'
    assert fluxdict['spectralindex'] == '-0.789'
    assert fluxdict['spectralindexerror'] == '0.012'
    assert fluxdict['dataconditions'] == '9001'
    assert fluxdict['ageOfNearestMonitorPoint'] == '12.5'
    assert fluxdict['version'] == '2026AUG'
    assert fluxdict['clarification'] is None


def test_fluxservice_user_agent_and_retries():
    """Test request headers and retry behavior for the flux service."""
    xml_response = b"""<?xml version="1.0"?>
<VOTABLE><RESOURCE><TABLE>
  <FIELD datatype="int" width="1" name="StatusCode"></FIELD>
  <FIELD datatype="char" name="SourceName" arraysize="16"/>
  <FIELD unit="Hz" datatype="double" width="10" name="Frequency"/>
  <FIELD datatype="char" name="Date" arraysize="32"/>
  <FIELD unit="Jansky" datatype="double" width="10" name="FluxDensity"/>
  <FIELD unit="Jansky" datatype="double" width="10" name="FluxDensityError"/>
  <FIELD unit="Unitless" datatype="double" width="10" name="SpectralIndex"/>
  <FIELD unit="Unitless" datatype="double" width="10" name="SpectralIndexError"/>
  <FIELD datatype="int" width="10" name="DataConditions"></FIELD>
  <FIELD datatype="float" width="10" name="Nearest Measurement Date"></FIELD>
  <FIELD datatype="char" name="Version" arraysize="20"></FIELD>
  <FIELD datatype="char" name="Clarification" arraysize="100"></FIELD>
  <DATA><TABLEDATA><TR>
    <TD>0</TD><TD>J1427-4206</TD><TD>86837309056.169219970703125</TD>
    <TD>27-March-2013</TD><TD>1.234</TD><TD>0.056</TD><TD>-0.789</TD><TD>0.012</TD>
    <TD>111</TD><TD>12.5</TD><TD>2026JUN</TD><TD></TD>
  </TR></TABLEDATA></DATA>
</TABLE></RESOURCE></VOTABLE>"""
    obs_time = datetime.datetime(2013, 3, 27, 7, 53, 3, 168000, tzinfo=datetime.timezone.utc)

    with (
        mock.patch(
            'pipeline.hifa.tasks.importdata.dbfluxes.urllib.request.urlopen',
            side_effect=[
                urllib.error.URLError('timeout'),
                urllib.error.URLError('timeout'),
                BytesIO(xml_response),
            ],
        ) as mock_urlopen,
        mock.patch('pipeline.hifa.tasks.importdata.dbfluxes.time.sleep') as mock_sleep,
    ):
        fluxdict = dbfluxes.fluxservice(
            'https://example.test/sc/flux',
            obs_time,
            '86837309056.169219970703125',
            'J1427-4206',
            retries=2,
            retry_delay=0.01,
        )

    assert mock_urlopen.call_count == 3
    assert mock_sleep.call_args_list == [mock.call(0.01), mock.call(0.02)]
    req = mock_urlopen.call_args_list[0][0][0]
    assert req.get_header('User-agent') == 'Mozilla/5.0'
    assert req.get_header('Accept') == '*/*'
    assert fluxdict['sourcename'] == 'J1427-4206'

    # Test custom headers override
    with mock.patch(
        'pipeline.hifa.tasks.importdata.dbfluxes.urllib.request.urlopen',
        return_value=BytesIO(xml_response),
    ) as mock_urlopen_custom:
        dbfluxes.fluxservice(
            'https://example.test/sc/flux',
            obs_time,
            '86837309056.169219970703125',
            'J1427-4206',
            headers={'User-Agent': 'CustomAgent/2.0'},
        )
        custom_req = mock_urlopen_custom.call_args[0][0]
        assert custom_req.get_header('User-agent') == 'CustomAgent/2.0'


def test_fluxservice_raises_on_persistent_failure():
    """Test that persistent flux service failures are raised."""
    obs_time = datetime.datetime(2013, 3, 27, 7, 53, 3, 168000, tzinfo=datetime.timezone.utc)
    with (
        mock.patch(
            'pipeline.hifa.tasks.importdata.dbfluxes.urllib.request.urlopen',
            side_effect=urllib.error.URLError('connection refused'),
        ) as mock_urlopen,
        mock.patch('pipeline.hifa.tasks.importdata.dbfluxes.time.sleep') as mock_sleep,
    ):
        with pytest.raises(IOError):
            dbfluxes.fluxservice(
                'https://example.test/sc/flux',
                obs_time,
                '86837309056.169219970703125',
                'J1427-4206',
                retries=1,
                retry_delay=0.01,
            )

    assert mock_urlopen.call_count == 2
    mock_sleep.assert_called_once_with(0.01)


def test_check_service_primary_success():
    """Test selection of the primary flux service."""
    flux_url, _ = dbfluxes.get_flux_urls()
    with mock.patch('pipeline.hifa.tasks.importdata.dbfluxes.fluxservice', return_value={'statuscode': '0'}) as mock_fs:
        status, url = dbfluxes.check_service()

    assert status == 'FIRSTURL'
    assert url == flux_url
    assert mock_fs.call_count == 1
    assert mock_fs.call_args[0][0] == flux_url


def test_check_service_backup_success():
    """Test selection of the backup flux service."""
    flux_url, backup_url = dbfluxes.get_flux_urls()
    with mock.patch(
        'pipeline.hifa.tasks.importdata.dbfluxes.fluxservice',
        side_effect=[IOError('Primary down'), {'statuscode': '0'}],
    ) as mock_fs:
        status, url = dbfluxes.check_service()

    assert status == 'BACKUPURL'
    assert url == backup_url
    assert mock_fs.call_count == 2
    assert mock_fs.call_args_list[0][0][0] == flux_url
    assert mock_fs.call_args_list[1][0][0] == backup_url


def test_check_service_both_fail():
    """Test failure when neither flux service is available."""
    with mock.patch(
        'pipeline.hifa.tasks.importdata.dbfluxes.fluxservice',
        side_effect=IOError('Service unreachable'),
    ) as mock_fs:
        status, url = dbfluxes.check_service()

    assert status == 'FAIL'
    assert url is None
    assert mock_fs.call_count == 2


def test_add_catalogue_fluxes_uses_service_url_without_probe():
    """Test use of the supplied service URL without an additional probe."""
    ms = mock.Mock()
    spw = mock.Mock()
    spw.id = 1
    ms.get_spectral_windows.return_value = [spw]
    ms.get_spectral_window.return_value = spw

    source = mock.Mock()
    source.name = 'TestSrc'
    meas = FluxMeasurement(spw_id=1, I=measures.FluxDensity(1.0, measures.FluxDensityUnits.JANSKY))

    measurements = collections.defaultdict(list, {source: [meas]})

    with (
        mock.patch('pipeline.hifa.tasks.importdata.dbfluxes.fluxservice') as mock_fs,
        mock.patch(
            'pipeline.hifa.tasks.importdata.dbfluxes.query_online_catalogue',
            return_value=('url', '1.0', '0', '111', None, meas),
        ) as mock_query,
        mock.patch('pipeline.hifa.tasks.importdata.dbfluxes.log_result'),
    ):
        results, qacodes = dbfluxes.add_catalogue_fluxes(measurements, ms, service_url='https://custom.service.test')

    # fluxservice should NOT have been called for test probing
    mock_fs.assert_not_called()
    # query_online_catalogue should be called with the custom service_url
    mock_query.assert_called_once_with('https://custom.service.test', ms, spw, source, client=mock.ANY)
    assert mock_query.call_args.kwargs['client'].service_url == 'https://custom.service.test'
    assert source in results


def test_fluxservice_retries_incomplete_read() -> None:
    """Retry a truncated response and close both response contexts."""
    truncated = mock.MagicMock()
    truncated.__enter__.return_value = truncated
    truncated.read.side_effect = IncompleteRead(b'partial', 10)
    complete = BytesIO(CATALOGUE_XML)
    with (
        mock.patch.object(dbfluxes.urllib.request, 'urlopen', side_effect=[truncated, complete]) as urlopen,
        mock.patch.object(dbfluxes.time, 'sleep') as sleep,
    ):
        result = dbfluxes.fluxservice(PRIMARY_URL, dbfluxes.TEST_OBS_TIME, '1e11', 'TestSrc')

    assert result['fluxdensity'] == '2.0'
    assert urlopen.call_count == 2
    sleep.assert_called_once_with(0.5)
    truncated.__exit__.assert_called_once()
    assert complete.closed


def test_fluxservice_exhausts_incomplete_read_retries() -> None:
    """Stop retrying a repeatedly truncated body after the configured attempts."""
    response = mock.MagicMock()
    response.__enter__.return_value = response
    response.read.side_effect = IncompleteRead(b'partial', 10)
    with (
        mock.patch.object(dbfluxes.urllib.request, 'urlopen', return_value=response) as urlopen,
        mock.patch.object(dbfluxes.time, 'sleep') as sleep,
        pytest.raises(IncompleteRead),
    ):
        dbfluxes.fluxservice(PRIMARY_URL, dbfluxes.TEST_OBS_TIME, '1e11', 'TestSrc')

    assert urlopen.call_count == 3
    assert sleep.call_args_list == [mock.call(0.5), mock.call(1.0)]
    assert response.__exit__.call_count == 3


@pytest.mark.parametrize('status', [400, 401, 403, 404, 408, 429, 500, 501, 502, 503, 504])
def test_fluxservice_retries_only_transient_http_errors(status: int) -> None:
    """Retry transient HTTP errors while propagating permanent errors immediately."""
    error_body = BytesIO(b'error')
    error = urllib.error.HTTPError(PRIMARY_URL, status, 'error', {}, error_body)
    with (
        mock.patch.object(dbfluxes.urllib.request, 'urlopen', side_effect=[error, BytesIO(CATALOGUE_XML)]) as urlopen,
        mock.patch.object(dbfluxes.time, 'sleep') as sleep,
    ):
        if status in {408, 429, 500, 502, 503, 504}:
            result = dbfluxes.fluxservice(PRIMARY_URL, dbfluxes.TEST_OBS_TIME, '1e11', 'TestSrc')
            assert result['fluxdensity'] == '2.0'
            assert urlopen.call_count == 2
            sleep.assert_called_once_with(0.5)
            assert error_body.closed
        else:
            with pytest.raises(urllib.error.HTTPError):
                dbfluxes.fluxservice(PRIMARY_URL, dbfluxes.TEST_OBS_TIME, '1e11', 'TestSrc')
            assert urlopen.call_count == 1
            sleep.assert_not_called()
    error.close()


@pytest.mark.parametrize('wrapped', [False, True])
def test_fluxservice_does_not_retry_certificate_errors(wrapped: bool) -> None:
    """Certificate verification failures do not recover by retrying unchanged requests."""
    error = ssl.SSLCertVerificationError('certificate verification failed')
    if wrapped:
        error = urllib.error.URLError(error)
    with (
        mock.patch.object(dbfluxes.urllib.request, 'urlopen', side_effect=error) as urlopen,
        mock.patch.object(dbfluxes.time, 'sleep') as sleep,
        pytest.raises(OSError),
    ):
        dbfluxes.fluxservice(PRIMARY_URL, dbfluxes.TEST_OBS_TIME, '1e11', 'TestSrc')

    assert urlopen.call_count == 1
    sleep.assert_not_called()


@pytest.mark.parametrize(
    'response',
    [
        b'<VOTABLE/>',
        b'<html/>',
        CATALOGUE_XML.replace(b'<TD>0</TD>', b'<TD/>'),
        CATALOGUE_XML.replace(b'<TD>0</TD>', b'<TD>invalid</TD>'),
        CATALOGUE_XML.replace(b'<TD>0</TD>', b'<TD>99</TD>'),
        CATALOGUE_XML.replace(b'"StatusCode"', b'"OtherColumn"'),
        CATALOGUE_XML.replace(b'"FluxDensity"', b'"OtherColumn"'),
    ],
)
def test_fluxservice_rejects_unusable_responses(response: bytes) -> None:
    """Reject missing catalogue rows and unusable status or measurement columns."""
    with (
        mock.patch.object(dbfluxes.urllib.request, 'urlopen', return_value=BytesIO(response)),
        pytest.raises(dbfluxes.FluxServiceResponseError),
    ):
        dbfluxes.fluxservice(PRIMARY_URL, dbfluxes.TEST_OBS_TIME, '1e11', 'TestSrc')


@pytest.mark.parametrize('response', [b'<VOTABLE/>', b'not XML'])
def test_check_service_rejects_unusable_primary_response(response: bytes) -> None:
    """Select the backup when a probe returns unusable XML or catalogue structure."""
    with mock.patch.object(
        dbfluxes.urllib.request, 'urlopen', side_effect=[BytesIO(response), BytesIO(CATALOGUE_XML)]
    ) as urlopen:
        assert dbfluxes.check_service() == ('BACKUPURL', BACKUP_URL)

    assert urlopen.call_count == 2


@pytest.mark.parametrize('missing_source_xml', [False, True])
def test_setjy_reuses_backup_across_measurement_sets(flux_data: FluxData, missing_source_xml: bool) -> None:
    """Fail over an actual query and reuse the backup across both flux-loading paths."""
    ms, source, measurements = flux_data
    second_ms = copy.copy(ms)
    second_ms.name = 'test_second.ms'
    client = dbfluxes.FluxServiceClient(PRIMARY_URL)
    with (
        mock.patch.object(dbfluxes.fluxes, 'read_fluxes_nodb', return_value={} if missing_source_xml else measurements),
        mock.patch.object(dbfluxes.utils, 'get_epoch_as_datetime', return_value=dbfluxes.TEST_OBS_TIME),
        mock.patch.object(
            dbfluxes.urllib.request,
            'urlopen',
            side_effect=[OSError('primary unavailable')] * 3 + [BytesIO(CATALOGUE_XML), BytesIO(CATALOGUE_XML)],
        ) as urlopen,
        mock.patch.object(dbfluxes.time, 'sleep'),
        mock.patch.object(dbfluxes, 'check_service') as probe,
    ):
        results, qastatus = dbfluxes.get_setjy_results([ms, second_ms], client=client)

    assert [call.args[0].full_url.split('?')[0] for call in urlopen.call_args_list] == [PRIMARY_URL] * 3 + [
        BACKUP_URL
    ] * 2
    assert client.service_url == BACKUP_URL
    assert client.status == 'BACKUPURL'
    assert len(results) == 2
    for result in results:
        assert result.measurements[0][0].I.to_units(measures.FluxDensityUnits.JANSKY) == 2.0
    assert qastatus == []
    probe.assert_not_called()


def test_invalid_actual_responses_preserve_local_flux(flux_data: FluxData) -> None:
    """Keep Source.xml measurements when both endpoints return unusable structures."""
    ms, source, measurements = flux_data
    with (
        mock.patch.object(dbfluxes.utils, 'get_epoch_as_datetime', return_value=dbfluxes.TEST_OBS_TIME),
        mock.patch.object(
            dbfluxes.urllib.request, 'urlopen', side_effect=lambda *args, **kwargs: BytesIO(b'<VOTABLE/>')
        ) as urlopen,
    ):
        results, qacodes = dbfluxes.add_catalogue_fluxes(measurements, ms)

    assert results[source][0] is measurements[source][0]
    assert qacodes == []
    assert urlopen.call_count == 2


def test_no_catalogue_measurement_does_not_trigger_failover(flux_data: FluxData) -> None:
    """A legitimate no-measurement status uses local flux without switching endpoints."""
    ms, source, measurements = flux_data
    response = b'<VOTABLE><FIELD name="StatusCode"/><TR><TD>4</TD></TR></VOTABLE>'
    client = dbfluxes.FluxServiceClient(PRIMARY_URL)
    with (
        mock.patch.object(dbfluxes.utils, 'get_epoch_as_datetime', return_value=dbfluxes.TEST_OBS_TIME),
        mock.patch.object(dbfluxes.urllib.request, 'urlopen', return_value=BytesIO(response)) as urlopen,
    ):
        results, qacodes = dbfluxes.add_catalogue_fluxes(measurements, ms, client=client)

    assert results[source][0] is measurements[source][0]
    assert qacodes == [{'source': source, 'status_code': '4', 'clarification': None}]
    assert client.service_url == PRIMARY_URL
    urlopen.assert_called_once()


@pytest.mark.parametrize('service_url', [BACKUP_URL, 'https://custom.test/sc/flux'])
def test_client_does_not_redirect_backup_or_custom_endpoints(service_url: str) -> None:
    """An explicitly selected backup or custom endpoint does not retry the primary."""
    client = dbfluxes.FluxServiceClient(service_url)
    with mock.patch.object(dbfluxes, 'fluxservice', side_effect=OSError('unavailable')) as query:
        with pytest.raises(OSError):
            client.query(dbfluxes.TEST_OBS_TIME, '1e11', 'TestSrc')
    query.assert_called_once_with(service_url, dbfluxes.TEST_OBS_TIME, '1e11', 'TestSrc')


def test_client_retains_primary_when_backup_also_fails() -> None:
    """Only retain a backup endpoint after it returns a usable response."""
    client = dbfluxes.FluxServiceClient(PRIMARY_URL)
    with mock.patch.object(
        dbfluxes, 'fluxservice', side_effect=[OSError('primary down'), OSError('backup down'), {'statuscode': '0'}]
    ) as query:
        with pytest.raises(OSError, match='backup down'):
            client.query(dbfluxes.TEST_OBS_TIME, '1e11', 'TestSrc')
        assert client.query(dbfluxes.TEST_OBS_TIME, '1e11', 'TestSrc') == {'statuscode': '0'}

    assert [call.args[0] for call in query.call_args_list] == [PRIMARY_URL, BACKUP_URL, PRIMARY_URL]
    assert client.status == 'FIRSTURL'


def test_client_does_not_repeat_identical_endpoints() -> None:
    """A duplicate backup URL does not cause a second sequence of failed requests."""
    with mock.patch.object(dbfluxes, 'get_flux_urls', return_value=(PRIMARY_URL, PRIMARY_URL)):
        client = dbfluxes.FluxServiceClient()
    with mock.patch.object(dbfluxes, 'fluxservice', side_effect=OSError('unavailable')) as query:
        with pytest.raises(OSError):
            client.query(dbfluxes.TEST_OBS_TIME, '1e11', 'TestSrc')
    query.assert_called_once()


@pytest.mark.parametrize('retries, delay', [(-1, 0.5), (2, -0.5)])
def test_fluxservice_rejects_negative_retry_options(retries: int, delay: float) -> None:
    """Reject invalid retry options before issuing a request."""
    with mock.patch.object(dbfluxes.urllib.request, 'urlopen') as urlopen:
        with pytest.raises(ValueError, match='nonnegative'):
            dbfluxes.fluxservice(PRIMARY_URL, dbfluxes.TEST_OBS_TIME, '1e11', 'TestSrc', retries, delay)
    urlopen.assert_not_called()


def test_log_result_data_conditions():
    """Log both current and legacy catalogue data-condition codes."""
    source = mock.MagicMock(name='source')
    source.name = 'J1427-4206'
    spw = mock.MagicMock(name='spw')
    spw.id = 16

    with mock.patch.object(dbfluxes.LOG, 'info') as mock_info:
        # Test 4-digit code (post-OFFLINE-2026AUG)
        dbfluxes.log_result(
            source, spw, '1.2', '1.2', '-0.7', '12.5', 'https://example.test', '2026AUG', '0', '9001', None
        )
        logged_messages = [
            call.args[0] % call.args[1:] if len(call.args) > 1 else call.args[0] for call in mock_info.call_args_list
        ]
        assert any('Number of measurements = >= 9' in msg for msg in logged_messages)
        assert any('Measurements in >= 2 distinct bands? No' in msg for msg in logged_messages)
        assert any('Observation date bracketed in time? No' in msg for msg in logged_messages)
        assert any('Spectral index cross-band bracketed in time? Yes' in msg for msg in logged_messages)

    with mock.patch.object(dbfluxes.LOG, 'info') as mock_info:
        # Test 3-digit legacy code
        dbfluxes.log_result(
            source, spw, '1.2', '1.2', '-0.7', '12.5', 'https://example.test', '2026AUG', '0', '311', None
        )
        logged_messages = [
            call.args[0] % call.args[1:] if len(call.args) > 1 else call.args[0] for call in mock_info.call_args_list
        ]
        assert any('Number of measurements = 3' in msg for msg in logged_messages)
        assert any('Measurements in >= 2 distinct bands? Yes' in msg for msg in logged_messages)
        assert any('Observation date bracketed in time? Yes' in msg for msg in logged_messages)
        assert any('Spectral index cross-band bracketed in time? N/A' in msg for msg in logged_messages)

    with mock.patch.object(dbfluxes.LOG, 'info') as mock_info:
        # Test empty/None code
        dbfluxes.log_result(
            source, spw, '1.2', '1.2', '-0.7', '12.5', 'https://example.test', '2026AUG', '0', None, None
        )
        logged_messages = [
            call.args[0] % call.args[1:] if len(call.args) > 1 else call.args[0] for call in mock_info.call_args_list
        ]
        assert any('Number of measurements = N/A' in msg for msg in logged_messages)
        assert any('Spectral index cross-band bracketed in time? N/A' in msg for msg in logged_messages)
