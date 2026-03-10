"""Structured pipeline run status publication."""

from __future__ import annotations

import json
import os
import logging as pylogging
from datetime import datetime, timezone
from pathlib import Path

from . import eventbus
from . import exceptions
from . import logging
from .eventbus import (
    ContextCreatedEvent,
    ContextLifecycleEvent,
    ContextResumedEvent,
    LogMessageEvent,
    ResultAcceptErrorEvent,
    ResultAcceptedEvent,
    ResultAcceptingEvent,
    ResultLifecycleEvent,
    RunCompletedEvent,
    RunFailedEvent,
    RunLifecycleEvent,
    RunStoppedEvent,
    TaskAbnormalExitEvent,
    TaskCompleteEvent,
    TaskLifecycleEvent,
    TaskStartedEvent,
    TaskStoppedEvent,
    WebLogLifecycleEvent,
    WebLogRenderingCompleteEvent,
    WebLogRenderingStartedEvent,
    WebLogStageLifecycleEvent,
    WebLogStageRenderingAbnormalExitEvent,
    WebLogStageRenderingCompleteEvent,
    WebLogStageRenderingStartedEvent,
)

LOG = logging.get_logger(__name__)

__all__ = [
    'status_publisher',
    'publish_active_context_completion',
    'publish_terminal_exception',
]

SCHEMA_VERSION = 1
EVENTS_FILENAME = 'pipeline-events.jsonl'
SNAPSHOT_FILENAME = 'pipeline-status.json'


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_timestamp(timestamp: datetime) -> str:
    return timestamp.isoformat().replace('+00:00', 'Z')


def _status_directory(output_dir: str | None) -> Path:
    return Path(output_dir or '.').resolve()


def _final_disposition_for_exit_code(exit_code: int | None) -> str | None:
    if exit_code == int(exceptions.PipelineExitCode.SUCCESS):
        return 'success'
    if exit_code == int(exceptions.PipelineExitCode.STOPPED):
        return 'clean_stop'
    if exit_code == int(exceptions.PipelineExitCode.INVALID_REQUEST):
        return 'invalid_request'
    if exit_code == int(exceptions.PipelineExitCode.TASK_FAILURE):
        return 'task_failure'
    if exit_code == int(exceptions.PipelineExitCode.INTERNAL_ERROR):
        return 'internal_error'
    return None


def _event_type_for_context_event(event: ContextLifecycleEvent) -> str:
    if isinstance(event, ContextResumedEvent):
        return 'run_resumed'
    return 'run_started'


def _event_type_for_task_event(event: TaskLifecycleEvent) -> str:
    if isinstance(event, TaskStartedEvent):
        return 'stage_started'
    if isinstance(event, TaskCompleteEvent):
        return 'stage_completed'
    if isinstance(event, TaskStoppedEvent):
        return 'stage_stopped'
    if isinstance(event, TaskAbnormalExitEvent):
        return 'stage_failed'
    raise ValueError(f'Unhandled task lifecycle event: {event.__class__.__name__}')


def _event_type_for_result_event(event: ResultLifecycleEvent) -> str:
    if isinstance(event, ResultAcceptingEvent):
        return 'result_accepting'
    if isinstance(event, ResultAcceptedEvent):
        return 'result_accepted'
    if isinstance(event, ResultAcceptErrorEvent):
        return 'result_error'
    raise ValueError(f'Unhandled result lifecycle event: {event.__class__.__name__}')


def _event_type_for_weblog_event(event: WebLogLifecycleEvent) -> str | None:
    if isinstance(event, WebLogStageRenderingStartedEvent):
        return 'weblog_stage_started'
    if isinstance(event, WebLogStageRenderingCompleteEvent):
        return 'weblog_stage_completed'
    if isinstance(event, WebLogStageRenderingAbnormalExitEvent):
        return 'weblog_stage_failed'
    return None


def _event_type_for_run_event(event: RunLifecycleEvent) -> str:
    if isinstance(event, RunCompletedEvent):
        return 'run_finished'
    if isinstance(event, RunStoppedEvent):
        return 'run_stopped'
    return 'run_failed'


def _severity_for_level(levelno: int | None) -> str | None:
    if levelno == logging.WARNING:
        return 'warning'
    if levelno == logging.ATTENTION:
        return 'attention'
    if levelno == logging.ERROR:
        return 'error'
    if levelno == logging.CRITICAL:
        return 'critical'
    return None


def _message_for_log_record(record: pylogging.LogRecord) -> str:
    try:
        message = record.getMessage()
    except Exception:
        message = getattr(record, 'msg', record.__class__.__name__)
    return str(message)


def _default_snapshot(context_name: str, output_dir: str) -> dict[str, object]:
    return {
        'schema_version': SCHEMA_VERSION,
        'run_id': context_name,
        'context_name': context_name,
        'observatory': 'unknown',
        'recipe_name': None,
        'state': 'initializing',
        'final_disposition': None,
        'reason_code': None,
        'message': None,
        'start_time': None,
        'end_time': None,
        'current_stage': None,
        'current_task': None,
        'latest_warning_count': 0,
        'latest_attention_count': 0,
        'conditions': [],
        'output_dir': output_dir,
    }


def _get_context_attribute(context: object, *attribute_path: str) -> object | None:
    value = context
    for attribute_name in attribute_path:
        value = getattr(value, attribute_name, None)
        if value is None:
            return None
    return value


def _get_context_recipe_name(context: object) -> str | None:
    get_recipe_name = getattr(context, 'get_recipe_name', None)
    if callable(get_recipe_name):
        recipe_name = get_recipe_name()
        if recipe_name:
            return recipe_name

    recipe_name = _get_context_attribute(context, 'project_structure', 'recipe_name')
    if isinstance(recipe_name, str) and recipe_name and recipe_name != 'Undefined':
        return recipe_name
    return None


def _get_context_observatory(context: object) -> str:
    telescope = _get_context_attribute(context, 'project_summary', 'telescope')
    if isinstance(telescope, str) and telescope:
        return telescope

    observatory = _get_context_attribute(context, 'project_summary', 'observatory')
    if isinstance(observatory, str) and observatory:
        return observatory
    return 'unknown'


def _get_latest_task_name(context: object) -> str | None:
    results = getattr(context, 'results', None)
    if not results:
        return None

    last_result = results[-1]
    for attribute_name in ('taskname', 'pipeline_casa_task'):
        task_name = getattr(last_result, attribute_name, None)
        if isinstance(task_name, str) and task_name:
            return task_name
    return None


def _snapshot_details_from_context(context: object) -> dict[str, object]:
    details: dict[str, object] = {
        'observatory': _get_context_observatory(context),
        'recipe_name': _get_context_recipe_name(context),
    }
    current_task = _get_latest_task_name(context)
    if current_task is not None:
        details['current_task'] = current_task
    return details


def _log_level_counts(result: object | None) -> dict[str, int]:
    if result is None:
        return {
            'latest_warning_count': 0,
            'latest_attention_count': 0,
        }

    def _iter_logrecords(value: object) -> list[object]:
        try:
            iterator = iter(value)
        except TypeError:
            return list(getattr(value, 'logrecords', []))

        records: list[object] = []
        for item in iterator:
            records.extend(_iter_logrecords(item))
        return records

    logrecords = _iter_logrecords(result)

    return {
        'latest_warning_count': len([record for record in logrecords if getattr(record, 'levelno', None) == logging.WARNING]),
        'latest_attention_count': len([record for record in logrecords if getattr(record, 'levelno', None) == logging.ATTENTION]),
    }


def _get_latest_result(context: object) -> object | None:
    results = getattr(context, 'results', None)
    if not results:
        return None
    return results[-1]


def _append_event(path: Path, event_record: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as event_file:
        event_file.write(json.dumps(event_record, sort_keys=True))
        event_file.write('\n')


def _write_snapshot(path: Path, snapshot: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f'{path.suffix}.tmp')
    with temp_path.open('w', encoding='utf-8') as snapshot_file:
        json.dump(snapshot, snapshot_file, sort_keys=True, indent=4, separators=(',', ': '))
        snapshot_file.write('\n')
    os.replace(temp_path, path)


class PipelineStatusTracker:
    """Track run lifecycle updates and publish structured status artifacts."""

    def __init__(self, context_name: str, output_dir: str) -> None:
        self.context_name = context_name
        self.output_dir = str(_status_directory(output_dir))
        base_dir = Path(self.output_dir)
        self.events_path = base_dir / EVENTS_FILENAME
        self.snapshot_path = base_dir / SNAPSHOT_FILENAME
        self.snapshot = _default_snapshot(context_name=context_name, output_dir=self.output_dir)
        self.live_log_handler = _LiveStatusLogHandler(self)
        self._live_log_handler_attached = False
        eventbus.subscribe(self.on_task_lifecycle_event, TaskLifecycleEvent.topic)
        eventbus.subscribe(self.on_result_lifecycle_event, ResultLifecycleEvent.topic)
        eventbus.subscribe(self.on_log_message_event, LogMessageEvent.topic)
        eventbus.subscribe(self.on_weblog_lifecycle_event, WebLogLifecycleEvent.topic)
        eventbus.subscribe(self.on_run_lifecycle_event, RunLifecycleEvent.topic)

    def _attach_live_log_handler(self) -> None:
        if self._live_log_handler_attached:
            return
        logging.add_handler(self.live_log_handler)
        self._live_log_handler_attached = True

    def _detach_live_log_handler(self) -> None:
        if not self._live_log_handler_attached:
            return
        logging.remove_handler(self.live_log_handler)
        self._live_log_handler_attached = False

    def _update_snapshot_from_context(self) -> None:
        context = _get_active_context()
        if context is None or getattr(context, 'name', None) != self.context_name:
            return

        self.snapshot.update(_snapshot_details_from_context(context))

    def _record_event(self, event_type: str, timestamp: datetime, **extra: object) -> None:
        event_record = {
            'schema_version': SCHEMA_VERSION,
            'timestamp': _format_timestamp(timestamp),
            'run_id': self.snapshot['run_id'],
            'context_name': self.context_name,
            'event_type': event_type,
            'state': self.snapshot['state'],
            'stage_number': None,
            'task_name': self.snapshot['current_task'],
            'severity': None,
            'reason_code': self.snapshot['reason_code'],
            'message': self.snapshot['message'],
            'exception_type': None,
            'traceback_excerpt': None,
            'payload': None,
        }
        event_record.update(extra)
        _append_event(self.events_path, event_record)

    def _update_snapshot(self, timestamp: datetime, **changes: object) -> None:
        self.snapshot.update(changes)
        self._update_snapshot_from_context()
        if self.snapshot['start_time'] is None:
            self.snapshot['start_time'] = _format_timestamp(timestamp)
        _write_snapshot(self.snapshot_path, self.snapshot)

    def on_context_lifecycle_event(self, event: ContextLifecycleEvent) -> None:
        if event.context_name != self.context_name:
            return

        self._attach_live_log_handler()
        timestamp = _utc_now()
        state = 'running' if isinstance(event, ContextResumedEvent) else 'initializing'
        self._update_snapshot(timestamp, state=state, end_time=None)
        self._record_event(
            _event_type_for_context_event(event),
            timestamp,
            state=state,
            reason_code=None,
            message=None,
        )
        if state == 'initializing':
            self._update_snapshot(timestamp, state='running')

    def on_task_lifecycle_event(self, event: TaskLifecycleEvent) -> None:
        if event.context_name != self.context_name:
            return

        timestamp = _utc_now()
        event_type = _event_type_for_task_event(event)
        state = 'running'
        final_disposition = self.snapshot['final_disposition']
        if isinstance(event, TaskStoppedEvent):
            state = 'stopped'
            final_disposition = 'clean_stop'
        elif isinstance(event, TaskAbnormalExitEvent):
            state = 'failed'
            final_disposition = 'task_failure'
        changes: dict[str, object] = {
            'state': state,
            'current_stage': event.stage_number,
            'current_task': event.task_name,
            'final_disposition': final_disposition,
            'reason_code': event.reason_code,
            'message': event.message,
        }
        if isinstance(event, TaskCompleteEvent):
            changes['last_completed_stage'] = event.stage_number
        self._update_snapshot(timestamp, **changes)
        self._record_event(
            event_type,
            timestamp,
            state=state,
            stage_number=event.stage_number,
            task_name=event.task_name,
            reason_code=event.reason_code,
            message=event.message,
        )

    def on_result_lifecycle_event(self, event: ResultLifecycleEvent) -> None:
        if event.context_name != self.context_name:
            return

        timestamp = _utc_now()
        event_type = _event_type_for_result_event(event)
        counts = {
            'latest_warning_count': self.snapshot['latest_warning_count'],
            'latest_attention_count': self.snapshot['latest_attention_count'],
        }
        context = _get_active_context()
        if context is not None and getattr(context, 'name', None) == self.context_name:
            counts = _log_level_counts(_get_latest_result(context))
        changes: dict[str, object] = {
            'state': 'running',
            'current_stage': event.stage_number,
            'current_task': event.task_name or self.snapshot['current_task'],
        }
        changes.update(counts)
        if isinstance(event, ResultAcceptedEvent):
            changes['last_completed_stage'] = event.stage_number
        self._update_snapshot(timestamp, **changes)
        self._record_event(
            event_type,
            timestamp,
            state='running',
            stage_number=event.stage_number,
            task_name=event.task_name or self.snapshot['current_task'],
            payload=counts,
        )

    def on_weblog_lifecycle_event(self, event: WebLogLifecycleEvent) -> None:
        if event.context_name != self.context_name:
            return

        event_type = _event_type_for_weblog_event(event)
        if event_type is None:
            return

        timestamp = _utc_now()
        changes: dict[str, object] = {
            'state': self.snapshot['state'],
            'weblog_state': event.state,
        }
        if isinstance(event, WebLogStageLifecycleEvent):
            changes['weblog_stage'] = event.stage_number
        self._update_snapshot(timestamp, **changes)
        self._record_event(
            event_type,
            timestamp,
            stage_number=getattr(event, 'stage_number', None),
        )

    def on_log_message_event(self, event: LogMessageEvent) -> None:
        if event.context_name != self.context_name:
            return

        timestamp = _utc_now()
        self._record_event(
            'log_message',
            timestamp,
            state=self.snapshot['state'],
            stage_number=event.stage_number,
            task_name=event.task_name,
            severity=event.severity,
            message=event.message,
            payload={
                'levelno': event.levelno,
                'logger_name': event.logger_name,
            },
        )

    def on_run_lifecycle_event(self, event: RunLifecycleEvent) -> None:
        if event.context_name != self.context_name:
            return

        timestamp = _utc_now()
        final_disposition = _final_disposition_for_exit_code(event.exit_code)
        changes = {
            'state': event.state,
            'final_disposition': final_disposition,
            'reason_code': event.reason_code,
            'message': event.message,
            'end_time': _format_timestamp(timestamp),
            'exit_code': event.exit_code,
            'source': event.source,
            'current_stage': None,
            'current_task': None,
        }
        self._update_snapshot(timestamp, **changes)
        self._record_event(
            _event_type_for_run_event(event),
            timestamp,
            state=event.state,
            reason_code=event.reason_code,
            message=event.message,
            exception_type=None,
            payload={'exit_code': event.exit_code, 'source': event.source},
        )
        self._detach_live_log_handler()


class _LiveStatusLogHandler(pylogging.Handler):
    """Bridge elevated log records into structured status events as they occur."""

    def __init__(self, tracker: PipelineStatusTracker) -> None:
        super().__init__(level=logging.ATTENTION)
        self._tracker = tracker

    def emit(self, record: pylogging.LogRecord) -> None:
        severity = _severity_for_level(getattr(record, 'levelno', None))
        if severity is None:
            return

        eventbus.send_message(
            LogMessageEvent(
                context_name=self._tracker.context_name,
                stage_number=self._tracker.snapshot['current_stage'],
                task_name=self._tracker.snapshot['current_task'],
                severity=severity,
                message=_message_for_log_record(record),
                levelno=getattr(record, 'levelno', None),
                logger_name=getattr(record, 'name', None),
            )
        )


class ContextStatusPublisher:
    """Create per-context status trackers when a context is created or resumed."""

    def __init__(self) -> None:
        self.tracking: dict[str, PipelineStatusTracker] = {}
        eventbus.subscribe(self.track, ContextCreatedEvent.topic)
        eventbus.subscribe(self.track, ContextResumedEvent.topic)

    def track(self, event: ContextLifecycleEvent) -> None:
        tracker = self.tracking.get(event.context_name)
        if tracker is None:
            tracker = PipelineStatusTracker(context_name=event.context_name, output_dir=event.output_dir)
            self.tracking[event.context_name] = tracker
        tracker.on_context_lifecycle_event(event)


def _get_active_context() -> object | None:
    try:
        from pipeline.h.cli import cli
    except Exception:
        return None

    pipeline_instance = cli.stack.get(cli.PIPELINE_NAME)
    if pipeline_instance is None:
        return None
    return getattr(pipeline_instance, 'context', None)


def _request_context_name(request_path: str | None) -> str:
    if request_path:
        return Path(request_path).stem or 'pipeline-run'
    return 'pipeline-run'


def _request_output_dir(request_path: str | None) -> str:
    if request_path:
        return str(Path(request_path).resolve().parent)
    return str(Path.cwd())


def _publish_terminal_event(
    *,
    context_name: str,
    output_dir: str,
    exit_code: int,
    reason_code: str | None,
    message: str | None,
    source: str,
) -> None:
    if exit_code == int(exceptions.PipelineExitCode.SUCCESS):
        eventbus.send_message(RunCompletedEvent(context_name=context_name, output_dir=output_dir, source=source))
        return
    if exit_code == int(exceptions.PipelineExitCode.STOPPED):
        eventbus.send_message(
            RunStoppedEvent(
                context_name=context_name,
                output_dir=output_dir,
                exit_code=exit_code,
                reason_code=reason_code,
                message=message,
                source=source,
            )
        )
        return
    eventbus.send_message(
        RunFailedEvent(
            context_name=context_name,
            output_dir=output_dir,
            exit_code=exit_code,
            reason_code=reason_code,
            message=message,
            source=source,
        )
    )


def _write_adhoc_terminal_status(
    *,
    context_name: str,
    output_dir: str,
    exit_code: int,
    reason_code: str | None,
    message: str | None,
    source: str,
) -> None:
    timestamp = _utc_now()
    snapshot = _default_snapshot(context_name=context_name, output_dir=str(_status_directory(output_dir)))
    state = 'completed' if exit_code == int(exceptions.PipelineExitCode.SUCCESS) else 'failed'
    if exit_code == int(exceptions.PipelineExitCode.STOPPED):
        state = 'stopped'
    snapshot.update(
        {
            'state': state,
            'final_disposition': _final_disposition_for_exit_code(exit_code),
            'reason_code': reason_code,
            'message': message,
            'start_time': _format_timestamp(timestamp),
            'end_time': _format_timestamp(timestamp),
            'exit_code': exit_code,
            'source': source,
        }
    )
    output_path = _status_directory(output_dir)
    _append_event(
        output_path / EVENTS_FILENAME,
        {
            'schema_version': SCHEMA_VERSION,
            'timestamp': _format_timestamp(timestamp),
            'run_id': context_name,
            'context_name': context_name,
            'event_type': 'run_finished'
            if exit_code == int(exceptions.PipelineExitCode.SUCCESS)
            else 'run_stopped'
            if exit_code == int(exceptions.PipelineExitCode.STOPPED)
            else 'run_failed',
            'state': state,
            'stage_number': None,
            'task_name': None,
            'severity': None,
            'reason_code': reason_code,
            'message': message,
            'exception_type': None,
            'traceback_excerpt': None,
            'payload': {'exit_code': exit_code, 'source': source},
        },
    )
    _write_snapshot(output_path / SNAPSHOT_FILENAME, snapshot)


def publish_active_context_completion(source: str) -> bool:
    context = _get_active_context()
    if context is None:
        return False

    _publish_terminal_event(
        context_name=context.name,
        output_dir=context.output_dir,
        exit_code=int(exceptions.PipelineExitCode.SUCCESS),
        reason_code=None,
        message=None,
        source=source,
    )
    return True


def publish_terminal_exception(
    exception: BaseException,
    *,
    request_path: str | None,
    source: str,
) -> bool:
    exit_code = exceptions.exit_code_for_exception(exception)
    reason_code = getattr(exception, 'reason_code', None)
    message = str(exception) or exception.__class__.__name__
    context = _get_active_context()
    if context is not None:
        _publish_terminal_event(
            context_name=context.name,
            output_dir=context.output_dir,
            exit_code=exit_code,
            reason_code=reason_code,
            message=message,
            source=source,
        )
        return True

    _write_adhoc_terminal_status(
        context_name=_request_context_name(request_path),
        output_dir=_request_output_dir(request_path),
        exit_code=exit_code,
        reason_code=reason_code,
        message=message,
        source=source,
    )
    return True


status_publisher = ContextStatusPublisher()