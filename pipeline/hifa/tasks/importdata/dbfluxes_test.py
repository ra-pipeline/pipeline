import datetime
from io import BytesIO
from unittest import mock

from pipeline.hifa.tasks.importdata import dbfluxes


def test_fluxservice_reads_source_catalogue_columns_by_field_name():
    xml_response = b'''<?xml version="1.0"?>
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
'''
    obs_time = datetime.datetime(2013, 3, 27, 7, 53, 3, 168000, tzinfo=datetime.timezone.utc)

    with mock.patch('pipeline.hifa.tasks.importdata.dbfluxes.urllib.request.urlopen', return_value=BytesIO(xml_response)):
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
