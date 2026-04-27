"""
The events module contains classes representing various stages in the
lifecycle of a pipeline reduction.

Events are published on a topic. The implementing class defines at a minimum
the event topic. The class may also define additional attributes identifying
and/or describing the event. These extra metadata can be interpreted by the
event listeners downstream.
"""


class Event:
    """
    Base class inherited by all pipeline events.
    """
    topic = ''


class ContextLifecycleEvent(Event):
    """
    Base class for events related to the lifecycle of the pipeline context.
    """
    topic = 'lifecycle.context'

    def __init__(self, context_name=None, output_dir=None):
        super().__init__()
        # Output directory should be set but can be an empty string.
        if output_dir is None:
            raise ValueError(f'output_dir unspecified when creating {self.__class__.__name__}')
        self.output_dir = output_dir
        if not context_name:
            raise ValueError(f'context_name unspecified when creating {self.__class__.__name__}')
        self.context_name = context_name


class ContextCreatedEvent(ContextLifecycleEvent):
    """
    Emitted when a pipeline Context is created.
    """
    topic = 'lifecycle.context.created'

    def __init__(self, context_name=None, output_dir=None):
        super().__init__(context_name=context_name, output_dir=output_dir)


class ContextResumedEvent(ContextLifecycleEvent):
    """
    Emitted when a pipeline Context is resumed.
    """
    topic = 'lifecycle.context.resumed'

    def __init__(self, context_name=None, output_dir=None):
        super().__init__(context_name=context_name, output_dir=output_dir)


class RunLifecycleEvent(ContextLifecycleEvent):
    """Base class for events related to overall pipeline run lifecycle."""

    topic = 'lifecycle.run'

    def __init__(
        self,
        context_name=None,
        output_dir=None,
        state=None,
        *,
        exit_code=None,
        reason_code=None,
        message=None,
        source=None,
    ):
        super().__init__(context_name=context_name, output_dir=output_dir)
        self.state = state
        self.exit_code = exit_code
        self.reason_code = reason_code
        self.message = message
        self.source = source


class RunCompletedEvent(RunLifecycleEvent):
    """Emitted when a pipeline run completes successfully."""

    topic = 'lifecycle.run.complete'

    def __init__(self, context_name=None, output_dir=None, *, source=None):
        super().__init__(
            context_name=context_name,
            output_dir=output_dir,
            state='completed',
            exit_code=0,
            source=source,
        )


class RunFailedEvent(RunLifecycleEvent):
    """Emitted when a pipeline run terminates with failure."""

    topic = 'lifecycle.run.failed'

    def __init__(
        self,
        context_name=None,
        output_dir=None,
        *,
        exit_code=None,
        reason_code=None,
        message=None,
        source=None,
    ):
        super().__init__(
            context_name=context_name,
            output_dir=output_dir,
            state='failed',
            exit_code=exit_code,
            reason_code=reason_code,
            message=message,
            source=source,
        )


class RunStoppedEvent(RunLifecycleEvent):
    """Emitted when a pipeline run stops intentionally."""

    topic = 'lifecycle.run.stopped'

    def __init__(
        self,
        context_name=None,
        output_dir=None,
        *,
        exit_code=None,
        reason_code=None,
        message=None,
        source=None,
    ):
        super().__init__(
            context_name=context_name,
            output_dir=output_dir,
            state='stopped',
            exit_code=exit_code,
            reason_code=reason_code,
            message=message,
            source=source,
        )


class LogMessageEvent(Event):
    """Emitted for elevated log records associated with a pipeline run."""

    topic = 'lifecycle.log.message'

    def __init__(
        self,
        context_name,
        *,
        stage_number=None,
        task_name=None,
        severity=None,
        message=None,
        levelno=None,
        logger_name=None,
    ):
        super().__init__()
        self.context_name = context_name
        self.stage_number = stage_number
        self.task_name = task_name
        self.severity = severity
        self.message = message
        self.levelno = levelno
        self.logger_name = logger_name


class ConditionLifecycleEvent(ContextLifecycleEvent):
    """Base class for events related to structured pipeline conditions."""

    topic = 'lifecycle.condition'

    def __init__(
        self,
        *,
        context_name=None,
        output_dir=None,
        state=None,
        code=None,
        severity=None,
        scope=None,
        disposition=None,
        message=None,
        details=None,
        producer_stage=None,
        producer_task=None,
        created_at=None,
        updated_at=None,
        active=None,
    ):
        super().__init__(context_name=context_name, output_dir=output_dir)
        self.state = state
        self.code = code
        self.severity = severity
        self.scope = scope
        self.disposition = disposition
        self.message = message
        self.details = details
        self.producer_stage = producer_stage
        self.producer_task = producer_task
        self.created_at = created_at
        self.updated_at = updated_at
        self.active = active


class ConditionRaisedEvent(ConditionLifecycleEvent):
    """Emitted when a structured pipeline condition becomes active."""

    topic = 'lifecycle.condition.raised'

    def __init__(self, **kwargs):
        super().__init__(state='raised', active=True, **kwargs)


class ConditionClearedEvent(ConditionLifecycleEvent):
    """Emitted when a structured pipeline condition is cleared."""

    topic = 'lifecycle.condition.cleared'

    def __init__(self, **kwargs):
        super().__init__(state='cleared', active=False, **kwargs)


class TaskLifecycleEvent(Event):
    """
    Base class for events related to the pipeline task lifecycle.
    """
    topic = 'lifecycle.task'

    def __init__(self, context_name, stage_number, state, task_name=None, reason_code=None, message=None):
        self.context_name = context_name
        self.stage_number = stage_number
        self.state = state
        self.task_name = task_name
        self.reason_code = reason_code
        self.message = message


class TaskStartedEvent(TaskLifecycleEvent):
    """
    Emitted when a pipeline Task is started.
    """
    topic = 'lifecycle.task.started'

    def __init__(self, context_name, stage_number, task_name=None):
        super().__init__(context_name, stage_number, 'started', task_name=task_name)


class TaskCompleteEvent(TaskLifecycleEvent):
    """
    Emitted when a pipeline Task completes.
    """
    topic = 'lifecycle.task.complete'

    def __init__(self, context_name, stage_number, task_name=None):
        super().__init__(context_name, stage_number, 'complete', task_name=task_name)


class TaskAbnormalExitEvent(TaskLifecycleEvent):
    """
    Emitted when a pipeline Task terminates due to an unexpected error.
    """
    topic = 'lifecycle.task.aborted'

    def __init__(self, context_name, stage_number, task_name=None):
        super().__init__(context_name, stage_number, 'abnormal exit', task_name=task_name)


class TaskStoppedEvent(TaskLifecycleEvent):
    """
    Emitted when a pipeline Task stops intentionally.
    """
    topic = 'lifecycle.task.stopped'

    def __init__(self, context_name, stage_number, task_name=None, reason_code=None, message=None):
        super().__init__(
            context_name,
            stage_number,
            'stopped',
            task_name=task_name,
            reason_code=reason_code,
            message=message,
        )


class WebLogLifecycleEvent(Event):
    """
    Base class for events related to weblog generation.

    This class represents the overall lifecycle encompassing generation of
    all weblog artifacts (all plots, all stages, etc.).
    """
    topic = 'lifecycle.weblog'

    def __init__(self, context_name, state):
        super().__init__()
        self.context_name = context_name
        self.state = state


class WebLogRenderingStartedEvent(WebLogLifecycleEvent):
    """
    Emitted when weblog rendering begins.
    """
    topic = 'lifecycle.weblog.rendering.started'

    def __init__(self, context_name):
        super().__init__(context_name, 'started')


class WebLogRenderingCompleteEvent(WebLogLifecycleEvent):
    """
    Emitted when weblog rendering ends.
    """
    topic = 'lifecycle.weblog.rendering.complete'

    def __init__(self, context_name):
        super().__init__(context_name, 'complete')


class WebLogStageLifecycleEvent(WebLogLifecycleEvent):
    """
    Base class for events related to weblog rendering of a specific stage.
    """
    topic = 'lifecycle.weblog.stage'

    def __init__(self, context_name, stage_number, state):
        super().__init__(context_name, state)
        self.stage_number = stage_number


class WebLogStageRenderingStartedEvent(WebLogStageLifecycleEvent):
    """
    Emitted when stage rendering begins.
    """
    topic = 'lifecycle.weblog.stage.rendering.started'

    def __init__(self, context_name, stage_number):
        super().__init__(context_name, stage_number, 'started')


class WebLogStageRenderingCompleteEvent(WebLogStageLifecycleEvent):
    """
    Emitted when stage rendering ends.
    """
    topic = 'lifecycle.weblog.stage.rendering.complete'

    def __init__(self, context_name, stage_number):
        super().__init__(context_name, stage_number, 'complete')


class WebLogStageRenderingAbnormalExitEvent(WebLogStageLifecycleEvent):
    """
    Emitted when stage rendering exits due to error.
    """
    topic = 'lifecycle.weblog.stage.rendering.aborted'

    def __init__(self, context_name, stage_number):
        super().__init__(context_name, stage_number, 'abnormal exit')


class ResultLifecycleEvent(Event):
    """
    Base class for events related to the acceptance of a pipeline Result.
    """
    topic = 'lifecycle.result'

    def __init__(self, context_name, stage_number, state, task_name=None):
        self.context_name = context_name
        self.stage_number = stage_number
        self.state = state
        self.task_name = task_name


class ResultAcceptingEvent(ResultLifecycleEvent):
    """
    Emitted when a Result is accepted into the Context.
    """
    topic = 'lifecycle.result.accepting'

    def __init__(self, context_name, stage_number, task_name=None):
        super().__init__(context_name, stage_number, 'accepting', task_name=task_name)


class ResultAcceptedEvent(ResultLifecycleEvent):
    """
    Emitted when a Result has been successfully incorporated into the Context.
    """
    topic = 'lifecycle.result.accepted'

    def __init__(self, context_name, stage_number, task_name=None):
        super().__init__(context_name, stage_number, 'accepted', task_name=task_name)


class ResultAcceptErrorEvent(TaskLifecycleEvent):
    """
    Emitted when Results acceptance fails due to error.
    """
    topic = 'lifecycle.result.error'

    def __init__(self, context_name, stage_number, task_name=None):
        super().__init__(context_name, stage_number, 'error', task_name=task_name)
