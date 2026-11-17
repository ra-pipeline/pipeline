"""Component tests for intentional pipeline workflow exits."""

from __future__ import annotations

import pickle
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import pipeline.cli as pipeline_cli
import pipeline.h.cli.cli as h_cli
from pipeline import recipereducer
from pipeline.h.cli import utils as cli_utils
from pipeline.infrastructure import basetask, exceptions, executeppr, task_registry, vdp
from pipeline.infrastructure.renderer import basetemplates, weblog

pytestmark = pytest.mark.component

_TASK_NAME = 'h_test_workflow_control'
_INVOCATIONS: list[str] = []


class _WorkflowControlInputs(vdp.StandardInputs):
    """Inputs for the test-only workflow control stage."""

    def __init__(self, context: Any, vis: str | list[str] | None = None, action: str = 'complete') -> None:
        super().__init__()
        self.context = context
        self.vis = vis
        self.action = action


class _WorkflowControlTask(basetask.StandardTaskTemplate):
    """Test-only task that completes, fails, or requests an early exit."""

    Inputs = _WorkflowControlInputs
    is_multi_vis_task = True

    def prepare(self, **parameters: Any) -> basetask.Results:
        action = self.inputs.action
        _INVOCATIONS.append(action)

        if action == 'early_exit':
            result = basetask.Results()
            result.request_pipeline_early_exit('synthetic review required')
            return result
        if action == 'failure':
            raise RuntimeError('synthetic task failure')

        return basetask.Results()

    def analyse(self, result: basetask.Results) -> basetask.Results:
        return result


@cli_utils.cli_wrapper
def h_test_workflow_control(
    vis: str | list[str] | None = None,
    action: str = 'complete',
) -> None:
    """Invoke the test-only workflow control stage."""


@pytest.fixture
def registered_workflow_control_task(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Register the test task and restore global registries afterward."""
    original_task_map = list(task_registry.task_map)
    task_registry.set_task_identifier(_TASK_NAME, _WorkflowControlTask)
    weblog.add_renderer(
        _WorkflowControlTask,
        basetemplates.T2_4MDetailsDefaultRenderer(description='Test workflow control'),
        group_by=weblog.UNGROUPED,
    )
    monkeypatch.setitem(pipeline_cli.__dict__, _TASK_NAME, h_test_workflow_control)
    _INVOCATIONS.clear()
    h_cli.stack.pop(h_cli.PIPELINE_NAME, None)

    try:
        yield
    finally:
        task_registry.task_map[:] = original_task_map
        weblog.registry.default_map.pop(_WorkflowControlTask, None)
        weblog.registry._render_ungrouped.discard(_WorkflowControlTask.__name__)
        _INVOCATIONS.clear()
        h_cli.stack.pop(h_cli.PIPELINE_NAME, None)


def _write_recipe(path: Path) -> None:
    path.write_text(
        f"""\
<ProcessingProcedure>
    <ProcedureTitle>test_early_exit</ProcedureTitle>
    <ProcessingCommand>
        <Command>{_TASK_NAME}</Command>
        <ParameterSet>
            <Parameter><Keyword>vis</Keyword><Value>test_small.ms</Value></Parameter>
            <Parameter><Keyword>action</Keyword><Value>early_exit</Value></Parameter>
        </ParameterSet>
    </ProcessingCommand>
    <ProcessingCommand>
        <Command>{_TASK_NAME}</Command>
        <ParameterSet>
            <Parameter><Keyword>vis</Keyword><Value>test_small.ms</Value></Parameter>
            <Parameter><Keyword>action</Keyword><Value>complete</Value></Parameter>
        </ParameterSet>
    </ProcessingCommand>
</ProcessingProcedure>
""",
        encoding='utf-8',
    )


def _load_saved_context(directory: Path) -> Any:
    (context_path,) = directory.glob('*.context')
    with context_path.open('rb') as context_file:
        return pickle.load(context_file)


def _assert_early_exit_weblog(directory: Path) -> None:
    """Assert that the first stage detail page explains the workflow stop."""
    detail_pages = list(directory.rglob('stage1/t2-4m_details.html'))
    assert len(detail_pages) == 1
    detail_page = detail_pages[0].read_text(encoding='utf-8')
    assert 'Pipeline execution stopped after this task.' in detail_page
    assert 'synthetic review required' in detail_page


def _configure_ppr(monkeypatch: pytest.MonkeyPatch, action: str) -> None:
    info = [
        ('proposal_code', ('Proposal code: ', 'synthetic')),
        ('observatory', ('Observatory: ', 'ALMA')),
        ('telescope', ('Telescope: ', 'ALMA')),
    ]
    structure = [
        ('ous_entity_id', ('OUS entity ID: ', 'uid://A001/X0/X0')),
        ('ous_part_id', ('OUS part ID: ', 'X0')),
        ('ous_title', ('OUS title: ', 'Synthetic')),
        ('ous_type', ('OUS type: ', 'Member')),
        ('ps_entity_id', ('PS entity ID: ', 'uid://A001/X0/X1')),
        ('ousstatus_entity_id', ('OUS status ID: ', 'uid://A001/X0/X2')),
    ]
    commands = [
        (_TASK_NAME, {'vis': 'test_small.ms', 'action': action}),
        (_TASK_NAME, {'vis': 'test_small.ms', 'action': 'complete'}),
    ]

    monkeypatch.delenv('SCIPIPE_ROOTDIR', raising=False)
    monkeypatch.setattr(executeppr, 'save_existing_context', lambda: None)
    monkeypatch.setattr(
        executeppr,
        '_getFirstRequest',
        lambda _: (info, structure, 'synthetic', {}, [('asdm', 'test_small.ms')], 'procedure_test', commands),
    )
    monkeypatch.setattr(executeppr, '_getProcessingIntents', lambda *args: {})


def test_recipe_early_exit_saves_context_and_skips_later_stage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    registered_workflow_control_task: None,
) -> None:
    """A recipe consumes the task signal and saves its partial context."""
    monkeypatch.chdir(tmp_path)
    recipe = tmp_path / 'procedure_test_early_exit.xml'
    _write_recipe(recipe)

    context = recipereducer.reduce(procedure=str(recipe))
    saved_context = _load_saved_context(tmp_path)

    assert _INVOCATIONS == ['early_exit']
    assert not list(tmp_path.rglob('errorexit-*.txt'))
    assert context.task_counter == 1
    assert saved_context.task_counter == 1
    assert saved_context.pipeline_early_exit_active
    assert str(saved_context.pipeline_early_exit) == 'synthetic review required'
    _assert_early_exit_weblog(tmp_path)


def test_ppr_early_exit_saves_context_without_errorfile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    registered_workflow_control_task: None,
) -> None:
    """A PPR consumes the task signal without creating an error sentinel."""
    working_dir = tmp_path / 'working'
    working_dir.mkdir()
    monkeypatch.chdir(working_dir)
    _configure_ppr(monkeypatch, action='early_exit')

    executeppr.executeppr('synthetic-ppr.xml', importonly=False, breakpoint='')
    saved_context = _load_saved_context(working_dir)

    assert _INVOCATIONS == ['early_exit']
    assert not list(tmp_path.rglob('errorexit-*.txt'))
    assert saved_context.task_counter == 1
    assert saved_context.pipeline_early_exit_active
    assert str(saved_context.pipeline_early_exit) == 'synthetic review required'
    _assert_early_exit_weblog(tmp_path)


def test_ppr_ordinary_failure_still_creates_errorfile(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    registered_workflow_control_task: None,
) -> None:
    """An ordinary task exception retains the existing fatal PPR behavior."""
    working_dir = tmp_path / 'working'
    working_dir.mkdir()
    monkeypatch.chdir(working_dir)
    _configure_ppr(monkeypatch, action='failure')
    monkeypatch.setattr(executeppr, 'export_on_exception', lambda *args: None)

    with pytest.raises(exceptions.PipelineException, match='synthetic task failure'):
        executeppr.executeppr('synthetic-ppr.xml', importonly=False, breakpoint='')
    saved_context = _load_saved_context(working_dir)

    assert _INVOCATIONS == ['failure']
    assert list(working_dir.glob('errorexit-*.txt'))
    assert saved_context.task_counter == 1
