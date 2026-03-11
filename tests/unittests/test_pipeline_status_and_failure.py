from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline.h.cli import utils as h_cli_utils
from pipeline.hifa.tasks.imageprecheck import imageprecheck
from pipeline.hif.tasks.findcont import resultobjects as findcont_resultobjects
from pipeline.hif.tasks.checkproductsize import resultobjects as checkproductsize_resultobjects
from pipeline.hif.tasks.makeimages import resultobjects as makeimages_resultobjects
from pipeline.hif.tasks.makeimlist import resultobjects as makeimlist_resultobjects
from pipeline.infrastructure import conditions as pipeline_conditions
from pipeline.infrastructure import exceptions
from pipeline.infrastructure import executeppr
from pipeline.infrastructure import executevlappr
from pipeline.infrastructure import launcher
from pipeline.infrastructure import mpihelpers
from pipeline.infrastructure import sessionutils
from pipeline.infrastructure import status
from pipeline.infrastructure import timetracker
from pipeline.infrastructure import basetask
from pipeline.infrastructure.renderer import basetemplates, htmlrenderer, rendererutils
from pipeline.infrastructure.eventbus import (
    ConditionClearedEvent,
    ConditionRaisedEvent,
    ContextCreatedEvent,
    LogMessageEvent,
    ResultAcceptedEvent,
    RunCompletedEvent,
    RunStoppedEvent,
    TaskStartedEvent,
    TaskStoppedEvent,
)
from pipeline import recipereducer


def _sample_info() -> list[tuple[str, tuple[str, str]]]:
    return [
        ('proposal_code', ('Proposal code: ', 'P123')),
        ('observatory', ('Observatory: ', 'ALMA')),
        ('telescope', ('Telescope: ', 'ALMA')),
    ]


def _sample_structure() -> list[tuple[str, tuple[str, str]]]:
    return [
        ('ous_entity_id', ('OUS entity id: ', 'ous-entity')),
        ('ous_part_id', ('OUS part id: ', 'ous-part')),
        ('ous_title', ('OUS title: ', 'ous-title')),
        ('ous_type', ('OUS type: ', 'ous-type')),
        ('ps_entity_id', ('PS entity id: ', 'ps-entity')),
        ('ousstatus_entity_id', ('OUS status entity id: ', 'ousstatus-entity')),
    ]


def _sample_vla_structure() -> list[tuple[str, tuple[str, str]]]:
    return []


def _status_context(
    *,
    name: str,
    observatory: str = 'EVLA',
    recipe_name: str = 'hifv_calimage',
    results: list[object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        results=[] if results is None else results,
        project_summary=SimpleNamespace(telescope=observatory, observatory=observatory),
        project_structure=SimpleNamespace(recipe_name=recipe_name),
        get_recipe_name=lambda: recipe_name,
    )


def _condition_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    name: str = 'ctx-condition',
) -> tuple[launcher.Context, list[object]]:
    published: list[object] = []
    monkeypatch.setattr(launcher.utils, 'mkdir_p', lambda path: None)
    monkeypatch.setattr(launcher.eventbus, 'send_message', lambda event: published.append(event))
    context = launcher.Context(name)
    context.output_dir = str(tmp_path)
    context.report_dir = str(tmp_path / 'html')
    return context, published


def test_executeppr_raises_request_error_for_empty_relative_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sci_root = tmp_path / 'sci_root'
    working_dir = sci_root / 'working'
    working_dir.mkdir(parents=True)

    monkeypatch.setenv('SCIPIPE_ROOTDIR', str(sci_root))
    monkeypatch.setattr(executeppr, 'save_existing_context', lambda: None)
    monkeypatch.setattr(executeppr.casa_tools, 'post_to_log', lambda *args, **kwargs: None)
    monkeypatch.setattr(executeppr, '_getFirstRequest', lambda _: (
        _sample_info(),
        _sample_structure(),
        '',
        {},
        [('sb1', 'uid___A002_X1')],
        'procedure_hifa_calimage.xml',
        [('hifa_importdata', {})],
    ))
    monkeypatch.setattr(executeppr, '_getProcessingIntents', lambda *_: {})
    monkeypatch.setattr(executeppr.cli, 'h_init', lambda **_: SimpleNamespace(processing_intents={}))

    with pytest.raises(exceptions.PipelineRequestError) as exc_info:
        executeppr.executeppr('example.xml', importonly=False, interactive=False)

    assert exc_info.value.reason_code == 'undefined_relative_data_path'
    assert list(working_dir.glob('errorexit-*.txt'))


def test_executeppr_raises_task_execution_error_for_failed_stage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sci_root = tmp_path / 'sci_root'
    relative_path = 'alma_run'
    working_dir = sci_root / relative_path / 'working'
    raw_dir = sci_root / relative_path / 'rawdata'
    working_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)

    context = SimpleNamespace(
        processing_intents={},
        project_summary=None,
        project_structure=None,
        project_performance_parameters=None,
    )

    def failing_task(**_: object) -> None:
        raise RuntimeError('boom')

    monkeypatch.setenv('SCIPIPE_ROOTDIR', str(sci_root))
    monkeypatch.setattr(executeppr, 'save_existing_context', lambda: None)
    monkeypatch.setattr(executeppr.casa_tools, 'post_to_log', lambda *args, **kwargs: None)
    monkeypatch.setattr(executeppr.casa_tools, 'set_log_origin', lambda **kwargs: None)
    monkeypatch.setattr(executeppr, '_getFirstRequest', lambda _: (
        _sample_info(),
        _sample_structure(),
        relative_path,
        {},
        [('sb1', 'uid___A002_X1')],
        'procedure_hifa_calimage.xml',
        [('hifa_importdata', {})],
    ))
    monkeypatch.setattr(executeppr, '_getProcessingIntents', lambda *_: {})
    monkeypatch.setattr(executeppr, '_getPerformanceParameters', lambda *_: {})
    monkeypatch.setattr(executeppr.cli, 'h_init', lambda **_: context)
    monkeypatch.setattr(executeppr.cli, 'get_pipeline_task_with_name', lambda _: failing_task)
    monkeypatch.setattr(executeppr.cli, 'h_save', lambda: None)
    monkeypatch.setattr(executeppr, 'export_on_exception', lambda *args, **kwargs: None)

    with pytest.raises(exceptions.PipelineTaskExecutionError) as exc_info:
        executeppr.executeppr('example.xml', importonly=False, interactive=False)

    assert exc_info.value.reason_code == 'task_execution_failed'
    assert list(working_dir.glob('errorexit-*.txt'))


def test_executevlappr_raises_request_error_for_empty_relative_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    sci_root = tmp_path / 'sci_root'
    working_dir = sci_root / 'working'
    working_dir.mkdir(parents=True)

    monkeypatch.setenv('SCIPIPE_ROOTDIR', str(sci_root))
    monkeypatch.setattr(executevlappr, 'save_existing_context', lambda: None)
    monkeypatch.setattr(executevlappr.casa_tools, 'post_to_log', lambda *args, **kwargs: None)
    monkeypatch.setattr(executevlappr, '_getFirstRequest', lambda _: (
        _sample_info(),
        _sample_vla_structure(),
        '',
        {},
        [('sb1', 'uid___A002_X1')],
        'procedure_hifv.xml',
        [('hifv_importdata', {})],
    ))
    monkeypatch.setattr(executevlappr, '_getProcessingIntents', lambda *_: {})
    monkeypatch.setattr(executevlappr.cli, 'h_init', lambda **_: SimpleNamespace(processing_intents={}))

    with pytest.raises(exceptions.PipelineRequestError) as exc_info:
        executevlappr.executeppr('example.xml', importonly=False, interactive=False)

    assert exc_info.value.reason_code == 'undefined_relative_data_path'
    assert list(working_dir.glob('errorexit-*.txt'))


def test_executevlappr_raises_task_execution_error_for_failed_stage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    sci_root = tmp_path / 'sci_root'
    relative_path = 'vla_run'
    working_dir = sci_root / relative_path / 'working'
    raw_dir = sci_root / relative_path / 'rawdata'
    working_dir.mkdir(parents=True)
    raw_dir.mkdir(parents=True)

    context = SimpleNamespace(
        processing_intents={},
        project_summary=None,
        project_structure=None,
        project_performance_parameters=None,
    )

    def failing_task(**_: object) -> None:
        raise RuntimeError('boom')

    monkeypatch.setenv('SCIPIPE_ROOTDIR', str(sci_root))
    monkeypatch.setattr(executevlappr, 'save_existing_context', lambda: None)
    monkeypatch.setattr(executevlappr.casa_tools, 'post_to_log', lambda *args, **kwargs: None)
    monkeypatch.setattr(executevlappr.casa_tools, 'set_log_origin', lambda **kwargs: None)
    monkeypatch.setattr(executevlappr, '_getFirstRequest', lambda _: (
        _sample_info(),
        _sample_vla_structure(),
        relative_path,
        {},
        [('sb1', 'uid___A002_X1')],
        'procedure_hifv.xml',
        [('hifv_importdata', {})],
    ))
    monkeypatch.setattr(executevlappr, '_getProcessingIntents', lambda *_: {})
    monkeypatch.setattr(executevlappr, '_getPerformanceParameters', lambda *_: {})
    monkeypatch.setattr(executevlappr.cli, 'h_init', lambda **_: context)
    monkeypatch.setattr(executevlappr.cli, 'get_pipeline_task_with_name', lambda _: failing_task)
    monkeypatch.setattr(executevlappr.cli, 'h_save', lambda: None)

    with pytest.raises(exceptions.PipelineTaskExecutionError) as exc_info:
        executevlappr.executeppr('example.xml', importonly=False, interactive=False)

    assert exc_info.value.reason_code == 'task_execution_failed'
    assert list(working_dir.glob('errorexit-*.txt'))


def test_runpipeline_main_maps_pipeline_request_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, 'casashell', SimpleNamespace(argv=['casa', '-c', 'runpipeline.py', 'example.xml']))
    runpipeline = importlib.reload(importlib.import_module('pipeline.runpipeline'))

    def raise_request_error(*args: object, **kwargs: object) -> None:
        raise exceptions.PipelineRequestError('bad request', reason_code='bad_request')

    monkeypatch.setattr(runpipeline.eppr, 'executeppr', raise_request_error)
    published: list[tuple[str | None, str]] = []
    monkeypatch.setattr(
        runpipeline.status,
        'publish_terminal_exception',
        lambda exc, *, request_path, source: published.append((request_path, source)),
    )

    exit_code = runpipeline.main(['casa', '-c', 'runpipeline.py', 'example.xml'])

    assert exit_code == int(exceptions.PipelineExitCode.INVALID_REQUEST)
    assert published == [('example.xml', 'runpipeline')]


def test_runpipeline_main_maps_missing_ppr_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, 'casashell', SimpleNamespace(argv=['casa', '-c', 'runpipeline.py']))
    runpipeline = importlib.reload(importlib.import_module('pipeline.runpipeline'))
    published: list[tuple[str | None, str]] = []
    monkeypatch.setattr(
        runpipeline.status,
        'publish_terminal_exception',
        lambda exc, *, request_path, source: published.append((request_path, source)),
    )

    exit_code = runpipeline.main(['casa', '-c', 'runpipeline.py'])

    assert exit_code == int(exceptions.PipelineExitCode.INVALID_REQUEST)
    assert published == [(None, 'runpipeline')]


def test_runpipeline_main_maps_pipeline_stop_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, 'casashell', SimpleNamespace(argv=['casa', '-c', 'runpipeline.py', 'example.xml']))
    runpipeline = importlib.reload(importlib.import_module('pipeline.runpipeline'))

    def raise_stop_requested(*args: object, **kwargs: object) -> None:
        raise exceptions.PipelineStopRequested('operator requested stop', reason_code='operator_requested_stop')

    monkeypatch.setattr(runpipeline.eppr, 'executeppr', raise_stop_requested)
    published: list[tuple[str | None, str]] = []
    monkeypatch.setattr(
        runpipeline.status,
        'publish_terminal_exception',
        lambda exc, *, request_path, source: published.append((request_path, source)),
    )

    exit_code = runpipeline.main(['casa', '-c', 'runpipeline.py', 'example.xml'])

    assert exit_code == int(exceptions.PipelineExitCode.STOPPED)
    assert published == [('example.xml', 'runpipeline')]


def test_runvlapipeline_main_maps_pipeline_request_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, 'casashell', SimpleNamespace(argv=['casa', '-c', 'runvlapipeline.py', 'example.xml']))
    runvlapipeline = importlib.reload(importlib.import_module('pipeline.runvlapipeline'))

    def raise_request_error(*args: object, **kwargs: object) -> None:
        raise exceptions.PipelineRequestError('bad request', reason_code='bad_request')

    monkeypatch.setattr(runvlapipeline.eppr, 'executeppr', raise_request_error)
    published: list[tuple[str | None, str]] = []
    monkeypatch.setattr(
        runvlapipeline.status,
        'publish_terminal_exception',
        lambda exc, *, request_path, source: published.append((request_path, source)),
    )

    exit_code = runvlapipeline.main(['casa', '-c', 'runvlapipeline.py', 'example.xml'])

    assert exit_code == int(exceptions.PipelineExitCode.INVALID_REQUEST)
    assert published == [('example.xml', 'runvlapipeline')]


def test_runvlapipeline_main_maps_missing_ppr_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, 'casashell', SimpleNamespace(argv=['casa', '-c', 'runvlapipeline.py']))
    runvlapipeline = importlib.reload(importlib.import_module('pipeline.runvlapipeline'))
    published: list[tuple[str | None, str]] = []
    monkeypatch.setattr(
        runvlapipeline.status,
        'publish_terminal_exception',
        lambda exc, *, request_path, source: published.append((request_path, source)),
    )

    exit_code = runvlapipeline.main(['casa', '-c', 'runvlapipeline.py'])

    assert exit_code == int(exceptions.PipelineExitCode.INVALID_REQUEST)
    assert published == [(None, 'runvlapipeline')]


def test_runvlapipeline_main_maps_pipeline_stop_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, 'casashell', SimpleNamespace(argv=['casa', '-c', 'runvlapipeline.py', 'example.xml']))
    runvlapipeline = importlib.reload(importlib.import_module('pipeline.runvlapipeline'))

    def raise_stop_requested(*args: object, **kwargs: object) -> None:
        raise exceptions.PipelineStopRequested('operator requested stop', reason_code='operator_requested_stop')

    monkeypatch.setattr(runvlapipeline.eppr, 'executeppr', raise_stop_requested)
    published: list[tuple[str | None, str]] = []
    monkeypatch.setattr(
        runvlapipeline.status,
        'publish_terminal_exception',
        lambda exc, *, request_path, source: published.append((request_path, source)),
    )

    exit_code = runvlapipeline.main(['casa', '-c', 'runvlapipeline.py', 'example.xml'])

    assert exit_code == int(exceptions.PipelineExitCode.STOPPED)
    assert published == [('example.xml', 'runvlapipeline')]


def test_runpipeline_main_publishes_completion_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, 'casashell', SimpleNamespace(argv=['casa', '-c', 'runpipeline.py', 'example.xml']))
    runpipeline = importlib.reload(importlib.import_module('pipeline.runpipeline'))

    monkeypatch.setattr(runpipeline.eppr, 'executeppr', lambda *args, **kwargs: None)
    published: list[str] = []
    monkeypatch.setattr(
        runpipeline.status,
        'publish_active_context_completion',
        lambda *, source: published.append(source),
    )

    exit_code = runpipeline.main(['casa', '-c', 'runpipeline.py', 'example.xml'])

    assert exit_code == int(exceptions.PipelineExitCode.SUCCESS)
    assert published == ['runpipeline']


def test_exit_code_for_exception_maps_known_and_unknown_types() -> None:
    assert exceptions.exit_code_for_exception(exceptions.PipelineRequestError('bad')) == 20
    assert exceptions.exit_code_for_exception(exceptions.PipelineStopRequested('stop')) == 10
    assert exceptions.exit_code_for_exception(exceptions.PipelineTaskExecutionError('bad')) == 30
    assert exceptions.exit_code_for_exception(KeyboardInterrupt()) == 10
    assert exceptions.exit_code_for_exception(RuntimeError('bad')) == 40


def test_get_context_raises_request_error_when_pipeline_not_initialized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(h_cli_utils.cli, 'PIPELINE_NAME', 'pipeline')
    monkeypatch.setattr(h_cli_utils.cli, 'stack', {})

    with pytest.raises(exceptions.PipelineRequestError) as exc_info:
        h_cli_utils.get_context()

    assert exc_info.value.reason_code == 'pipeline_not_initialized'


def test_execute_task_raises_task_execution_error_for_tracebacks(monkeypatch: pytest.MonkeyPatch) -> None:
    result = SimpleNamespace(taskname=None)

    monkeypatch.setattr(h_cli_utils, '_get_task_inputs', lambda *args, **kwargs: object())
    monkeypatch.setattr(h_cli_utils, '_execute_task', lambda *args, **kwargs: result)
    monkeypatch.setattr(h_cli_utils, '_merge_results', lambda *args, **kwargs: None)
    monkeypatch.setattr(h_cli_utils.utils, 'get_tracebacks', lambda _: ['traceback text'])

    with pytest.raises(exceptions.PipelineTaskExecutionError) as exc_info:
        h_cli_utils.execute_task(SimpleNamespace(), 'hifa_mocktask', {})

    assert exc_info.value.reason_code == 'task_execution_failed'
    assert result.taskname == 'hifa_mocktask'


def test_recipereducer_execute_task_raises_task_execution_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(recipereducer, '_as_task_call', lambda task, args: 'mock_task()')
    monkeypatch.setattr(recipereducer.utils, 'get_tracebacks', lambda _: ['traceback text'])

    with pytest.raises(exceptions.PipelineTaskExecutionError) as exc_info:
        recipereducer._execute_task(lambda **kwargs: SimpleNamespace(), {})

    assert exc_info.value.reason_code == 'task_execution_failed'


def test_sync_task_get_result_raises_typed_execution_error() -> None:
    def failing_callable() -> None:
        raise RuntimeError('boom')

    task = mpihelpers.SyncTask(failing_callable)

    with pytest.raises(exceptions.PipelineTaskExecutionError) as exc_info:
        task.get_result()

    assert exc_info.value.reason_code == 'sync_task_execution_failed'


def test_sync_task_get_result_reraises_pipeline_stop_requested() -> None:
    def stopping_callable() -> None:
        raise exceptions.PipelineStopRequested(
            'operator requested stop',
            reason_code='operator_requested_stop',
        )

    task = mpihelpers.SyncTask(stopping_callable)

    with pytest.raises(exceptions.PipelineStopRequested) as exc_info:
        task.get_result()

    assert exc_info.value.reason_code == 'operator_requested_stop'


def test_async_task_get_result_reraises_remote_pipeline_stop_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    task = object.__new__(mpihelpers.AsyncTask)
    task._AsyncTask__pid = 'pid-1'

    response = [{
        'successful': False,
        'server': 2,
        'traceback': (
            'Traceback (most recent call last):\n'
            '  File "worker.py", line 1, in <module>\n'
            'pipeline.infrastructure.exceptions.PipelineStopRequested: operator requested stop\n'
        ),
        'id': 'pid-1',
        'parameters': {'tier0_executable': 'mock-executable'},
    }]
    monkeypatch.setattr(
        mpihelpers,
        'mpiclient',
        SimpleNamespace(get_command_response=lambda *args, **kwargs: response),
    )

    with pytest.raises(exceptions.PipelineStopRequested) as exc_info:
        task.get_result()

    assert str(exc_info.value) == 'operator requested stop'


def test_parallel_template_prepare_reraises_pipeline_stop_requested(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyInputs:
        def __init__(self) -> None:
            self.vis = ['uid___A002_X1']

    class DummyParallelTask(sessionutils.ParallelTemplate):
        Inputs = DummyInputs

        @property
        def Task(self):
            return object

        def analyse(self, assessed):
            return assessed

    class DummyWorkerTask:
        def get_result(self):
            raise exceptions.PipelineStopRequested(
                'operator requested stop',
                reason_code='operator_requested_stop',
            )

    class DummyFactory:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def get_task(self, vis: str):
            return ({'vis': vis}, DummyWorkerTask())

    monkeypatch.setattr(sessionutils, 'as_list', lambda value: value)
    monkeypatch.setattr(sessionutils, 'VDPTaskFactory', DummyFactory)

    task = DummyParallelTask(DummyInputs())
    task._executor = None

    with pytest.raises(exceptions.PipelineStopRequested) as exc_info:
        task.prepare()

    assert exc_info.value.reason_code == 'operator_requested_stop'


def test_timetracker_accepts_task_stopped_event(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(timetracker.eventbus, 'subscribe', lambda *args, **kwargs: None)

    tracker = timetracker.TaskTimeTracker(context_name='ctx-stop', output_dir=str(tmp_path))

    tracker.on_task_lifecycle_event(TaskStartedEvent('ctx-stop', 4, task_name='hifa_importdata'))
    tracker.on_task_lifecycle_event(
        TaskStoppedEvent(
            'ctx-stop',
            4,
            task_name='hifa_importdata',
            reason_code='operator_requested_stop',
            message='operator requested stop',
        )
    )

    tracker.export()

    export = json.loads((tmp_path / 'ctx-stop.timetracker.json').read_text(encoding='utf-8'))

    assert '4' in export['tasks']
    assert float(export['tasks']['4']['seconds']) >= 0.0


def test_cli_wrapper_swallows_pipeline_stop_requested_for_direct_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(h_cli_utils.task_registry, 'get_pipeline_class_for_task', lambda _: object)
    context = SimpleNamespace()
    monkeypatch.setattr(h_cli_utils, 'get_context', lambda: context)
    monkeypatch.setattr(
        h_cli_utils,
        'execute_task',
        lambda *args, **kwargs: (_ for _ in ()).throw(
            exceptions.PipelineStopRequested('operator requested stop', reason_code='operator_requested_stop')
        ),
    )
    published: list[tuple[str | None, str]] = []
    monkeypatch.setattr(
        h_cli_utils.status,
        'publish_terminal_exception',
        lambda exc, *, request_path, source: published.append((request_path, source)),
    )
    rendered: list[object] = []
    monkeypatch.setattr(
        h_cli_utils.htmlrenderer.WebLogGenerator,
        'render',
        lambda ctx: rendered.append(ctx),
    )

    @h_cli_utils.cli_wrapper
    def hifa_mocktask(vis: str) -> None:
        return None

    result = hifa_mocktask(vis='uid___A002_X1')

    assert result is None
    assert published == [(None, 'cli')]
    assert getattr(context, h_cli_utils.STOP_REQUESTED_ATTR) is True
    assert rendered == [context]


def test_cli_wrapper_propagates_pipeline_stop_requested_when_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(h_cli_utils.task_registry, 'get_pipeline_class_for_task', lambda _: object)
    monkeypatch.setattr(h_cli_utils, 'get_context', lambda: SimpleNamespace())
    monkeypatch.setattr(
        h_cli_utils,
        'execute_task',
        lambda *args, **kwargs: (_ for _ in ()).throw(
            exceptions.PipelineStopRequested('operator requested stop', reason_code='operator_requested_stop')
        ),
    )

    @h_cli_utils.cli_wrapper
    def hifa_mocktask(vis: str) -> None:
        return None

    with h_cli_utils.set_contextvar(h_cli_utils.propagate_stop_requested, True):
        with pytest.raises(exceptions.PipelineStopRequested) as exc_info:
            hifa_mocktask(vis='uid___A002_X1')

    assert exc_info.value.reason_code == 'operator_requested_stop'


def test_cli_wrapper_skips_later_tasks_after_direct_clean_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(h_cli_utils.task_registry, 'get_pipeline_class_for_task', lambda _: object)
    context = SimpleNamespace(_pipeline_stop_requested=True)
    monkeypatch.setattr(h_cli_utils, 'get_context', lambda: context)
    executed: list[str] = []
    monkeypatch.setattr(
        h_cli_utils,
        'execute_task',
        lambda *args, **kwargs: executed.append('executed'),
    )

    @h_cli_utils.cli_wrapper
    def hifa_flagdata(vis: str) -> None:
        return None

    result = hifa_flagdata(vis='uid___A002_X1')

    assert result is None
    assert executed == []


def test_status_tracker_writes_event_stream_and_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    subscriptions: list[tuple[object, str]] = []
    monkeypatch.setattr(status.eventbus, 'subscribe', lambda fn, topic: subscriptions.append((fn, topic)))
    added_handlers: list[object] = []
    removed_handlers: list[object] = []
    monkeypatch.setattr(status.logging, 'add_handler', lambda handler: added_handlers.append(handler))
    monkeypatch.setattr(status.logging, 'remove_handler', lambda handler: removed_handlers.append(handler))
    context = _status_context(
        name='ctx-001',
        results=[
            SimpleNamespace(
                taskname='hifv_importdata',
                pipeline_casa_task='hifv_importdata(vis=[\'uid\'])',
                logrecords=[
                    SimpleNamespace(levelno=status.logging.WARNING),
                    SimpleNamespace(levelno=status.logging.ATTENTION),
                    SimpleNamespace(levelno=status.logging.ATTENTION),
                ],
            )
        ],
    )
    monkeypatch.setattr(status, '_get_active_context', lambda: context)
    tracker = status.PipelineStatusTracker('ctx-001', str(tmp_path))

    tracker.on_context_lifecycle_event(ContextCreatedEvent(context_name='ctx-001', output_dir=str(tmp_path)))
    tracker.on_task_lifecycle_event(TaskStartedEvent('ctx-001', 3, task_name='hifv_importdata'))
    monkeypatch.setattr(
        status.eventbus,
        'send_message',
        lambda event: tracker.on_log_message_event(event) if isinstance(event, LogMessageEvent) else None,
    )
    tracker.live_log_handler.emit(
        SimpleNamespace(
            levelno=status.logging.WARNING,
            name='pipeline.hifv.importdata',
            getMessage=lambda: 'flagged something',
        )
    )
    tracker.on_result_lifecycle_event(ResultAcceptedEvent('ctx-001', 3, task_name='hifv_importdata'))

    running_snapshot = json.loads((tmp_path / 'pipeline-status.json').read_text(encoding='utf-8'))

    tracker.on_run_lifecycle_event(
        RunCompletedEvent(context_name='ctx-001', output_dir=str(tmp_path), source='runpipeline')
    )

    event_lines = (tmp_path / 'pipeline-events.jsonl').read_text(encoding='utf-8').strip().splitlines()
    snapshot = json.loads((tmp_path / 'pipeline-status.json').read_text(encoding='utf-8'))

    assert subscriptions
    assert added_handlers == [tracker.live_log_handler]
    assert removed_handlers == [tracker.live_log_handler]
    assert [json.loads(line)['event_type'] for line in event_lines] == [
        'run_started',
        'stage_started',
        'log_message',
        'result_accepted',
        'run_finished',
    ]
    assert json.loads(event_lines[1])['task_name'] == 'hifv_importdata'
    assert json.loads(event_lines[2])['task_name'] == 'hifv_importdata'
    assert json.loads(event_lines[2])['severity'] == 'warning'
    assert json.loads(event_lines[2])['message'] == 'flagged something'
    assert json.loads(event_lines[2])['payload'] == {
        'levelno': status.logging.WARNING,
        'logger_name': 'pipeline.hifv.importdata',
    }
    assert running_snapshot['observatory'] == 'EVLA'
    assert running_snapshot['recipe_name'] == 'hifv_calimage'
    assert running_snapshot['current_task'] == 'hifv_importdata'
    assert running_snapshot['latest_warning_count'] == 1
    assert running_snapshot['latest_attention_count'] == 2
    assert snapshot['context_name'] == 'ctx-001'
    assert snapshot['state'] == 'completed'
    assert snapshot['final_disposition'] == 'success'
    assert snapshot['observatory'] == 'EVLA'
    assert snapshot['recipe_name'] == 'hifv_calimage'
    assert snapshot['latest_warning_count'] == 1
    assert snapshot['latest_attention_count'] == 2
    assert snapshot['current_stage'] is None
    assert snapshot['last_completed_stage'] == 3
    assert snapshot['source'] == 'runpipeline'


def test_status_tracker_writes_stage_stopped_and_run_stopped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    subscriptions: list[tuple[object, str]] = []
    monkeypatch.setattr(status.eventbus, 'subscribe', lambda fn, topic: subscriptions.append((fn, topic)))
    added_handlers: list[object] = []
    removed_handlers: list[object] = []
    monkeypatch.setattr(status.logging, 'add_handler', lambda handler: added_handlers.append(handler))
    monkeypatch.setattr(status.logging, 'remove_handler', lambda handler: removed_handlers.append(handler))
    monkeypatch.setattr(status, '_get_active_context', lambda: _status_context(name='ctx-stop'))

    tracker = status.PipelineStatusTracker('ctx-stop', str(tmp_path))
    tracker.on_context_lifecycle_event(ContextCreatedEvent(context_name='ctx-stop', output_dir=str(tmp_path)))
    tracker.on_task_lifecycle_event(TaskStartedEvent('ctx-stop', 4, task_name='hifa_mocktask'))
    tracker.on_task_lifecycle_event(
        TaskStoppedEvent(
            'ctx-stop',
            4,
            task_name='hifa_mocktask',
            reason_code='operator_requested_stop',
            message='operator requested stop',
        )
    )
    tracker.on_run_lifecycle_event(
        RunStoppedEvent(
            context_name='ctx-stop',
            output_dir=str(tmp_path),
            exit_code=int(exceptions.PipelineExitCode.STOPPED),
            reason_code='operator_requested_stop',
            message='operator requested stop',
            source='runpipeline',
        )
    )

    event_lines = (tmp_path / 'pipeline-events.jsonl').read_text(encoding='utf-8').strip().splitlines()
    snapshot = json.loads((tmp_path / 'pipeline-status.json').read_text(encoding='utf-8'))

    assert subscriptions
    assert added_handlers == [tracker.live_log_handler]
    assert removed_handlers == [tracker.live_log_handler]
    assert [json.loads(line)['event_type'] for line in event_lines] == [
        'run_started',
        'stage_started',
        'stage_stopped',
        'run_stopped',
    ]
    assert json.loads(event_lines[2])['state'] == 'stopped'
    assert json.loads(event_lines[2])['reason_code'] == 'operator_requested_stop'
    assert json.loads(event_lines[2])['message'] == 'operator requested stop'
    assert snapshot['state'] == 'stopped'
    assert snapshot['final_disposition'] == 'clean_stop'
    assert snapshot['reason_code'] == 'operator_requested_stop'
    assert snapshot['message'] == 'operator requested stop'
    assert snapshot['source'] == 'runpipeline'


def test_publish_terminal_exception_writes_adhoc_status(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(status, '_get_active_context', lambda: None)

    status.publish_terminal_exception(
        exceptions.PipelineRequestError('bad request', reason_code='bad_request'),
        request_path=str(tmp_path / 'request.xml'),
        source='runpipeline',
    )

    event_record = json.loads((tmp_path / 'pipeline-events.jsonl').read_text(encoding='utf-8').strip())
    snapshot = json.loads((tmp_path / 'pipeline-status.json').read_text(encoding='utf-8'))

    assert event_record['event_type'] == 'run_failed'
    assert event_record['reason_code'] == 'bad_request'
    assert snapshot['context_name'] == 'request'
    assert snapshot['state'] == 'failed'
    assert snapshot['final_disposition'] == 'invalid_request'
    assert snapshot['reason_code'] == 'bad_request'


def test_live_log_handler_publishes_elevated_messages_with_current_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    subscriptions: list[tuple[object, str]] = []
    monkeypatch.setattr(status.eventbus, 'subscribe', lambda fn, topic: subscriptions.append((fn, topic)))
    tracker = status.PipelineStatusTracker('ctx-live', '.')
    tracker.snapshot['current_stage'] = 5
    tracker.snapshot['current_task'] = 'hifa_mocktask'

    published: list[LogMessageEvent] = []
    monkeypatch.setattr(status.eventbus, 'send_message', lambda event: published.append(event))

    tracker.live_log_handler.emit(
        SimpleNamespace(
            levelno=status.logging.ATTENTION,
            name='pipeline.task',
            getMessage=lambda: 'pay attention',
        )
    )
    tracker.live_log_handler.emit(
        SimpleNamespace(
            levelno=status.logging.INFO,
            name='pipeline.task',
            getMessage=lambda: 'ignore me',
        )
    )

    assert subscriptions
    assert len(published) == 1
    assert published[0].severity == 'attention'
    assert published[0].message == 'pay attention'
    assert published[0].stage_number == 5
    assert published[0].task_name == 'hifa_mocktask'


def test_standard_task_execute_emits_stage_stopped_and_reraises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    class DummyInputs:
        def __init__(self, context: SimpleNamespace) -> None:
            self.context = context
            self.vis = 'uid___A002_X1'
            self._pipeline_casa_task = None

        def as_dict(self) -> dict[str, object]:
            return {}

    class DummyStopTask(basetask.StandardTaskTemplate):
        Inputs = DummyInputs

        def prepare(self, **parameters):
            raise exceptions.PipelineStopRequested(
                'operator requested stop',
                reason_code='operator_requested_stop',
            )

        def analyse(self, result):
            return result

    casa_log = tmp_path / 'casa.log'
    casa_log.write_text('', encoding='utf-8')
    monkeypatch.setattr(basetask.utils, 'is_top_level_task', lambda: True)
    monkeypatch.setattr(basetask.utils, 'pickle_copy', lambda value: value)
    monkeypatch.setattr(basetask, '_log_task', lambda task: None)
    monkeypatch.setattr(basetask.logging, 'add_handler', lambda handler: None)
    monkeypatch.setattr(basetask.logging, 'remove_handler', lambda handler: None)
    monkeypatch.setattr(basetask.casa_tools.log, 'logfile', lambda: str(casa_log))
    monkeypatch.setattr(basetask, 'Executor', lambda context: object())
    monkeypatch.setattr(basetask, 'CasaTasks', lambda executor: object())

    published = []
    monkeypatch.setattr(basetask.eventbus, 'send_message', lambda event: published.append(event))

    context = SimpleNamespace(name='ctx-stop', task_counter=0, subtask_counter=0)
    task = DummyStopTask(DummyInputs(context))

    with pytest.raises(exceptions.PipelineStopRequested) as exc_info:
        task.execute()

    assert exc_info.value.reason_code == 'operator_requested_stop'
    assert [event.__class__.__name__ for event in published] == ['TaskStartedEvent', 'TaskStoppedEvent']
    assert published[1].task_name == 'DummyStopTask'
    assert published[1].reason_code == 'operator_requested_stop'


def test_standard_task_execute_uses_base_context_for_container_stop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    class DummyInputs:
        pass

    class DummyStopTask(basetask.StandardTaskTemplate):
        Inputs = DummyInputs
        is_multi_vis_task = True

        def prepare(self, **parameters):
            raise exceptions.PipelineStopRequested(
                'operator requested stop',
                reason_code='operator_requested_stop',
            )

        def analyse(self, result):
            return result

    class DummyContainer:
        def __init__(self, context: SimpleNamespace) -> None:
            self._context = context
            self.context = [context, context]
            self.vis = ['uid___A002_X1', 'uid___A002_X2']
            self._pipeline_casa_task = None
            self._task_cls = SimpleNamespace(Inputs=DummyInputs)

    monkeypatch.setattr(basetask.vdp, 'InputsContainer', DummyContainer)

    casa_log = tmp_path / 'casa.log'
    casa_log.write_text('', encoding='utf-8')
    monkeypatch.setattr(basetask.utils, 'is_top_level_task', lambda: True)
    monkeypatch.setattr(basetask.utils, 'pickle_copy', lambda value: value)
    monkeypatch.setattr(basetask, '_log_task', lambda task: None)
    monkeypatch.setattr(basetask.logging, 'add_handler', lambda handler: None)
    monkeypatch.setattr(basetask.logging, 'remove_handler', lambda handler: None)
    monkeypatch.setattr(basetask.casa_tools.log, 'logfile', lambda: str(casa_log))
    monkeypatch.setattr(basetask, 'Executor', lambda context: object())
    monkeypatch.setattr(basetask, 'CasaTasks', lambda executor: object())

    published = []
    monkeypatch.setattr(basetask.eventbus, 'send_message', lambda event: published.append(event))

    context = SimpleNamespace(name='ctx-container-stop', task_counter=0, subtask_counter=0)
    task = DummyStopTask(DummyContainer(context))

    with pytest.raises(exceptions.PipelineStopRequested) as exc_info:
        task.execute()

    assert exc_info.value.reason_code == 'operator_requested_stop'
    assert context.task_counter == 1
    assert [event.__class__.__name__ for event in published] == ['TaskStartedEvent', 'TaskStoppedEvent']


def test_get_weblog_results_includes_synthetic_stopped_stage(tmp_path: Path) -> None:
    events_path = tmp_path / 'pipeline-events.jsonl'
    events_path.write_text(
        json.dumps(
            {
                'event_type': 'stage_stopped',
                'stage_number': 4,
                'task_name': 'hifa_mocktask',
                'reason_code': 'operator_requested_stop',
                'message': 'operator requested stop',
            }
        ) + '\n',
        encoding='utf-8',
    )
    context = SimpleNamespace(
        output_dir=str(tmp_path),
        results=[SimpleNamespace(stage_number=3)],
    )

    results = htmlrenderer.get_weblog_results(context)

    assert len(results) == 2
    stopped_result = results[1]
    assert isinstance(stopped_result, basetask.StoppedTaskResults)
    assert stopped_result.stage_number == 4
    assert stopped_result.taskname == 'hifa_mocktask'
    assert stopped_result.reason_code == 'operator_requested_stop'
    assert stopped_result.message == 'operator requested stop'


def test_load_pipeline_status_snapshot_reads_snapshot(tmp_path: Path) -> None:
    snapshot = {
        'state': 'stopped',
        'final_disposition': 'clean_stop',
        'reason_code': 'operator_requested_stop',
        'message': 'operator requested stop',
        'conditions': [],
    }
    (tmp_path / 'pipeline-status.json').write_text(json.dumps(snapshot), encoding='utf-8')

    loaded = htmlrenderer._load_pipeline_status_snapshot(SimpleNamespace(output_dir=str(tmp_path)))

    assert loaded == snapshot


def test_get_weblog_run_status_reports_clean_stop(tmp_path: Path) -> None:
    snapshot = {
        'state': 'stopped',
        'final_disposition': 'clean_stop',
        'reason_code': 'operator_requested_stop',
        'message': 'operator requested stop',
        'conditions': [],
    }
    (tmp_path / 'pipeline-status.json').write_text(json.dumps(snapshot), encoding='utf-8')

    run_status = htmlrenderer.get_weblog_run_status(SimpleNamespace(output_dir=str(tmp_path)))

    assert run_status == {
        'title': 'Run stopped intentionally',
        'alert_class': 'info alert-info',
        'message': 'operator requested stop',
        'reason_code': 'operator_requested_stop',
    }


def test_get_active_conditions_for_weblog_prefers_snapshot_over_context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    snapshot = {
        'state': 'completed',
        'final_disposition': 'success',
        'conditions': [{'code': 'from_snapshot', 'severity': 'warning', 'scope': 'stage', 'message': 'snapshot condition'}],
    }
    (tmp_path / 'pipeline-status.json').write_text(json.dumps(snapshot), encoding='utf-8')
    context, _ = _condition_context(monkeypatch, tmp_path, name='ctx-renderer-condition')
    context.set_condition(
        pipeline_conditions.CONDITION_CODE_CLEAN_LIST_INFO,
        severity='info',
        scope='stage',
        disposition='continue',
        message='context condition',
        details={'msg': 'context condition'},
    )

    conditions = htmlrenderer.get_active_conditions_for_weblog(context)

    assert conditions == snapshot['conditions']


def test_stopped_task_weblog_helpers_label_stage_distinctly() -> None:
    stopped_result = basetask.StoppedTaskResults(
        None,
        taskname='hifa_mocktask',
        stage_number=7,
        reason_code='operator_requested_stop',
        message='operator requested stop',
    )
    stopped_result.qa = SimpleNamespace(representative=SimpleNamespace(score=None), pool=[])
    stopped_result.logrecords = []

    task_name = htmlrenderer.get_task_name(stopped_result)
    task_description = htmlrenderer.get_task_description(stopped_result, SimpleNamespace())
    symbol_badge = rendererutils.get_symbol_badge(stopped_result)

    assert task_name == '7. hifa_mocktask (stopped)'
    assert task_description == "7. <strong>hifa_mocktask (stopped)</strong>: 'hifa_mocktask'"
    assert 'glyphicon-pause' in symbol_badge


def test_stopped_task_detail_renderer_tolerates_missing_timestamps(tmp_path: Path) -> None:
    stopped_result = basetask.StoppedTaskResults(
        None,
        taskname='hifa_mocktask',
        stage_number=7,
        reason_code='operator_requested_stop',
        message='operator requested stop',
    )
    stopped_result.inputs = {}
    stopped_result.timestamps = SimpleNamespace(start=None, end=None)

    context = SimpleNamespace(
        report_dir=str(tmp_path),
        observing_run=SimpleNamespace(measurement_sets=[]),
    )
    renderer = basetemplates.T2_4MDetailsStoppedTaskRenderer()

    rendered = renderer.render(context, stopped_result)

    assert 'Stop message:' in rendered
    assert 'operator requested stop' in rendered
    assert 'N/A' in rendered


def test_context_condition_registry_tracks_active_conditions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    context, published = _condition_context(monkeypatch, tmp_path)
    published.clear()

    context.set_condition(
        pipeline_conditions.CONDITION_CODE_CLEAN_LIST_INFO,
        severity='info',
        scope='stage',
        disposition='continue',
        message='No imaging targets were created.',
        details={'msg': 'No imaging targets were created.'},
    )

    active_condition = context.get_condition(pipeline_conditions.CONDITION_CODE_CLEAN_LIST_INFO)

    assert active_condition is not None
    assert active_condition.active is True
    assert active_condition.message == 'No imaging targets were created.'
    assert len(context.get_conditions()) == 1
    assert isinstance(published[0], ConditionRaisedEvent)

    context.clear_condition(pipeline_conditions.CONDITION_CODE_CLEAN_LIST_INFO)

    cleared_condition = context.get_condition(
        pipeline_conditions.CONDITION_CODE_CLEAN_LIST_INFO,
        active_only=False,
    )

    assert context.get_condition(pipeline_conditions.CONDITION_CODE_CLEAN_LIST_INFO) is None
    assert cleared_condition is not None
    assert cleared_condition.active is False
    assert isinstance(published[1], ConditionClearedEvent)


def test_condition_helpers_prefer_registry_over_legacy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    context, _ = _condition_context(monkeypatch, tmp_path)
    context.size_mitigation_parameters = {'status': 'OK', 'field': 'legacy-field'}
    context.clean_list_info = {'msg': 'legacy message'}
    context.imaging_parameters = {'robust': 0.5, 'uvtaper': ['legacy taper']}

    context.set_condition(
        pipeline_conditions.CONDITION_CODE_SIZE_MITIGATION,
        severity='error',
        scope='run',
        disposition='skip_stage',
        message='registry mitigation error',
        details={'status': 'ERROR', 'field': 'registry-field'},
    )
    context.set_condition(
        pipeline_conditions.CONDITION_CODE_CLEAN_LIST_INFO,
        severity='info',
        scope='stage',
        disposition='continue',
        message='registry message',
        details={'msg': 'registry message'},
    )
    context.set_condition(
        pipeline_conditions.CONDITION_CODE_IMAGING_PARAMETER_OVERRIDE,
        severity='info',
        scope='run',
        disposition='continue',
        message='registry imaging parameters',
        details={'robust': 2.0, 'uvtaper': ['registry taper']},
    )
    context.set_condition(
        pipeline_conditions.CONDITION_CODE_CONTINUUM_SELECTION_WARNING,
        severity='warning',
        scope='stage',
        disposition='continue',
        message='registry continuum warning',
        details={
            'warning_count': 1,
            'warnings': [{'field': 'target-a', 'spw': '3', 'message': 'registry warning'}],
        },
    )

    assert pipeline_conditions.get_size_mitigation_parameters(context)['field'] == 'registry-field'
    assert pipeline_conditions.has_size_mitigation_error(context) is True
    assert pipeline_conditions.get_clean_list_info(context)['msg'] == 'registry message'
    assert pipeline_conditions.get_imaging_parameter(context, 'robust') == 2.0
    assert pipeline_conditions.get_imaging_parameter_overrides(context)['uvtaper'] == ['registry taper']
    assert pipeline_conditions.get_continuum_selection_warnings(context)[0]['message'] == 'registry warning'


def test_imageprecheck_result_merge_with_context_publishes_imaging_parameter_condition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context, _ = _condition_context(monkeypatch, tmp_path, name='ctx-imageprecheck')
    context.imaging_parameters = {'uvtaper': ['legacy taper']}
    context.per_spw_cont_sensitivities_all_chan = {}
    context.synthesized_beams = {}

    result = imageprecheck.ImagePreCheckResults(hm_robust=2.0, hm_uvtaper=['10klambda'])

    result.merge_with_context(context)

    imaging_parameter_condition = context.get_condition(
        pipeline_conditions.CONDITION_CODE_IMAGING_PARAMETER_OVERRIDE
    )

    assert context.imaging_parameters == {'robust': 2.0, 'uvtaper': ['10klambda']}
    assert imaging_parameter_condition is not None
    assert imaging_parameter_condition.scope == 'run'
    assert imaging_parameter_condition.details == {'robust': 2.0, 'uvtaper': ['10klambda']}


def test_findcont_result_merge_with_context_publishes_continuum_warning_condition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context, _ = _condition_context(monkeypatch, tmp_path, name='ctx-findcont')
    context.contfile = str(tmp_path / 'cont.dat')
    context.clean_list_pending = []

    writes: list[object] = []

    class DummyContFileHandler:
        def __init__(self, path: str) -> None:
            self.path = path

        def write(self, payload: object) -> None:
            writes.append(payload)

    monkeypatch.setattr(findcont_resultobjects.contfilehandler, 'ContFileHandler', DummyContFileHandler)

    result = findcont_resultobjects.FindContResult(
        {},
        {'fields': {}},
        {},
        0,
        0,
        [],
        {},
        warning_details={
            'target-a': {
                '3': [
                    {
                        'category': 'heuristic_warning',
                        'field': 'target-a',
                        'spw': '3',
                        'message': 'line contamination may affect the continuum estimate',
                    }
                ]
            }
        },
    )
    result.inputs = {'target_list': []}

    result.merge_with_context(context)

    warning_condition = context.get_condition(pipeline_conditions.CONDITION_CODE_CONTINUUM_SELECTION_WARNING)

    assert writes == [{'fields': {}}]
    assert warning_condition is not None
    assert warning_condition.severity == 'warning'
    assert warning_condition.details['warning_count'] == 1
    assert warning_condition.details['warnings'][0]['field'] == 'target-a'


def test_findcont_result_merge_with_context_clears_continuum_warning_condition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context, _ = _condition_context(monkeypatch, tmp_path, name='ctx-findcont-clear')
    context.contfile = str(tmp_path / 'cont.dat')
    context.clean_list_pending = []
    context.set_condition(
        pipeline_conditions.CONDITION_CODE_CONTINUUM_SELECTION_WARNING,
        severity='warning',
        scope='stage',
        disposition='continue',
        message='stale warning',
        details={'warning_count': 1, 'warnings': [{'message': 'stale warning'}]},
    )

    class DummyContFileHandler:
        def __init__(self, path: str) -> None:
            self.path = path

        def write(self, payload: object) -> None:
            return None

    monkeypatch.setattr(findcont_resultobjects.contfilehandler, 'ContFileHandler', DummyContFileHandler)

    result = findcont_resultobjects.FindContResult({}, {'fields': {}}, {}, 0, 0, [], {})
    result.inputs = {'target_list': []}

    result.merge_with_context(context)

    assert context.get_condition(pipeline_conditions.CONDITION_CODE_CONTINUUM_SELECTION_WARNING) is None


def test_status_tracker_writes_condition_events_and_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    subscriptions: list[tuple[object, str]] = []
    monkeypatch.setattr(status.eventbus, 'subscribe', lambda fn, topic: subscriptions.append((fn, topic)))
    monkeypatch.setattr(status.logging, 'add_handler', lambda handler: None)
    monkeypatch.setattr(status.logging, 'remove_handler', lambda handler: None)
    context, published = _condition_context(monkeypatch, tmp_path, name='ctx-condition-status')
    monkeypatch.setattr(status, '_get_active_context', lambda: context)

    tracker = status.PipelineStatusTracker('ctx-condition-status', str(tmp_path))
    tracker.on_context_lifecycle_event(ContextCreatedEvent(context_name='ctx-condition-status', output_dir=str(tmp_path)))

    published.clear()
    context.set_condition(
        pipeline_conditions.CONDITION_CODE_SIZE_MITIGATION,
        severity='warning',
        scope='run',
        disposition='continue',
        message='Size had to be mitigated.',
        details={'status': 'MITIGATED', 'field': 'target-a'},
    )
    tracker.on_condition_lifecycle_event(published[-1])

    condition_snapshot = json.loads((tmp_path / 'pipeline-status.json').read_text(encoding='utf-8'))

    context.clear_condition(pipeline_conditions.CONDITION_CODE_SIZE_MITIGATION)
    tracker.on_condition_lifecycle_event(published[-1])

    event_lines = (tmp_path / 'pipeline-events.jsonl').read_text(encoding='utf-8').strip().splitlines()
    final_snapshot = json.loads((tmp_path / 'pipeline-status.json').read_text(encoding='utf-8'))

    assert subscriptions
    assert [json.loads(line)['event_type'] for line in event_lines] == [
        'run_started',
        'condition_raised',
        'condition_cleared',
    ]
    assert condition_snapshot['conditions'][0]['code'] == pipeline_conditions.CONDITION_CODE_SIZE_MITIGATION
    assert condition_snapshot['conditions'][0]['details']['field'] == 'target-a'
    assert final_snapshot['conditions'] == []


def test_checkproductsize_result_merge_with_context_updates_condition_registry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context, _ = _condition_context(monkeypatch, tmp_path, name='ctx-checkproductsize')

    mitigated_result = checkproductsize_resultobjects.CheckProductSizeResult(
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        {'status': 'MITIGATED', 'field': 'target-a'},
        'MITIGATED',
        {'longmsg': 'Size had to be mitigated.'},
        None,
    )

    mitigated_result.merge_with_context(context)

    mitigation_condition = context.get_condition(pipeline_conditions.CONDITION_CODE_SIZE_MITIGATION)

    assert mitigation_condition is not None
    assert mitigation_condition.severity == 'warning'
    assert mitigation_condition.details['field'] == 'target-a'

    ok_result = checkproductsize_resultobjects.CheckProductSizeResult(
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        1.0,
        {'status': 'OK'},
        'OK',
        {'longmsg': 'No mitigation required.'},
        None,
    )

    ok_result.merge_with_context(context)

    assert context.get_condition(pipeline_conditions.CONDITION_CODE_SIZE_MITIGATION) is None


def test_makeimlist_result_merge_with_context_publishes_clean_list_condition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context, _ = _condition_context(monkeypatch, tmp_path, name='ctx-makeimlist')
    result = makeimlist_resultobjects.MakeImListResult()
    result.set_info(
        {
            'msg': 'No data found. No imaging targets were created.',
            'intent': 'TARGET',
            'specmode': 'cube',
            'stokes': 'I',
        }
    )

    result.merge_with_context(context)

    clean_list_condition = context.get_condition(pipeline_conditions.CONDITION_CODE_CLEAN_LIST_INFO)

    assert clean_list_condition is not None
    assert clean_list_condition.message == 'No data found. No imaging targets were created.'
    assert pipeline_conditions.get_clean_list_info(context)['intent'] == 'TARGET'


def test_makeimages_result_merge_with_context_clears_clean_list_condition(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    context, _ = _condition_context(monkeypatch, tmp_path, name='ctx-makeimages')
    context.clean_list_pending = [{}]
    context.clean_list_info = {'msg': 'No data found. No imaging targets were created.'}
    context.set_condition(
        pipeline_conditions.CONDITION_CODE_CLEAN_LIST_INFO,
        severity='info',
        scope='stage',
        disposition='continue',
        message=context.clean_list_info['msg'],
        details=context.clean_list_info,
    )

    result = makeimages_resultobjects.MakeImagesResult()
    result.inputs = {'target_list': []}
    result.results = []

    result.merge_with_context(context)

    assert context.clean_list_pending == []
    assert context.clean_list_info == {}
    assert context.get_condition(pipeline_conditions.CONDITION_CODE_CLEAN_LIST_INFO) is None