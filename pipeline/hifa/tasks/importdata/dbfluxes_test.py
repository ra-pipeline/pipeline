import datetime
from io import BytesIO
from unittest import mock

from pipeline.hifa.tasks.importdata import dbfluxes


def test_fluxservice_reads_source_catalogue_columns_by_field_name():
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
            <TD>111</TD>
            <TD>12.5</TD>
            <TD>extra source catalogue details</TD>
            <TD>2026JUN</TD>
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
    assert fluxdict['dataconditions'] == '111'
    assert fluxdict['ageOfNearestMonitorPoint'] == '12.5'
    assert fluxdict['version'] == '2026JUN'
    assert fluxdict['clarification'] is None


def test_fluxservice_user_agent_and_retries():
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

    import urllib.error

    with mock.patch(
        'pipeline.hifa.tasks.importdata.dbfluxes.urllib.request.urlopen',
        side_effect=[urllib.error.URLError('timeout'), BytesIO(xml_response)],
    ) as mock_urlopen:
        fluxdict = dbfluxes.fluxservice(
            'https://example.test/sc/flux',
            obs_time,
            '86837309056.169219970703125',
            'J1427-4206',
            retries=1,
            retry_delay=0.01,
        )

    assert mock_urlopen.call_count == 2
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
    obs_time = datetime.datetime(2013, 3, 27, 7, 53, 3, 168000, tzinfo=datetime.timezone.utc)
    import pytest
    import urllib.error

    with mock.patch(
        'pipeline.hifa.tasks.importdata.dbfluxes.urllib.request.urlopen',
        side_effect=urllib.error.URLError('connection refused'),
    ) as mock_urlopen:
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


def test_check_service_primary_success():
    flux_url, _ = dbfluxes.get_flux_urls()
    with mock.patch('pipeline.hifa.tasks.importdata.dbfluxes.fluxservice', return_value={'statuscode': '0'}) as mock_fs:
        status, url = dbfluxes.check_service()

    assert status == 'FIRSTURL'
    assert url == flux_url
    assert mock_fs.call_count == 1
    assert mock_fs.call_args[0][0] == flux_url


def test_check_service_backup_success():
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
    with mock.patch(
        'pipeline.hifa.tasks.importdata.dbfluxes.fluxservice',
        side_effect=IOError('Service unreachable'),
    ) as mock_fs:
        status, url = dbfluxes.check_service()

    assert status == 'FAIL'
    assert url is None
    assert mock_fs.call_count == 2


def test_add_catalogue_fluxes_uses_service_url_without_probe():
    import collections
    from pipeline.domain import FluxMeasurement
    from pipeline.domain import measures

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
    mock_query.assert_called_once_with('https://custom.service.test', ms, spw, source)
    assert source in results
