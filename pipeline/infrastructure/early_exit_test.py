"""Tests for propagation of intentional pipeline early exits."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from . import basetask, exceptions, mpihelpers
from .eventbus import TaskStartedEvent, TaskStoppedEvent


class _Inputs:
    def __init__(self, context: SimpleNamespace) -> None:
        self.context = context
        self.vis = 'uid___A002_X000000_X000.ms'
        self._pipeline_casa_task = None

    def as_dict(self) -> dict[str, object]:
        return {}


class _EarlyExitTask(basetask.StandardTaskTemplate):
    Inputs = _Inputs

    def prepare(self, **parameters: object) -> None:
        raise exceptions.PipelineEarlyExit('review required')

    def analyse(self, result: object) -> object:
        return result


def test_standard_task_propagates_early_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A task early exit bypasses failed-result conversion."""
    casa_log = tmp_path / 'casa.log'
    casa_log.write_text('', encoding='utf-8')

    monkeypatch.setattr(basetask.utils, 'is_top_level_task', lambda: True)
    monkeypatch.setattr(basetask.utils, 'pickle_copy', lambda value: value)
    monkeypatch.setattr(basetask, '_log_task', lambda task: None)
    monkeypatch.setattr(basetask.pipeline_logging, 'add_handler', lambda handler: None)
    monkeypatch.setattr(basetask.pipeline_logging, 'remove_handler', lambda handler: None)
    monkeypatch.setattr(basetask.casa_tools.log, 'logfile', lambda: str(casa_log))
    monkeypatch.setattr(basetask, 'Executor', lambda context: object())
    monkeypatch.setattr(basetask, 'CasaTasks', lambda executor: object())

    events = []
    monkeypatch.setattr(basetask.eventbus, 'send_message', events.append)

    context = SimpleNamespace(name='early-exit', task_counter=0, subtask_counter=0)
    task = _EarlyExitTask(_Inputs(context))

    with pytest.raises(exceptions.PipelineEarlyExit, match='review required'):
        task.execute()

    assert [type(event) for event in events] == [TaskStartedEvent, TaskStoppedEvent]


def test_sync_task_propagates_early_exit() -> None:
    """The synchronous execution adapter preserves an early exit."""
    def request_early_exit() -> None:
        raise exceptions.PipelineEarlyExit('review required')

    task = mpihelpers.SyncTask(request_early_exit)

    with pytest.raises(exceptions.PipelineEarlyExit, match='review required'):
        task.get_result()


def test_async_task_reconstructs_remote_early_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """The MPI execution adapter reconstructs a remote early exit."""
    task = object.__new__(mpihelpers.AsyncTask)
    task._AsyncTask__pid = 'request-1'
    response = [
        {
            'successful': False,
            'server': 2,
            'traceback': (
                'Traceback (most recent call last):\n'
                'pipeline.infrastructure.exceptions.PipelineEarlyExit: review required\n'
            ),
            'id': 'request-1',
            'parameters': {'tier0_executable': 'test-executable'},
        }
    ]
    monkeypatch.setattr(
        mpihelpers,
        'mpiclient',
        SimpleNamespace(get_command_response=lambda *args, **kwargs: response),
    )

    with pytest.raises(exceptions.PipelineEarlyExit, match='review required'):
        task.get_result()
