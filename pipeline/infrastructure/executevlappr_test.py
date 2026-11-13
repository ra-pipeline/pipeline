"""Tests for VLA Pipeline Processing Request execution."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace

import pytest

from . import exceptions, executevlappr


def test_executeppr_early_exit_saves_without_errorfile(monkeypatch: pytest.MonkeyPatch) -> None:
    """An early exit follows the normal VLA PPR completion path."""
    context = SimpleNamespace()
    saved: list[bool] = []
    resolved_tasks: list[str] = []
    info = [
        ('proposal_code', ('Proposal code: ', 'synthetic')),
        ('observatory', ('Observatory: ', 'VLA')),
        ('telescope', ('Telescope: ', 'VLA')),
    ]
    commands = [('request_review', {}), ('must_not_run', {})]

    def get_task(task_name: str) -> Callable[[], None]:
        resolved_tasks.append(task_name)

        def request_early_exit() -> None:
            raise exceptions.PipelineEarlyExit('review required')

        return request_early_exit

    monkeypatch.delenv('SCIPIPE_ROOTDIR', raising=False)
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
    monkeypatch.setattr(
        executevlappr.utils,
        'write_errorexit_file',
        lambda *args, **kwargs: pytest.fail('early exit wrote an errorexit file'),
    )

    executevlappr.executeppr('synthetic-ppr.xml', importonly=False)

    assert resolved_tasks == ['request_review']
    assert saved == [True]
