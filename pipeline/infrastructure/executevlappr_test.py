"""Tests for VLA Pipeline Processing Request execution."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from . import executevlappr, workflow


@pytest.mark.parametrize('create_errorfile', [False, True])
def test_executeppr_early_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    create_errorfile: bool,
) -> None:
    """An early exit follows its requested VLA PPR completion policy."""
    context = SimpleNamespace(
        pipeline_early_exit=None,
        pipeline_early_exit_active=False,
        task_counter=1,
    )
    saved: list[bool] = []
    resolved_tasks: list[str] = []
    working_dir = tmp_path / 'working'
    working_dir.mkdir()
    info = [
        ('proposal_code', ('Proposal code: ', 'synthetic')),
        ('observatory', ('Observatory: ', 'VLA')),
        ('telescope', ('Telescope: ', 'VLA')),
    ]
    commands = [('request_review', {}), ('must_not_run', {})]

    def get_task(task_name: str) -> Callable[[], object]:
        resolved_tasks.append(task_name)

        def request_early_exit() -> object:
            context.pipeline_early_exit = workflow.PipelineEarlyExitRequest(
                'review required',
                create_errorfile=create_errorfile,
            )
            context.pipeline_early_exit_active = True
            return object()

        return request_early_exit

    monkeypatch.delenv('SCIPIPE_ROOTDIR', raising=False)
    monkeypatch.chdir(working_dir)
    monkeypatch.setattr(executevlappr, 'save_existing_context', lambda: None)
    monkeypatch.setattr(
        executevlappr,
        '_getFirstRequest',
        lambda _: (info, [], 'synthetic', {}, [('asdm', 'test_small.ms')], 'procedure_test', commands),
    )
    monkeypatch.setattr(executevlappr, '_getProcessingIntents', lambda *args: {})
    monkeypatch.setattr(executevlappr, '_getPerformanceParameters', lambda *args: None)
    monkeypatch.setattr(executevlappr.cli, 'h_init', lambda **kwargs: context)
    monkeypatch.setattr(executevlappr.cli, 'h_save', lambda: saved.append(True))
    monkeypatch.setattr(executevlappr.cli, 'get_pipeline_task_with_name', get_task)
    monkeypatch.setattr(executevlappr.casa_tools, 'post_to_log', lambda *args, **kwargs: None)
    monkeypatch.setattr(executevlappr.casa_tools, 'set_log_origin', lambda *args, **kwargs: None)
    executevlappr.executeppr('synthetic-ppr.xml', importonly=False)

    assert resolved_tasks == ['request_review']
    assert saved == [True]
    assert bool(list(working_dir.glob('errorexit-*.txt'))) is create_errorfile
