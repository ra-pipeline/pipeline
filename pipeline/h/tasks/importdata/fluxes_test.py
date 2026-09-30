"""Unit tests for pipeline.h.tasks.importdata.fluxes."""

from __future__ import annotations

from unittest import mock

from pipeline.domain import measures
from pipeline.h.tasks.importdata import fluxes

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
    <spectralWindowId>SpectralWindow_0</spectralWindowId>
  </row>
</DataDescriptionTable>
"""

SYNTHETIC_SOURCE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<SourceTable xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" schemaVersion="3">
  <Entity entityId="uid://X0/X0/X3" entityTypeName="SourceTable" schemaVersion="3" documentVersion="1"/>
  <ContainerEntity entityId="uid://X0/X0/X1" entityTypeName="ASDM" schemaVersion="3" documentVersion="1"/>
  <row>
    <sourceId>0</sourceId>
    <timeInterval>7090683272335387903 4265377529038775807</timeInterval>
    <code>none</code>
    <direction>1 2 1.3528024488371877 0.31436086058385826</direction>
    <properMotion>1 2 0.0 0.0</properMotion>
    <sourceName>CAL_FLUX_TEST</sourceName>
    <directionCode>ICRS</directionCode>
    <numFreq>2</numFreq>
    <numStokes>4</numStokes>
    <frequency>1 2 9.99e10 1.001e11</frequency>
    <stokesParameter>1 4 I Q U V</stokesParameter>
    <flux>2 2 4 4.5 0.0 0.0 0.0 4.6 0.0 0.0 0.0</flux>
    <spectralWindowId>SpectralWindow_0</spectralWindowId>
  </row>
</SourceTable>
"""


def _create_mock_ms(ms_path: str):
    ms = mock.MagicMock()
    ms.name = ms_path
    ms.basename = 'mock_ms'
    ms.origin_ms = None
    ms.asdm_spw_mapping = None

    spw0 = mock.MagicMock()
    spw0.id = 0
    spw0.centre_frequency = measures.Frequency(100.0, measures.FrequencyUnits.GIGAHERTZ)
    spw0.min_frequency = measures.Frequency(99.0, measures.FrequencyUnits.GIGAHERTZ)
    spw0.max_frequency = measures.Frequency(101.0, measures.FrequencyUnits.GIGAHERTZ)

    ms.spectral_windows = [spw0]
    ms.get_spectral_window = lambda idx: spw0
    ms.sources = {0: 'CAL_FLUX_TEST'}
    return ms


def test_read_fluxes_via_pyasdm(tmp_path):
    """Test reading source fluxes using pyasdm on synthetic ASDM tables."""
    (tmp_path / 'SpectralWindow.xml').write_text(SYNTHETIC_SPECTRAL_WINDOW_XML)
    (tmp_path / 'DataDescription.xml').write_text(SYNTHETIC_DATA_DESCRIPTION_XML)
    (tmp_path / 'Source.xml').write_text(SYNTHETIC_SOURCE_XML)

    ms = _create_mock_ms(str(tmp_path))

    results = fluxes.read_fluxes_nodb(ms)
    assert 'CAL_FLUX_TEST' in results
    measurements = results['CAL_FLUX_TEST']
    assert len(measurements) == 1

    m = measurements[0]
    assert m.spw_id == 0
    assert m.origin == fluxes.ORIGIN_XML
    # Average of equally distant frequencies (99.9 GHz and 100.1 GHz from 100 GHz center): (4.5 + 4.6)/2 = 4.55
    assert abs(float(m.I.to_units(measures.FluxDensityUnits.JANSKY)) - 4.55) < 1e-6
    assert float(m.Q.to_units(measures.FluxDensityUnits.JANSKY)) == 0.0


def test_read_fluxes_missing_source_xml(tmp_path):
    """Test read_fluxes_nodb returns empty dict when Source table is missing."""
    ms = _create_mock_ms(str(tmp_path))
    results = fluxes.read_fluxes_nodb(ms)
    assert len(results) == 0


def test_read_fluxes_origin_ms_fallback(tmp_path):
    """Test read_fluxes_nodb falls back to origin_ms when Source table is missing in child MS."""
    origin_dir = tmp_path / 'origin.ms'
    origin_dir.mkdir()
    (origin_dir / 'SpectralWindow.xml').write_text(SYNTHETIC_SPECTRAL_WINDOW_XML)
    (origin_dir / 'DataDescription.xml').write_text(SYNTHETIC_DATA_DESCRIPTION_XML)
    (origin_dir / 'Source.xml').write_text(SYNTHETIC_SOURCE_XML)

    child_dir = tmp_path / 'child.ms'
    child_dir.mkdir()

    ms = _create_mock_ms(str(child_dir))
    ms.origin_ms = str(origin_dir)

    results = fluxes.read_fluxes_nodb(ms)
    assert 'CAL_FLUX_TEST' in results
    assert len(results['CAL_FLUX_TEST']) == 1
