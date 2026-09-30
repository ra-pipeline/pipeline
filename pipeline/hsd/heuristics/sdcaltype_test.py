"""Unit tests for pipeline.hsd.heuristics.sdcaltype."""

from __future__ import annotations

from pipeline.hsd.heuristics.sdcaltype import AsdmCalibrationTypeHeuristics

SYNTHETIC_SCAN_TARGET_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<ScanTable xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" schemaVersion="3">
  <Entity entityId="uid://X0/X0/X4" entityTypeName="ScanTable" schemaVersion="3" documentVersion="1"/>
  <ContainerEntity entityId="uid://X0/X0/X1" entityTypeName="ASDM" schemaVersion="3" documentVersion="1"/>
  <row>
    <execBlockId>ExecBlock_0</execBlockId>
    <scanNumber>1</scanNumber>
    <startTime>7090683272335387903</startTime>
    <endTime>7090683272435387903</endTime>
    <numIntent>1</numIntent>
    <numSubscan>1</numSubscan>
    <scanIntent>1 1 OBSERVE_TARGET</scanIntent>
    <calDataType>1 1 NONE</calDataType>
    <calibrationSet>1 1 NONE</calibrationSet>
    <calibrationFunction>1 1 UNSPECIFIED</calibrationFunction>
    <calibrationOnLine>1 1 false</calibrationOnLine>
    <antennaId>1 1 Antenna_0</antennaId>
    <fieldName>1 1 Field_0</fieldName>
    <sourceName>1 1 Source_0</sourceName>
  </row>
</ScanTable>
"""

SYNTHETIC_SCAN_CAL_ONLY_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<ScanTable xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" schemaVersion="3">
  <Entity entityId="uid://X0/X0/X4" entityTypeName="ScanTable" schemaVersion="3" documentVersion="1"/>
  <ContainerEntity entityId="uid://X0/X0/X1" entityTypeName="ASDM" schemaVersion="3" documentVersion="1"/>
  <row>
    <execBlockId>ExecBlock_0</execBlockId>
    <scanNumber>1</scanNumber>
    <startTime>7090683272335387903</startTime>
    <endTime>7090683272435387903</endTime>
    <numIntent>1</numIntent>
    <numSubscan>1</numSubscan>
    <scanIntent>1 1 CALIBRATE_ATMOSPHERE</scanIntent>
    <calDataType>1 1 NONE</calDataType>
    <calibrationSet>1 1 NONE</calibrationSet>
    <calibrationFunction>1 1 UNSPECIFIED</calibrationFunction>
    <calibrationOnLine>1 1 false</calibrationOnLine>
    <antennaId>1 1 Antenna_0</antennaId>
    <fieldName>1 1 Field_0</fieldName>
    <sourceName>1 1 Source_0</sourceName>
  </row>
</ScanTable>
"""

SYNTHETIC_PARTIAL_XML_TARGET = """\
<ScanTable>
  <row>
    <scanIntent>1 1 OBSERVE_TARGET</scanIntent>
  </row>
</ScanTable>
"""

SYNTHETIC_PARTIAL_XML_NOT_TARGET = """\
<ScanTable>
  <row>
    <scanIntent>1 1 CALIBRATE_ATMOSPHERE</scanIntent>
  </row>
</ScanTable>
"""


def test_asdm_caltype_target_via_pyasdm(tmp_path):
    """Test AsdmCalibrationTypeHeuristics returns 'ps' for ASDM with OBSERVE_TARGET scan."""
    (tmp_path / 'Scan.xml').write_text(SYNTHETIC_SCAN_TARGET_XML)
    h = AsdmCalibrationTypeHeuristics()
    assert h.calculate(str(tmp_path)) == 'ps'


def test_asdm_caltype_non_target_via_pyasdm(tmp_path):
    """Test AsdmCalibrationTypeHeuristics returns 'none' when no OBSERVE_TARGET scan is present."""
    (tmp_path / 'Scan.xml').write_text(SYNTHETIC_SCAN_CAL_ONLY_XML)
    h = AsdmCalibrationTypeHeuristics()
    assert h.calculate(str(tmp_path)) == 'none'


def test_asdm_caltype_missing_scan_table(tmp_path):
    """Test AsdmCalibrationTypeHeuristics returns 'none' when Scan table is missing."""
    h = AsdmCalibrationTypeHeuristics()
    assert h.calculate(str(tmp_path)) == 'none'


def test_asdm_caltype_fallback_to_elementtree(tmp_path):
    """Test AsdmCalibrationTypeHeuristics fallback to ElementTree on partial XML without pyasdm schema headers."""
    (tmp_path / 'Scan.xml').write_text(SYNTHETIC_PARTIAL_XML_TARGET)
    h = AsdmCalibrationTypeHeuristics()
    assert h.calculate(str(tmp_path)) == 'ps'

    (tmp_path / 'Scan.xml').write_text(SYNTHETIC_PARTIAL_XML_NOT_TARGET)
    assert h.calculate(str(tmp_path)) == 'none'
