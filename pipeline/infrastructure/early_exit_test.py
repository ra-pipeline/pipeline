"""Tests for propagation of intentional pipeline early exits."""

from __future__ import annotations

import pickle
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.h.cli import utils as cli_utils

from . import basetask, exceptions, launcher, workflow
from .eventbus import ResultAcceptedEvent


def test_qa_can_request_early_exit_after_result_acceptance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A QA stop request is stored and reported after accepting its result."""
    result = basetask.Results()
    result.stage_number = 1
    result.inputs = {}

    context = object.__new__(launcher.Context)
    context.name = 'qa-early-exit'
    context.output_dir = str(tmp_path)
    context.results = []
    context.pipeline_early_exit = None
    context.pipeline_early_exit_overridden = False

    events = []
    monkeypatch.setattr(basetask.utils, 'task_depth', lambda: 0)
    monkeypatch.setattr(basetask, 'write_pipeline_casa_tasks', lambda context: None)
    monkeypatch.setattr(basetask, 'DISABLE_WEBLOG', True)
    monkeypatch.setattr(basetask.eventbus, 'send_message', events.append)
    monkeypatch.setattr(
        basetask.pipelineqa.qa_registry,
        'do_qa',
        lambda context, qa_result: qa_result.request_pipeline_early_exit('QA review required'),
    )

    result.accept(context)

    assert context.pipeline_early_exit_active
    assert str(context.pipeline_early_exit) == 'QA review required'
    assert isinstance(events[-1], ResultAcceptedEvent)


def test_context_can_override_early_exit() -> None:
    """An explicit override permits later interactive tasks to run."""
    context = object.__new__(launcher.Context)
    context.pipeline_early_exit = None
    context.pipeline_early_exit_overridden = False
    context.request_pipeline_early_exit(workflow.PipelineEarlyExitRequest('review required'))

    assert context.pipeline_early_exit_active

    context.override_pipeline_early_exit()

    assert not context.pipeline_early_exit_active
    assert str(context.pipeline_early_exit) == 'review required'


def test_early_exit_preserves_errorfile_request_when_pickled() -> None:
    """A saved stop request retains its error-sentinel policy."""
    early_exit = workflow.PipelineEarlyExitRequest('processing failed', create_errorfile=True)

    restored = pickle.loads(pickle.dumps(early_exit))

    assert str(restored) == 'processing failed'
    assert restored.create_errorfile


def test_cli_returns_result_after_merging_early_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI returns normally after merging a workflow stop request."""
    result = basetask.Results()
    result.request_pipeline_early_exit('review required')
    context = SimpleNamespace(pipeline_early_exit_active=False)
    calls = []

    monkeypatch.setattr(cli_utils, '_get_task_inputs', lambda *args: object())
    monkeypatch.setattr(cli_utils, '_execute_task', lambda *args: result)

    def merge_results(context: SimpleNamespace, result: basetask.Results) -> None:
        calls.append('merge')
        context.pipeline_early_exit_active = True

    monkeypatch.setattr(cli_utils, '_merge_results', merge_results)

    returned = cli_utils.execute_task(context, 'h_test', {})

    assert calls == ['merge']
    assert returned is result


def test_cli_blocks_task_while_early_exit_is_active(monkeypatch: pytest.MonkeyPatch) -> None:
    """A later interactive task requires an explicit early-exit override."""
    context = SimpleNamespace(
        pipeline_early_exit=workflow.PipelineEarlyExitRequest('review required'),
        pipeline_early_exit_active=True,
    )
    calls = []

    def task() -> None:
        calls.append('task')

    monkeypatch.setattr(cli_utils.task_registry, 'get_pipeline_class_for_task', lambda _: object())
    monkeypatch.setattr(cli_utils, 'get_context', lambda: context)
    wrapped = cli_utils.cli_wrapper(task)

    with pytest.raises(exceptions.PipelineException, match='override_pipeline_early_exit'):
        wrapped()

    assert calls == []
