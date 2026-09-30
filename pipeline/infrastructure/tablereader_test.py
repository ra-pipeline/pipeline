"""Unit tests for pipeline.infrastructure.tablereader."""

from __future__ import annotations

from unittest import mock

from pipeline.infrastructure.tablereader import SpectralWindowTable

SYNTHETIC_SPECTRAL_WINDOW_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<SpectralWindowTable xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" schemaVersion="3">
  <Entity entityId="uid://X0/X0/X0" entityTypeName="SpectralWindowTable" schemaVersion="3" documentVersion="1"/>
  <ContainerEntity entityId="uid://X0/X0/X1" entityTypeName="ASDM" schemaVersion="3" documentVersion="1"/>
  <row>
    <spectralWindowId>SpectralWindow_0</spectralWindowId>
    <basebandName>NOBB</basebandName>
    <netSideband>NOSB</netSideband>
    <numChan>128</numChan>
    <refFreq>100000000000.0</refFreq>
    <sidebandProcessingMode>NONE</sidebandProcessingMode>
    <totBandwidth>2000000000.0</totBandwidth>
    <windowFunction>UNIFORM</windowFunction>
  </row>
  <row>
    <spectralWindowId>SpectralWindow_1</spectralWindowId>
    <basebandName>NOBB</basebandName>
    <netSideband>NOSB</netSideband>
    <numChan>128</numChan>
    <refFreq>110000000000.0</refFreq>
    <sidebandProcessingMode>NONE</sidebandProcessingMode>
    <totBandwidth>2000000000.0</totBandwidth>
    <windowFunction>UNIFORM</windowFunction>
  </row>
  <row>
    <spectralWindowId>SpectralWindow_2</spectralWindowId>
    <basebandName>NOBB</basebandName>
    <netSideband>NOSB</netSideband>
    <numChan>64</numChan>
    <refFreq>120000000000.0</refFreq>
    <sidebandProcessingMode>NONE</sidebandProcessingMode>
    <totBandwidth>1000000000.0</totBandwidth>
    <windowFunction>UNIFORM</windowFunction>
  </row>
</SpectralWindowTable>
"""

SYNTHETIC_DATA_DESCRIPTION_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<DataDescriptionTable xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" schemaVersion="3">
  <Entity entityId="uid://X0/X0/X2" entityTypeName="DataDescriptionTable" schemaVersion="3" documentVersion="1"/>
  <ContainerEntity entityId="uid://X0/X0/X1" entityTypeName="ASDM" schemaVersion="3" documentVersion="1"/>
  <row>
    <dataDescriptionId>DataDescription_0</dataDescriptionId>
    <polOrHoloId>Polarization_0</polOrHoloId>
    <spectralWindowId>SpectralWindow_1</spectralWindowId>
  </row>
  <row>
    <dataDescriptionId>DataDescription_1</dataDescriptionId>
    <polOrHoloId>Polarization_0</polOrHoloId>
    <spectralWindowId>SpectralWindow_2</spectralWindowId>
  </row>
</DataDescriptionTable>
"""

PARTIAL_XML_ROW_ONLY = """\
<SpectralWindowTable>
  <row>
    <spectralWindowId>SpectralWindow_99</spectralWindowId>
  </row>
</SpectralWindowTable>
"""


def test_parse_spectral_window_ids_via_pyasdm(tmp_path):
    """Test extracting spectral window IDs using pyasdm on valid synthetic ASDM XML."""
    spw_xml = tmp_path / 'SpectralWindow.xml'
    spw_xml.write_text(SYNTHETIC_SPECTRAL_WINDOW_XML)

    dd_xml = tmp_path / 'DataDescription.xml'
    dd_xml.write_text(SYNTHETIC_DATA_DESCRIPTION_XML)

    spw_ids = SpectralWindowTable.parse_spectral_window_ids_from_xml(str(spw_xml))
    assert spw_ids == [0, 1, 2]

    dd_ids = SpectralWindowTable.parse_spectral_window_ids_from_xml(str(dd_xml))
    assert dd_ids == [1, 2]


def test_parse_spectral_window_ids_fallback(tmp_path):
    """Test fallback to ElementTree when pyasdm schema conversion is incomplete."""
    fragment_xml = tmp_path / 'SpectralWindow.xml'
    fragment_xml.write_text(PARTIAL_XML_ROW_ONLY)

    ids = SpectralWindowTable.parse_spectral_window_ids_from_xml(str(fragment_xml))
    assert ids == [99]


def test_get_asdm_to_ms_spw_mapping_computation_and_cache(tmp_path):
    """Test computation and in-memory caching of ASDM-to-MS SpW mapping."""
    spw_xml = tmp_path / 'SpectralWindow.xml'
    spw_xml.write_text(SYNTHETIC_SPECTRAL_WINDOW_XML)

    dd_xml = tmp_path / 'DataDescription.xml'
    dd_xml.write_text(SYNTHETIC_DATA_DESCRIPTION_XML)

    ms = mock.MagicMock()
    ms.name = str(tmp_path)
    ms.asdm_spw_mapping = None

    # SpectralWindow has [0, 1, 2], DataDescription has [1, 2].
    # In-dd spws come first [1, 2], non-dd spws come after [0].
    # ASDM order: [1, 2, 0] mapped to MS spws: [0, 1, 2].
    # Resulting dict: {1: 0, 2: 1, 0: 2}
    mapping = SpectralWindowTable.get_asdm_to_ms_spw_mapping(ms)
    assert mapping == {1: 0, 2: 1, 0: 2}
    assert ms.asdm_spw_mapping == mapping

    # Subsequent call returns cached mapping directly without recomputing
    cached_mapping = SpectralWindowTable.get_asdm_to_ms_spw_mapping(ms)
    assert cached_mapping is mapping


def test_origin_ms_fallback_for_spw_ids(tmp_path):
    """Test fallback to origin_ms when XML files are missing in derived MS directory."""
    origin_dir = tmp_path / 'origin.ms'
    origin_dir.mkdir()
    (origin_dir / 'SpectralWindow.xml').write_text(SYNTHETIC_SPECTRAL_WINDOW_XML)
    (origin_dir / 'DataDescription.xml').write_text(SYNTHETIC_DATA_DESCRIPTION_XML)

    split_dir = tmp_path / 'split.ms'
    split_dir.mkdir()

    ms = mock.MagicMock()
    ms.name = str(split_dir)
    ms.origin_ms = str(origin_dir)
    ms.asdm_spw_mapping = None

    mapping = SpectralWindowTable.get_asdm_to_ms_spw_mapping(ms)
    assert mapping == {1: 0, 2: 1, 0: 2}
