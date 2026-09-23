"""Unit tests for VLASetjy QA handlers."""

from __future__ import annotations

import unittest.mock as mock

import pipeline.infrastructure.pipelineqa as pqa
from pipeline.hifv.tasks.setmodel.qa import VLASetjyQAHandler


class MockDomainField:
    """Mock domain Field object for QA unit testing."""

    def __init__(self, field_id: int, name: str, intents: list[str] | set[str]) -> None:
        """Initialize a MockDomainField."""
        self.id = field_id
        self.name = name
        self.intents = set(intents)


def create_mock_context_and_result(vis: str = 'test.ms') -> tuple[mock.MagicMock, mock.MagicMock]:
    """Create mock Pipeline context and task result objects.

    Args:
        vis: Path or name of the MeasurementSet.

    Returns:
        A tuple of (mock_context, mock_result).
    """
    context = mock.MagicMock()
    result = mock.MagicMock()
    result.inputs = {'vis': vis}
    result.qa = pqa.QAScorePool()
    return context, result


def test_no_standard_sources_in_ms() -> None:
    """Test when no standard calibrator positions are observed in the MS."""
    context, result = create_mock_context_and_result()
    names = ['3C48', '3C138', '3C147', '3C286']
    fields: list[list[int]] = [[], [], [], []]

    with mock.patch('pipeline.hifv.tasks.setmodel.vlasetjy.standard_sources', return_value=(names, fields)):
        handler = VLASetjyQAHandler()
        handler.handle(context, result)

    assert len(result.qa.pool) == 1
    assert result.qa.pool[0].score == 0.0
    assert result.qa.pool[0].longmsg == 'No VLA standard calibrator present'


def test_standard_sources_present_without_amplitude_intent() -> None:
    """Test when standard calibrators are present, but none have AMPLITUDE intent."""
    context, result = create_mock_context_and_result()
    names = ['3C48', '3C138', '3C147', '3C286']
    fields = [[], [1], [], []]

    mock_ms = mock.MagicMock()
    mock_field1 = MockDomainField(1, '3C138', ['POLARIZATION', 'PHASE'])
    mock_ms.get_fields.side_effect = lambda fid: [mock_field1] if fid == 1 else []
    context.observing_run.get_ms.return_value = mock_ms

    with mock.patch('pipeline.hifv.tasks.setmodel.vlasetjy.standard_sources', return_value=(names, fields)):
        handler = VLASetjyQAHandler()
        handler.handle(context, result)

    assert len(result.qa.pool) == 1
    assert result.qa.pool[0].score == 0.0
    assert result.qa.pool[0].longmsg == 'No flux calibration intent found'


def test_single_standard_calibrator_unflagged() -> None:
    """Test standard calibrator with AMPLITUDE intent and clean (<0.995 flagged) data."""
    context, result = create_mock_context_and_result()
    names = ['3C48', '3C138', '3C147', '3C286']
    fields = [[0], [], [], []]

    mock_ms = mock.MagicMock()
    mock_field0 = MockDomainField(0, '3C48', ['AMPLITUDE'])
    mock_ms.get_fields.side_effect = lambda fid: [mock_field0] if fid == 0 else []
    context.observing_run.get_ms.return_value = mock_ms

    flagdata_result = {'field': {'3C48': {'flagged': 100, 'total': 10000}}}
    mock_flagdata_task = mock.MagicMock()
    mock_flagdata_task.execute.return_value = flagdata_result

    with (
        mock.patch('pipeline.hifv.tasks.setmodel.vlasetjy.standard_sources', return_value=(names, fields)),
        mock.patch('pipeline.infrastructure.casa_tasks.flagdata', return_value=mock_flagdata_task) as mock_flagdata,
    ):
        handler = VLASetjyQAHandler()
        handler.handle(context, result)
        mock_flagdata.assert_called_once_with(vis='test.ms', mode='summary', field='0', intent='*CALIBRATE*')

    assert len(result.qa.pool) == 1
    assert result.qa.pool[0].score == 1.0
    assert result.qa.pool[0].longmsg == 'Standard calibrator 3C48 present.'


def test_single_standard_calibrator_fully_flagged() -> None:
    """Test standard calibrator with AMPLITUDE intent but fully flagged (>=0.995)."""
    context, result = create_mock_context_and_result()
    names = ['3C48', '3C138', '3C147', '3C286']
    fields = [[0], [], [], []]

    mock_ms = mock.MagicMock()
    mock_field0 = MockDomainField(0, '3C48', ['AMPLITUDE'])
    mock_ms.get_fields.side_effect = lambda fid: [mock_field0] if fid == 0 else []
    context.observing_run.get_ms.return_value = mock_ms

    flagdata_result = {'field': {'3C48': {'flagged': 996, 'total': 1000}}}
    mock_flagdata_task = mock.MagicMock()
    mock_flagdata_task.execute.return_value = flagdata_result

    with (
        mock.patch('pipeline.hifv.tasks.setmodel.vlasetjy.standard_sources', return_value=(names, fields)),
        mock.patch('pipeline.infrastructure.casa_tasks.flagdata', return_value=mock_flagdata_task),
    ):
        handler = VLASetjyQAHandler()
        handler.handle(context, result)

    assert len(result.qa.pool) == 1
    assert result.qa.pool[0].score == 0.0
    assert result.qa.pool[0].longmsg == 'Standard calibrator 3C48 is fully flagged'


def test_13b_scenario_flux_cal_and_pol_cal() -> None:
    """Verify secondary standard (pol cal only) does not produce spurious failure.

    In the 13B project case, 3C48 is observed as flux cal at the beginning (AMPLITUDE),
    and 3C138 is observed as pol cal at the end (POLARIZATION only, NO AMPLITUDE).
    """
    context, result = create_mock_context_and_result()
    names = ['3C48', '3C138', '3C147', '3C286']
    fields = [[0], [1], [], []]

    mock_ms = mock.MagicMock()
    mock_field0 = MockDomainField(0, '3C48', ['AMPLITUDE'])
    mock_field1 = MockDomainField(1, '3C138', ['POLARIZATION'])
    mock_ms.get_fields.side_effect = lambda fid: [mock_field0] if fid == 0 else ([mock_field1] if fid == 1 else [])
    context.observing_run.get_ms.return_value = mock_ms

    flagdata_result = {'field': {'3C48': {'flagged': 50, 'total': 5000}}}
    mock_flagdata_task = mock.MagicMock()
    mock_flagdata_task.execute.return_value = flagdata_result

    with (
        mock.patch('pipeline.hifv.tasks.setmodel.vlasetjy.standard_sources', return_value=(names, fields)),
        mock.patch('pipeline.infrastructure.casa_tasks.flagdata', return_value=mock_flagdata_task) as mock_flagdata,
    ):
        handler = VLASetjyQAHandler()
        handler.handle(context, result)
        # Verify flagdata is ONLY called for field 0 (3C48), not field 1 (3C138)
        mock_flagdata.assert_called_once_with(vis='test.ms', mode='summary', field='0', intent='*CALIBRATE*')

    # Exactly 1 score for 3C48, no 0.0 score for 3C138
    assert len(result.qa.pool) == 1
    assert result.qa.pool[0].score == 1.0
    assert result.qa.pool[0].longmsg == 'Standard calibrator 3C48 present.'
    assert result.qa.representative.score == 1.0


def test_18b_scenario_pointing_alias_and_flux_scan() -> None:
    """Verify multi-field standard evaluates the AMPLITUDE field, skipping pointing scans.

    In the 18B project case, 3C286 has field 3 (pointing, SYSTEM_CONFIGURATION) and
    field 4 (1331+305=3C286, AMPLITUDE).
    """
    context, result = create_mock_context_and_result()
    names = ['3C48', '3C138', '3C147', '3C286']
    # 3C286 has both field 3 and field 4
    fields = [[], [], [], [3, 4]]

    mock_ms = mock.MagicMock()
    mock_field3 = MockDomainField(3, '3C286', ['POINTING', 'SYSTEM_CONFIGURATION'])
    mock_field4 = MockDomainField(4, '1331+305=3C286', ['BANDPASS', 'DELAY', 'AMPLITUDE'])
    mock_ms.get_fields.side_effect = lambda fid: [mock_field3] if fid == 3 else ([mock_field4] if fid == 4 else [])
    context.observing_run.get_ms.return_value = mock_ms

    flagdata_result = {'field': {'1331+305=3C286': {'flagged': 100, 'total': 50000}}}
    mock_flagdata_task = mock.MagicMock()
    mock_flagdata_task.execute.return_value = flagdata_result

    with (
        mock.patch('pipeline.hifv.tasks.setmodel.vlasetjy.standard_sources', return_value=(names, fields)),
        mock.patch('pipeline.infrastructure.casa_tasks.flagdata', return_value=mock_flagdata_task) as mock_flagdata,
    ):
        handler = VLASetjyQAHandler()
        handler.handle(context, result)
        # Verify flagdata is ONLY called for field 4, not field 3
        mock_flagdata.assert_called_once_with(vis='test.ms', mode='summary', field='4', intent='*CALIBRATE*')

    assert len(result.qa.pool) == 1
    assert result.qa.pool[0].score == 1.0
    assert result.qa.pool[0].longmsg == 'Standard calibrator 3C286 (1331+305=3C286) present.'
    assert result.qa.representative.score == 1.0


def test_quoted_field_name_in_domain() -> None:
    """Test when domain field name has quotes, e.g. '"3C48"', matching unquoted key in flagdata."""
    context, result = create_mock_context_and_result()
    names = ['3C48', '3C138', '3C147', '3C286']
    fields = [[0], [], [], []]

    mock_ms = mock.MagicMock()
    mock_field0 = MockDomainField(0, '"3C48"', ['AMPLITUDE'])
    mock_ms.get_fields.side_effect = lambda fid: [mock_field0] if fid == 0 else []
    context.observing_run.get_ms.return_value = mock_ms

    flagdata_result = {'field': {'3C48': {'flagged': 10, 'total': 1000}}}
    mock_flagdata_task = mock.MagicMock()
    mock_flagdata_task.execute.return_value = flagdata_result

    with (
        mock.patch('pipeline.hifv.tasks.setmodel.vlasetjy.standard_sources', return_value=(names, fields)),
        mock.patch('pipeline.infrastructure.casa_tasks.flagdata', return_value=mock_flagdata_task),
    ):
        handler = VLASetjyQAHandler()
        handler.handle(context, result)

    assert len(result.qa.pool) == 1
    assert result.qa.pool[0].score == 1.0
    assert result.qa.pool[0].longmsg == 'Standard calibrator 3C48 present.'


def test_missing_or_zero_total_flagdata() -> None:
    """Test that missing field key or total == 0 does not raise KeyError or ZeroDivisionError."""
    context, result = create_mock_context_and_result()
    names = ['3C48', '3C138', '3C147', '3C286']
    fields = [[0], [], [], []]

    mock_ms = mock.MagicMock()
    mock_field0 = MockDomainField(0, '3C48', ['AMPLITUDE'])
    mock_ms.get_fields.side_effect = lambda fid: [mock_field0] if fid == 0 else []
    context.observing_run.get_ms.return_value = mock_ms

    # Empty summary
    flagdata_result = {'field': {}}
    mock_flagdata_task = mock.MagicMock()
    mock_flagdata_task.execute.return_value = flagdata_result

    with (
        mock.patch('pipeline.hifv.tasks.setmodel.vlasetjy.standard_sources', return_value=(names, fields)),
        mock.patch('pipeline.infrastructure.casa_tasks.flagdata', return_value=mock_flagdata_task),
    ):
        handler = VLASetjyQAHandler()
        handler.handle(context, result)

    assert len(result.qa.pool) == 1
    assert result.qa.pool[0].score == 0.0
    assert result.qa.pool[0].longmsg == 'Standard calibrator 3C48 is fully flagged'


def test_multiple_standard_calibrators_both_with_amplitude() -> None:
    """Test when multiple standard calibrators are observed with AMPLITUDE intent."""
    context, result = create_mock_context_and_result()
    names = ['3C48', '3C138', '3C147', '3C286']
    # 3C48 has field 0, 3C286 has field 4
    fields = [[0], [], [], [4]]

    mock_ms = mock.MagicMock()
    mock_field0 = MockDomainField(0, '3C48', ['AMPLITUDE'])
    mock_field4 = MockDomainField(4, '1331+305=3C286', ['AMPLITUDE'])
    mock_ms.get_fields.side_effect = lambda fid: [mock_field0] if fid == 0 else ([mock_field4] if fid == 4 else [])
    context.observing_run.get_ms.return_value = mock_ms

    flagdata_result = {
        'field': {
            '3C48': {'flagged': 10, 'total': 1000},
            '1331+305=3C286': {'flagged': 20, 'total': 2000},
        }
    }
    mock_flagdata_task = mock.MagicMock()
    mock_flagdata_task.execute.return_value = flagdata_result

    with (
        mock.patch('pipeline.hifv.tasks.setmodel.vlasetjy.standard_sources', return_value=(names, fields)),
        mock.patch('pipeline.infrastructure.casa_tasks.flagdata', return_value=mock_flagdata_task) as mock_flagdata,
    ):
        handler = VLASetjyQAHandler()
        handler.handle(context, result)
        mock_flagdata.assert_called_once_with(vis='test.ms', mode='summary', field='0,4', intent='*CALIBRATE*')

    assert len(result.qa.pool) == 2
    assert result.qa.pool[0].longmsg == 'Standard calibrator 3C48 present.'
    assert result.qa.pool[1].longmsg == 'Standard calibrator 3C286 (1331+305=3C286) present.'
    assert all(s.score == 1.0 for s in result.qa.pool)
    assert result.qa.representative.score == 1.0
