"""Tests for intentional early exits from recipe workflows."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline import recipereducer
from pipeline.infrastructure import basetask, workflow


def test_execute_task_returns_result_with_early_exit_request() -> None:
    """The recipe task adapter returns a result containing a stop request."""
    result = basetask.Results()
    result.request_pipeline_early_exit('review required')

    def request_early_exit() -> basetask.Results:
        return result

    returned = recipereducer._execute_task(request_early_exit, {})

    assert returned is result


@pytest.mark.parametrize('create_errorfile', [False, True])
def test_reduce_stops_recipe_and_saves_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    create_errorfile: bool,
) -> None:
    """A recipe early exit skips later tasks and follows its sentinel policy."""
    context = SimpleNamespace(
        output_dir=str(tmp_path),
        task_counter=1,
        pipeline_early_exit=None,
        pipeline_early_exit_active=False,
    )
    executed = []
    saved = []

    def request_early_exit() -> SimpleNamespace:
        executed.append('stop')
        context.pipeline_early_exit = workflow.PipelineEarlyExitRequest(
            'review required',
            create_errorfile=create_errorfile,
        )
        context.pipeline_early_exit_active = True
        return SimpleNamespace(stage_number=1)

    def should_not_run() -> None:
        executed.append('later task')

    monkeypatch.setattr(recipereducer, '_register_context', lambda *args: None)
    monkeypatch.setattr(
        recipereducer,
        '_get_tasks',
        lambda *args: iter(((request_early_exit, {}), (should_not_run, {}))),
    )
    monkeypatch.setattr(recipereducer.cli, 'h_save', lambda: saved.append(True))

    result = recipereducer.reduce(context=context)

    assert result is context
    assert executed == ['stop']
    assert saved == [True]
    assert bool(list(tmp_path.glob('errorexit-*.txt'))) is create_errorfile


def test_run_named_tasks_stops_and_saves_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """An explicit task list exits early and saves the context."""
    context = SimpleNamespace(
        output_dir='',
        task_counter=1,
        pipeline_early_exit=None,
        pipeline_early_exit_active=False,
    )
    resolved = []
    saved = []

    def get_task(task_name: str) -> Callable[[], SimpleNamespace]:
        resolved.append(task_name)

        def request_early_exit() -> SimpleNamespace:
            context.pipeline_early_exit = workflow.PipelineEarlyExitRequest('review required')
            context.pipeline_early_exit_active = True
            return SimpleNamespace()

        return request_early_exit

    monkeypatch.setattr(recipereducer.cli, 'h_init', lambda: context)
    monkeypatch.setattr(recipereducer.cli, 'h_save', lambda: saved.append(True))
    monkeypatch.setattr(recipereducer.cli, 'get_pipeline_task_with_name', get_task)
    result = recipereducer.run_named_tasks([('stop', {}), ('later_task', {})])

    assert result is context
    assert resolved == ['stop']
    assert saved == [True]
