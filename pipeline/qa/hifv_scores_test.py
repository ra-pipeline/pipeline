"""Unit tests for pipeline.qa.hifv_scores."""

from __future__ import annotations

from unittest import mock

from pipeline.qa import hifv_scores

SYNTHETIC_FLAG_ZERO_ENDTIME_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<FlagTable xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" schemaVersion="3">
  <Entity entityId="uid://X0/X0/X5" entityTypeName="FlagTable" schemaVersion="3" documentVersion="1"/>
  <ContainerEntity entityId="uid://X0/X0/X1" entityTypeName="ASDM" schemaVersion="3" documentVersion="1"/>
  <row>
    <flagId>Flag_1</flagId>
    <startTime>7090683272335387903</startTime>
    <endTime>0</endTime>
    <reason>ANTENNA_NOT_ON_SOURCE</reason>
    <numAntenna>1</numAntenna>
    <antennaId>1 1 Antenna_0</antennaId>
  </row>
</FlagTable>
"""

SYNTHETIC_FLAG_VALID_ENDTIME_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<FlagTable xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" schemaVersion="3">
  <Entity entityId="uid://X0/X0/X5" entityTypeName="FlagTable" schemaVersion="3" documentVersion="1"/>
  <ContainerEntity entityId="uid://X0/X0/X1" entityTypeName="ASDM" schemaVersion="3" documentVersion="1"/>
  <row>
    <flagId>Flag_1</flagId>
    <startTime>7090683272335387903</startTime>
    <endTime>7090683272435387903</endTime>
    <reason>ANTENNA_NOT_ON_SOURCE</reason>
    <numAntenna>1</numAntenna>
    <antennaId>1 1 Antenna_0</antennaId>
  </row>
</FlagTable>
"""

SYNTHETIC_PARTIAL_FLAG_ZERO_XML = """\
<FlagTable>
  <row>
    <endTime>0</endTime>
  </row>
</FlagTable>
"""

SYNTHETIC_PARTIAL_FLAG_VALID_XML = """\
<FlagTable>
  <row>
    <endTime>7090683272435387903</endTime>
  </row>
</FlagTable>
"""


def _create_mock_ms(ms_path: str):
    ms = mock.MagicMock()
    ms.name = ms_path
    ms.basename = 'mock_ms'
    ms.origin_ms = None
    ms.get_spectral_windows.return_value = []
    return ms


def test_score_vla_agents_zero_endtime_via_pyasdm(tmp_path):
    """Test score_vla_agents flags zero endTime online flags as 0.3 QA score."""
    (tmp_path / 'Flag.xml').write_text(SYNTHETIC_FLAG_ZERO_ENDTIME_XML)
    ms = _create_mock_ms(str(tmp_path))
    summaries = [{'name': 'online', 'flagged': 50, 'total': 1000}]

    scores = hifv_scores.score_vla_agents(ms, summaries)
    online_flag_scores = [s for s in scores if s.longmsg == 'In flag.xml for online flags, end time is 0']
    assert len(online_flag_scores) == 1
    assert online_flag_scores[0].score == 0.3


def test_score_vla_agents_valid_endtime_via_pyasdm(tmp_path):
    """Test score_vla_agents does not penalize valid non-zero endTime online flags."""
    (tmp_path / 'Flag.xml').write_text(SYNTHETIC_FLAG_VALID_ENDTIME_XML)
    ms = _create_mock_ms(str(tmp_path))
    summaries = [{'name': 'online', 'flagged': 50, 'total': 1000}]

    scores = hifv_scores.score_vla_agents(ms, summaries)
    online_flag_scores = [s for s in scores if s.longmsg == 'In flag.xml for online flags, end time is 0']
    assert len(online_flag_scores) == 0


def test_score_vla_agents_origin_ms_fallback(tmp_path):
    """Test score_vla_agents detects zero endTime in origin_ms when missing in child MS."""
    origin_dir = tmp_path / 'origin.ms'
    origin_dir.mkdir()
    (origin_dir / 'Flag.xml').write_text(SYNTHETIC_FLAG_ZERO_ENDTIME_XML)

    child_dir = tmp_path / 'child.ms'
    child_dir.mkdir()

    ms = _create_mock_ms(str(child_dir))
    ms.origin_ms = str(origin_dir)
    summaries = [{'name': 'online', 'flagged': 50, 'total': 1000}]

    scores = hifv_scores.score_vla_agents(ms, summaries)
    online_flag_scores = [s for s in scores if s.longmsg == 'In flag.xml for online flags, end time is 0']
    assert len(online_flag_scores) == 1


def test_score_vla_agents_elementtree_fallback(tmp_path):
    """Test score_vla_agents fallback to ElementTree on partial XML without pyasdm schema headers."""
    (tmp_path / 'Flag.xml').write_text(SYNTHETIC_PARTIAL_FLAG_ZERO_XML)
    ms = _create_mock_ms(str(tmp_path))
    summaries = [{'name': 'online', 'flagged': 50, 'total': 1000}]

    scores = hifv_scores.score_vla_agents(ms, summaries)
    online_flag_scores = [s for s in scores if s.longmsg == 'In flag.xml for online flags, end time is 0']
    assert len(online_flag_scores) == 1

    (tmp_path / 'Flag.xml').write_text(SYNTHETIC_PARTIAL_FLAG_VALID_XML)
    scores2 = hifv_scores.score_vla_agents(ms, summaries)
    online_flag_scores2 = [s for s in scores2 if s.longmsg == 'In flag.xml for online flags, end time is 0']
    assert len(online_flag_scores2) == 0
