"""Prefect adapter for pipeline orchestration.

This module provides a non-invasive Prefect integration layer that wraps
the existing pipeline execution entry points (``executeppr``,
``executevlappr``, ``recipereducer``) as Prefect flows/tasks.  When
enabled, every pipeline stage appears as an individually tracked Prefect
task inside a parent flow, giving operators dashboard visibility, state
tracking, and retry management without changing any core pipeline code.

Activation
----------
Set the environment variable ``PIPELINE_USE_PREFECT=1`` **or** set
``pipeconfig.prefect.enabled: true`` in ``config.yaml``.  If the
``prefect`` package is not installed the adapter silently falls back to
native execution.

Design
------
* **Thin wrapper pattern** – Prefect ``@task`` / ``@flow`` decorators are
  applied to *new* functions that delegate to existing pipeline
  callables.  No business logic is duplicated.
* **Lightweight serialization** – Only :class:`TaskResultSummary`
  (a small dataclass) crosses the Prefect serialization boundary.  The
  heavy ``Context`` / ``Results`` objects stay in-process.
* **Coexistence** – The pipeline's ``pypubsub`` event bus,
  ``TimeTracker``, and weblog generation continue to function normally.
"""

from __future__ import annotations

import dataclasses
import os
import time
import traceback
from typing import TYPE_CHECKING, Any

from pipeline import infrastructure
from pipeline.infrastructure import exceptions

if TYPE_CHECKING:
    from pipeline.infrastructure.launcher import Context

LOG = infrastructure.logging.get_logger(__name__)

# ---------------------------------------------------------------------------
# Prefect availability detection
# ---------------------------------------------------------------------------

try:
    from prefect import flow, task

    _PREFECT_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PREFECT_AVAILABLE = False


def is_prefect_enabled() -> bool:
    """Return ``True`` when Prefect orchestration should be used.

    The check is intentionally cheap (env-var / config lookup) so it can be
    called at the top of every entry-point without measurable overhead.

    The function returns ``True`` only when **all** of the following hold:

    1. The ``prefect`` package is importable.
    2. Either the ``PIPELINE_USE_PREFECT`` environment variable is set to a
       truthy value **or** ``pipeconfig.prefect.enabled`` is ``true`` in
       ``config.yaml``.
    """
    if not _PREFECT_AVAILABLE:
        return False

    # Environment variable takes precedence.
    env_val = os.environ.get('PIPELINE_USE_PREFECT', '').strip()
    if env_val:
        return env_val.lower() in ('1', 'true', 'yes')

    # Fall back to config.yaml.
    try:
        from pipeline.config import config

        return bool(config.get('pipeconfig', {}).get('prefect', {}).get('enabled', False))
    except Exception:
        return False


def _apply_prefect_config() -> None:
    """Apply Prefect-related settings from ``config.yaml`` to the environment.

    This function reads ``pipeconfig.prefect`` from the pipeline configuration
    and sets corresponding environment variables (e.g. ``PREFECT_API_URL``)
    when they are not already set.  This lets users consolidate all Prefect
    configuration in ``config.yaml`` instead of managing separate env vars.

    This is idempotent and should be called once at the start of each
    Prefect flow.
    """
    try:
        from pipeline.config import config

        prefect_cfg = config.get('pipeconfig', {}).get('prefect', {})

        # api_url → PREFECT_API_URL  (only if not already set by the user)
        api_url = prefect_cfg.get('api_url')
        if api_url and not os.environ.get('PREFECT_API_URL'):
            os.environ['PREFECT_API_URL'] = str(api_url)
            LOG.info('Set PREFECT_API_URL=%s from config.yaml', api_url)

    except Exception as exc:
        LOG.debug('Could not apply Prefect config from config.yaml: %s', exc)

    # Suppress httpx INFO-level logs (e.g. "HTTP Request: POST ... 500");
    # errors are already caught and re-logged at DEBUG by our own code.
    import logging

    logging.getLogger('httpx').setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Lightweight result summary
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class TaskResultSummary:
    """A small, JSON-serializable summary returned by each Prefect task.

    The full pipeline ``Results`` object is intentionally **not** passed
    through Prefect's serialization layer because it is large and tightly
    coupled to CASA internals.
    """

    stage_number: int | None = None
    task_name: str = ''
    success: bool = True
    error_message: str = ''
    duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Dask observability bridge
# ---------------------------------------------------------------------------

_dask_observer_registered = False


def _register_dask_observer() -> None:
    """Register a Dask SchedulerPlugin that logs tier0 activity.

    This function is idempotent — calling it multiple times is safe.
    It attaches a lightweight plugin to the existing ``daskclient``
    (from :mod:`daskhelpers`) that logs task state transitions.  Because
    Prefect captures log output from flow/task functions, these messages
    appear in the Prefect dashboard alongside stage-level information.

    If no Dask client is active or Dask is not available, this is a no-op.
    """
    global _dask_observer_registered
    if _dask_observer_registered:
        return

    try:
        from pipeline.infrastructure import daskhelpers

        if not daskhelpers.daskclient:
            return

        from distributed import SchedulerPlugin

        class PrefectDaskPlugin(SchedulerPlugin):
            """Reports Dask task transitions to the pipeline logger.

            Runs inside the scheduler (in-process for ``LocalCluster``,
            remote for SLURM/HTCondor).  Each transition is logged at
            DEBUG level and captured by Prefect's log system.
            """

            name = 'prefect-dask-observer'

            def __init__(self):
                self.task_count = 0
                self.error_count = 0

            def transition(self, key, start, finish, *args, **kwargs):
                if finish == 'memory':
                    self.task_count += 1
                    LOG.debug(
                        'Dask tier0: task %s completed (%s -> %s) [total: %d]',
                        key,
                        start,
                        finish,
                        self.task_count,
                    )
                elif finish == 'erred':
                    self.error_count += 1
                    LOG.warning(
                        'Dask tier0: task %s FAILED (%s -> %s) [errors: %d]',
                        key,
                        start,
                        finish,
                        self.error_count,
                    )

        daskhelpers.daskclient.register_scheduler_plugin(PrefectDaskPlugin())
        _dask_observer_registered = True
        LOG.info('Prefect-Dask observer plugin registered on %s', daskhelpers.daskclient)

        # Publish Dask dashboard URL as a Prefect artifact for easy access.
        _publish_dask_dashboard_link(daskhelpers.daskclient)

    except Exception as exc:
        LOG.debug('Could not register Dask observer: %s', exc)


def _publish_dask_dashboard_link(client) -> None:
    """Create a Prefect markdown artifact with a link to the Dask dashboard.

    This gives operators one-click access from the Prefect UI to the live
    Dask task stream, worker memory, and cluster status views.
    """
    try:
        from prefect.artifacts import create_markdown_artifact

        dashboard_link = client.dashboard_link
        if not dashboard_link:
            return

        info = client.scheduler_info()
        n_workers = len(info.get('workers', {}))

        markdown = (
            f'## Dask Cluster\n\n'
            f'- **Dashboard**: [{dashboard_link}]({dashboard_link})\n'
            f'- **Workers**: {n_workers}\n'
            f'- **Scheduler**: `{client.scheduler.address}`\n'
        )
        create_markdown_artifact(
            key='dask-cluster',
            markdown=markdown,
            description='Dask cluster dashboard and status',
        )
        LOG.info('Published Dask dashboard artifact: %s', dashboard_link)

    except Exception as exc:
        LOG.debug('Could not publish Dask dashboard artifact: %s', exc)


def _log_dask_summary(task_name: str) -> None:
    """Log Dask cluster utilization and publish a per-worker Prefect artifact.

    Called after each ``run_pipeline_task`` to give Prefect users visibility
    into how the Dask cluster was used during that stage.  The artifact
    appears in the Prefect dashboard with a per-worker breakdown.

    This function spawns a daemon thread to prevent any slow or hanging Prefect
    API / Dask scheduler queries from blocking the main pipeline workflow.
    """
    try:
        from pipeline.infrastructure import daskhelpers

        if not daskhelpers.daskclient:
            return

        def _background_summary():
            try:
                # Add timeout so the daemon thread doesn't hang infinitely if Dask is locked
                info = daskhelpers.daskclient.scheduler_info(timeout=10)
                workers = info.get('workers', {})
                if not workers:
                    return

                n_workers = len(workers)
                total_memory = sum(w.get('memory_limit', 0) for w in workers.values())
                used_memory = sum(w.get('metrics', {}).get('memory', 0) for w in workers.values())

                mem_pct = (used_memory / total_memory * 100) if total_memory > 0 else 0.0

                LOG.info(
                    'Dask cluster after %s: %d workers, memory %.1f%% (%s / %s)',
                    task_name,
                    n_workers,
                    mem_pct,
                    _human_bytes(used_memory),
                    _human_bytes(total_memory),
                )

                # Publish per-worker detail as a Prefect artifact.
                _publish_dask_worker_artifact(task_name, workers, daskhelpers.daskclient)
            except Exception as exc:
                LOG.debug('Could not collect Dask summary: %s', exc)

        import threading

        t = threading.Thread(target=_background_summary, daemon=True)
        t.start()

    except Exception as exc:
        LOG.debug('Could not spawn Dask summary thread: %s', exc)


def _publish_dask_worker_artifact(task_name: str, workers: dict, client) -> None:
    """Create a Prefect markdown artifact with individual worker details.

    The artifact includes a table with each worker's name, thread count,
    memory usage, and number of tasks executed, plus a link to the Dask
    dashboard.
    """
    try:
        from prefect.artifacts import create_markdown_artifact

        dashboard_link = client.dashboard_link or ''

        # Build per-worker table rows.
        rows = []
        for addr, w in workers.items():
            name = w.get('name', addr)
            nthreads = w.get('nthreads', '?')
            mem_limit = w.get('memory_limit', 0)
            metrics = w.get('metrics', {})
            mem_used = metrics.get('memory', 0)
            cpu = metrics.get('cpu', 0.0)
            n_tasks = metrics.get('task_count', metrics.get('executing', '?'))
            status = w.get('status', 'unknown')

            mem_pct = (mem_used / mem_limit * 100) if mem_limit > 0 else 0.0
            rows.append(
                f'| {name} | {status} | {nthreads} | {cpu:.0f}% '
                f'| {_human_bytes(mem_used)} / {_human_bytes(mem_limit)} ({mem_pct:.0f}%) '
                f'| {n_tasks} |'
            )

        table_header = (
            '| Worker | Status | Threads | CPU | Memory (used / limit) | Tasks |\n'
            '|--------|--------|---------|-----|----------------------|-------|\n'
        )
        table_body = '\n'.join(rows)

        header = f'## Dask Workers — after `{task_name}`\n\n'
        if dashboard_link:
            header += f'📊 [Dask Dashboard]({dashboard_link})\n\n'

        markdown = header + table_header + table_body

        create_markdown_artifact(
            key='dask-workers',
            markdown=markdown,
            description=f'Dask worker status after {task_name}',
        )

    except Exception as exc:
        LOG.debug('Could not publish Dask worker artifact: %s', exc)


def _human_bytes(n: int) -> str:
    """Format byte count as human-readable string."""
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if abs(n) < 1024:
            return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} PiB'


# ---------------------------------------------------------------------------
# Prefect @task wrapper
# ---------------------------------------------------------------------------


def _execute_pipeline_task(task_name: str, task_args: dict[str, Any]) -> TaskResultSummary:
    """Execute a single pipeline task and return a lightweight summary.

    This is the core delegate shared by all Prefect task wrappers.  It
    calls into the normal pipeline CLI layer, so all existing event-bus
    events, time-tracking, QA, and weblog rendering happen as usual.

    Args:
        task_name: CLI name of the pipeline task (e.g. ``'hifa_bandpass'``).
        task_args: Keyword arguments forwarded to the task callable.

    Returns:
        A :class:`TaskResultSummary` describing the outcome.

    Raises:
        exceptions.PipelineException: Re-raised when the task result
            contains tracebacks, so that Prefect marks the task as
            *failed*.
    """
    from pipeline import cli

    start = time.monotonic()
    import casatasks
    from pipeline.infrastructure import logging as log_utils

    origin = task_name
    if getattr(log_utils, 'DASK_WORKER_ID', None):
        origin = f'{log_utils.DASK_WORKER_ID}::{origin}'
    casatasks.casalog.post(f'Prefect adapter: executing {task_name}({task_args})', 'INFO', origin)

    pipeline_task = cli.get_pipeline_task_with_name(task_name)

    try:
        result = pipeline_task(**task_args)
    except Exception:
        elapsed = time.monotonic() - start
        tb = traceback.format_exc()
        import casatasks
        from pipeline.infrastructure import logging as log_utils

        origin = task_name
        if getattr(log_utils, 'DASK_WORKER_ID', None):
            origin = f'{log_utils.DASK_WORKER_ID}::{origin}'
        casatasks.casalog.post(f'Prefect adapter: unhandled error in {task_name}', 'SEVERE', origin)
        casatasks.casalog.post(tb, 'SEVERE', origin)
        return TaskResultSummary(
            task_name=task_name,
            success=False,
            error_message=tb,
            duration_seconds=elapsed,
        )

    elapsed = time.monotonic() - start
    stage_number = getattr(result, 'stage_number', None)

    # Check for tracebacks (same logic as recipereducer._execute_task).
    from pipeline.infrastructure import utils

    tracebacks = utils.get_tracebacks(result)
    if tracebacks:
        msg = '\n'.join(tracebacks)
        raise exceptions.PipelineException(msg)

    _log_dask_summary(task_name)

    return TaskResultSummary(
        stage_number=stage_number,
        task_name=task_name,
        success=True,
        duration_seconds=elapsed,
    )


# Only define decorated versions when Prefect is available.
if _PREFECT_AVAILABLE:

    @task(
        name='pipeline-task',
        task_run_name='{task_name}',
        log_prints=True,
    )
    def run_pipeline_task(task_name: str, task_args: dict[str, Any]) -> TaskResultSummary:
        """Prefect-tracked execution of a single pipeline task."""
        return _execute_pipeline_task(task_name, task_args)

else:
    # Fallback: plain function without Prefect decorators.
    run_pipeline_task = _execute_pipeline_task  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Prefect @flow: PPR (ALMA)
# ---------------------------------------------------------------------------


def _run_ppr_flow_impl(
    pprXmlFile: str,
    importonly: bool = True,
    breakpoint: str = 'breakpoint',
    bpaction: str = 'ignore',
    loglevel: str = 'info',
    plotlevel: str = 'default',
    interactive: bool = True,
) -> None:
    """Prefect flow implementation for :func:`executeppr.executeppr`.

    This function replicates the control flow of the original
    ``executeppr`` but delegates each pipeline task to
    :func:`run_pipeline_task` so that Prefect tracks them individually.
    """
    from pipeline import cli
    from pipeline.infrastructure import casa_tools, project, utils
    from pipeline.infrastructure.executeppr import (
        _getFirstRequest,
        _getPerformanceParameters,
        _getProcessingIntents,
        _getSessions,
        export_on_exception,
        save_existing_context,
    )
    from pipeline.infrastructure import filenamer

    echo_to_screen = interactive
    workingDir = None

    save_existing_context()

    try:
        casa_tools.post_to_log('Analyzing pipeline processing request ...', echo_to_screen=echo_to_screen)
        info, structure, relativePath, intentsDict, asdmList, procedureName, commandsList = _getFirstRequest(pprXmlFile)
        processing_intents = _getProcessingIntents(intentsDict, procedureName)

        if 'SCIPIPE_ROOTDIR' in os.environ:
            workingDir = os.path.join(os.path.expandvars('$SCIPIPE_ROOTDIR'), relativePath, 'working')
            rawDir = os.path.join(os.path.expandvars('$SCIPIPE_ROOTDIR'), relativePath, 'rawdata')
        else:
            workingDir = os.path.abspath(os.path.join('..', 'working'))
            rawDir = os.path.abspath(os.path.join('..', 'rawdata'))

        # Breakpoint check
        bpset = False
        if breakpoint != '':
            for command in commandsList:
                if command[0] == breakpoint:
                    casa_tools.post_to_log('    Found break point: ' + breakpoint, echo_to_screen=echo_to_screen)
                    casa_tools.post_to_log('    Break point action is: ' + bpaction, echo_to_screen=echo_to_screen)
                    bpset = True
                    break

        if bpset and bpaction == 'resume':
            context = cli.h_resume(filename='last')
            context.processing_intents.update(processing_intents)
            casa_tools.post_to_log('    Resuming from last context', echo_to_screen=echo_to_screen)
        else:
            context = cli.h_init(loglevel=loglevel, plotlevel=plotlevel, processing_intents=processing_intents)
            casa_tools.post_to_log('    Creating new pipeline context', echo_to_screen=echo_to_screen)

    except Exception:
        casa_tools.post_to_log('Beginning pipeline run ...', echo_to_screen=echo_to_screen)
        casa_tools.post_to_log('For processing request: ' + pprXmlFile, echo_to_screen=echo_to_screen)
        traceback.print_exc()
        errstr = traceback.format_exc()
        casa_tools.post_to_log(errstr, echo_to_screen=echo_to_screen)
        casa_tools.post_to_log('Terminating procedure execution ...', echo_to_screen=echo_to_screen)
        utils.write_errorexit_file(workingDir, 'errorexit', 'txt')
        return

    # Validation
    casa_tools.post_to_log('Beginning pipeline run ...', echo_to_screen=echo_to_screen)
    casa_tools.post_to_log('For processing request: ' + pprXmlFile, echo_to_screen=echo_to_screen)

    if relativePath == '':
        casa_tools.post_to_log('    Undefined relative data path', echo_to_screen=echo_to_screen)
        casa_tools.post_to_log('Terminating pipeline execution ...', echo_to_screen=echo_to_screen)
        utils.write_errorexit_file(workingDir, 'errorexit', 'txt')
        return
    elif len(asdmList) < 1:
        casa_tools.post_to_log('    Empty ASDM list', echo_to_screen=echo_to_screen)
        casa_tools.post_to_log('Terminating pipeline execution ...', echo_to_screen=echo_to_screen)
        utils.write_errorexit_file(workingDir, 'errorexit', 'txt')
        return
    elif len(commandsList) < 1:
        casa_tools.post_to_log('    Empty commands list', echo_to_screen=echo_to_screen)
        casa_tools.post_to_log('Terminating pipeline execution ...', echo_to_screen=echo_to_screen)
        utils.write_errorexit_file(workingDir, 'errorexit', 'txt')
        return

    # Project summary
    casa_tools.post_to_log('Project summary', echo_to_screen=echo_to_screen)
    for item in info:
        casa_tools.post_to_log('    ' + item[1][0] + item[1][1], echo_to_screen=echo_to_screen)
    ds = dict(info)
    context.project_summary = project.ProjectSummary(
        proposal_code=ds['proposal_code'][1],
        proposal_title='unknown',
        piname='unknown',
        observatory=ds['observatory'][1],
        telescope=ds['telescope'][1],
    )

    # Project structure
    casa_tools.post_to_log('Project structure', echo_to_screen=echo_to_screen)
    for item in structure:
        casa_tools.post_to_log('    ' + item[1][0] + item[1][1], echo_to_screen=echo_to_screen)
    ds = dict(structure)
    context.project_structure = project.ProjectStructure(
        ous_entity_id=ds['ous_entity_id'][1],
        ous_part_id=ds['ous_part_id'][1],
        ous_title=ds['ous_title'][1],
        ous_type=ds['ous_type'][1],
        ps_entity_id=ds['ps_entity_id'][1],
        ousstatus_entity_id=ds['ousstatus_entity_id'][1],
        ppr_file=pprXmlFile,
        recipe_name=procedureName,
    )

    context.project_performance_parameters = _getPerformanceParameters(intentsDict)

    # Sessions
    if len(intentsDict) > 0:
        sessionsDict = _getSessions(intentsDict)
    else:
        sessionsDict = {}

    casa_tools.post_to_log('Directory structure', echo_to_screen=echo_to_screen)
    casa_tools.post_to_log('    Working directory: ' + workingDir, echo_to_screen=echo_to_screen)
    casa_tools.post_to_log('    Raw data directory: ' + rawDir, echo_to_screen=echo_to_screen)

    # ASDM list
    casa_tools.post_to_log('Number of ASDMs: ' + str(len(asdmList)), echo_to_screen=echo_to_screen)
    files = []
    sessions = []
    defsession = 'session_1'
    for asdm in asdmList:
        session = defsession
        for key, value in sessionsDict.items():
            if filenamer.sanitize_for_ms(asdm[1]) in value:
                session = key.lower()
                break
        sessions.append(session)
        files.append(os.path.join(rawDir, asdm[1]))
        casa_tools.post_to_log('    Session: ' + session + '  ASDM: ' + asdm[1], echo_to_screen=echo_to_screen)

    casa_tools.post_to_log('\nStarting procedure execution ...\n', echo_to_screen=echo_to_screen)
    casa_tools.post_to_log('Procedure name: ' + procedureName + '\n', echo_to_screen=echo_to_screen)

    import_tasks = ('h_importdata', 'hifa_importdata', 'hifv_importdata', 'hsd_importdata', 'hsdn_importdata')
    restore_tasks = ('h_restoredata', 'hifa_restoredata', 'hifv_restoredata', 'hsd_restoredata')
    restore_tasks_no_session = ('hsdn_restoredata',)

    errstr = ''
    foundbp = False
    tracebacks_list = []

    for command in commandsList:
        pipeline_task_name = command[0]
        task_args = command[1]
        casa_tools.set_log_origin(fromwhere=pipeline_task_name)

        # Breakpoint handling
        if bpset:
            if pipeline_task_name == breakpoint:
                foundbp = True
                if bpaction == 'ignore':
                    casa_tools.post_to_log('Ignoring breakpoint ' + pipeline_task_name, echo_to_screen=echo_to_screen)
                    continue
                elif bpaction == 'break':
                    casa_tools.post_to_log(
                        'Terminating execution at breakpoint ' + pipeline_task_name, echo_to_screen=echo_to_screen
                    )
                    break
                elif bpaction == 'resume':
                    casa_tools.post_to_log(
                        'Resuming execution after breakpoint ' + pipeline_task_name, echo_to_screen=echo_to_screen
                    )
                    continue
            elif not foundbp and bpaction == 'resume':
                casa_tools.post_to_log('Skipping task ' + pipeline_task_name, echo_to_screen=echo_to_screen)
                continue

        casa_tools.post_to_log('Executing command ...' + pipeline_task_name, echo_to_screen=echo_to_screen)

        for keyword, value in task_args.items():
            casa_tools.post_to_log('    Parameter: ' + keyword + ' = ' + repr(value), echo_to_screen=echo_to_screen)

        if pipeline_task_name in import_tasks or pipeline_task_name in restore_tasks:
            task_args['vis'] = files
            task_args['session'] = sessions
        elif pipeline_task_name in restore_tasks_no_session:
            task_args['vis'] = files

        try:
            summary = run_pipeline_task(task_name=pipeline_task_name, task_args=task_args)

            if not summary.success:
                errstr = summary.error_message
                casa_tools.post_to_log(errstr, echo_to_screen=echo_to_screen)

            if importonly and pipeline_task_name in import_tasks:
                casa_tools.post_to_log(
                    'Terminating execution after running ' + pipeline_task_name, echo_to_screen=echo_to_screen
                )
                break

        except exceptions.PipelineException:
            raise
        except Exception:
            casa_tools.post_to_log(
                'Unhandled error in executeppr while running pipeline task {}'.format(pipeline_task_name),
                echo_to_screen=echo_to_screen,
            )
            errstr = traceback.format_exc()
            casa_tools.post_to_log(errstr, echo_to_screen=echo_to_screen)

        if errstr:
            tracebacks_list.append(errstr)

        if len(tracebacks_list) > 0:
            errorfile = utils.write_errorexit_file(workingDir, 'errorexit', 'txt')
            export_on_exception(context, errorfile)
            cli.h_save()
            casa_tools.post_to_log('Terminating procedure execution ...', echo_to_screen=echo_to_screen)
            casa_tools.set_log_origin(fromwhere='')
            previous_tracebacks_as_string = '\n'.join(tracebacks_list)
            raise exceptions.PipelineException(previous_tracebacks_as_string)

    cli.h_save()
    casa_tools.post_to_log('Terminating procedure execution ...', echo_to_screen=echo_to_screen)
    casa_tools.set_log_origin(fromwhere='')


# ---------------------------------------------------------------------------
# Prefect @flow: PPR (VLA)
# ---------------------------------------------------------------------------


def _run_vla_ppr_flow_impl(
    pprXmlFile: str,
    importonly: bool = True,
    loglevel: str = 'info',
    plotlevel: str = 'summary',
    interactive: bool = True,
) -> None:
    """Prefect flow implementation for :func:`executevlappr.executeppr`."""
    from pipeline import cli
    from pipeline.infrastructure import casa_tools, project, utils
    from pipeline.infrastructure.executeppr import (
        _getPerformanceParameters,
        _getProcessingIntents,
        save_existing_context,
    )
    from pipeline.infrastructure.executevlappr import (
        _getFirstRequest,
    )

    echo_to_screen = interactive
    workingDir = None

    save_existing_context()

    try:
        casa_tools.post_to_log('Analyzing pipeline processing request ...', echo_to_screen=echo_to_screen)
        info, structure, relativePath, intentsDict, asdmList, procedureName, commandsList = _getFirstRequest(pprXmlFile)
        processing_intents = _getProcessingIntents(intentsDict, procedureName)

        if 'SCIPIPE_ROOTDIR' in os.environ:
            workingDir = os.path.join(os.path.expandvars('$SCIPIPE_ROOTDIR'), relativePath, 'working')
            rawDir = os.path.join(os.path.expandvars('$SCIPIPE_ROOTDIR'), relativePath, 'rawdata')
        else:
            workingDir = os.path.abspath(os.path.join('..', 'working'))
            rawDir = os.path.abspath(os.path.join('..', 'rawdata'))

        context = cli.h_init(loglevel=loglevel, plotlevel=plotlevel, processing_intents=processing_intents)

    except Exception:
        casa_tools.post_to_log('Beginning pipeline run ...', echo_to_screen=echo_to_screen)
        casa_tools.post_to_log('For processing request: ' + pprXmlFile, echo_to_screen=echo_to_screen)
        traceback.print_exc()
        errstr = traceback.format_exc()
        casa_tools.post_to_log(errstr, echo_to_screen=echo_to_screen)
        casa_tools.post_to_log('Terminating procedure execution ...', echo_to_screen=echo_to_screen)
        utils.write_errorexit_file(workingDir, 'errorexit', 'txt')
        return

    # Validate
    casa_tools.post_to_log('Beginning pipeline run ...', echo_to_screen=echo_to_screen)
    casa_tools.post_to_log('For processing request: ' + pprXmlFile, echo_to_screen=echo_to_screen)

    if relativePath == '':
        casa_tools.post_to_log('    Undefined relative data path', echo_to_screen=echo_to_screen)
        casa_tools.post_to_log('Terminating pipeline execution ...', echo_to_screen=echo_to_screen)
        utils.write_errorexit_file(workingDir, 'errorexit', 'txt')
        return
    elif len(asdmList) < 1:
        casa_tools.post_to_log('    Empty ASDM list', echo_to_screen=echo_to_screen)
        casa_tools.post_to_log('Terminating pipeline execution ...', echo_to_screen=echo_to_screen)
        utils.write_errorexit_file(workingDir, 'errorexit', 'txt')
        return
    elif len(commandsList) < 1:
        casa_tools.post_to_log('    Empty commands list', echo_to_screen=echo_to_screen)
        casa_tools.post_to_log('Terminating pipeline execution ...', echo_to_screen=echo_to_screen)
        utils.write_errorexit_file(workingDir, 'errorexit', 'txt')
        return

    # Project summary / structure
    casa_tools.post_to_log('Project summary', echo_to_screen=echo_to_screen)
    for item in info:
        casa_tools.post_to_log('    ' + item[1][0] + item[1][1], echo_to_screen=echo_to_screen)
    ds = dict(info)
    context.project_summary = project.ProjectSummary(
        proposal_code=ds['proposal_code'][1],
        proposal_title='unknown',
        piname='unknown',
        observatory=ds['observatory'][1],
        telescope=ds['telescope'][1],
    )

    casa_tools.post_to_log('Project structure', echo_to_screen=echo_to_screen)
    for item in structure:
        casa_tools.post_to_log('    ' + item[1][0] + item[1][1], echo_to_screen=echo_to_screen)

    context.project_structure = project.ProjectStructure(ppr_file=pprXmlFile, recipe_name=procedureName)

    context.project_performance_parameters = _getPerformanceParameters(intentsDict)

    casa_tools.post_to_log('Directory structure', echo_to_screen=echo_to_screen)
    casa_tools.post_to_log('    Working directory: ' + workingDir, echo_to_screen=echo_to_screen)
    casa_tools.post_to_log('    Raw data directory: ' + rawDir, echo_to_screen=echo_to_screen)

    # ASDM list
    casa_tools.post_to_log('Number of ASDMs: ' + str(len(asdmList)), echo_to_screen=echo_to_screen)
    files = []
    sessions = []
    defsession = 'session_1'
    for asdm in asdmList:
        session = defsession
        sessions.append(session)
        files.append(os.path.join(rawDir, asdm[1]))
        casa_tools.post_to_log('    Session: ' + session + '  ASDM: ' + asdm[1], echo_to_screen=echo_to_screen)

    casa_tools.post_to_log('\nStarting procedure execution ...\n', echo_to_screen=echo_to_screen)
    casa_tools.post_to_log('Procedure name: ' + procedureName + '\n', echo_to_screen=echo_to_screen)

    import_tasks = ('h_importdata', 'hifa_importdata', 'hifv_importdata')
    restore_tasks = ('h_restoredata', 'hifv_restoredata')
    breakpoint_task = 'breakpoint'

    for command in commandsList:
        pipeline_task_name = command[0]
        task_args = command[1]
        casa_tools.set_log_origin(fromwhere=pipeline_task_name)

        if pipeline_task_name == breakpoint_task:
            casa_tools.post_to_log(
                'Found {}, not performing any action.'.format(pipeline_task_name), echo_to_screen=echo_to_screen
            )
            continue

        casa_tools.post_to_log('Executing command ...' + pipeline_task_name, echo_to_screen=echo_to_screen)

        for keyword, value in task_args.items():
            casa_tools.post_to_log('    Parameter: ' + keyword + ' = ' + repr(value), echo_to_screen=echo_to_screen)

        if pipeline_task_name in import_tasks or pipeline_task_name in restore_tasks:
            task_args['vis'] = files
            task_args['session'] = sessions

        # VLA spectral mode skip
        spectral_mode = intentsDict.get('SPECTRAL_MODE', False)
        if spectral_mode and pipeline_task_name == 'hifv_hanning':
            casa_tools.post_to_log('SPECTRAL_MODE=True.  Hanning smoothing will not be executed.')
            continue

        try:
            run_pipeline_task(task_name=pipeline_task_name, task_args=task_args)

            if importonly and pipeline_task_name in import_tasks:
                casa_tools.post_to_log(
                    'Terminating execution after running ' + pipeline_task_name, echo_to_screen=echo_to_screen
                )
                break

        except exceptions.PipelineException:
            raise
        except Exception:
            casa_tools.post_to_log(
                'Unhandled error in executevlappr while running pipeline task {}'.format(pipeline_task_name),
                echo_to_screen=echo_to_screen,
            )
            errstr = traceback.format_exc()
            casa_tools.post_to_log(errstr, echo_to_screen=echo_to_screen)
            utils.write_errorexit_file(workingDir, 'errorexit', 'txt')
            break

    cli.h_save()
    casa_tools.post_to_log('Terminating procedure execution ...', echo_to_screen=echo_to_screen)
    casa_tools.set_log_origin(fromwhere='')


# ---------------------------------------------------------------------------
# Prefect @flow: recipereducer.reduce
# ---------------------------------------------------------------------------


def _run_recipe_flow_impl(
    vis: list[str] | None = None,
    infiles: list[str] | None = None,
    procedure: str = 'procedure_hifa_calimage.xml',
    context: Context | None = None,
    name: str | None = None,
    loglevel: str = 'info',
    plotlevel: str = 'default',
    session: list[str] | None = None,
    exitstage: int | None = None,
    startstage: int | None = None,
) -> Context:
    """Prefect flow implementation for :func:`recipereducer.reduce`."""
    from pipeline import cli
    from pipeline.recipereducer import (
        TaskArgs,
        _create_context,
        _get_context_name,
        _get_procedure_title,
        _get_tasks,
        _register_context,
    )

    if vis is None:
        vis = []
    if infiles is None:
        infiles = []

    if context is None:
        name = name if name else _get_context_name(procedure)
        context = _create_context(loglevel, plotlevel, name)
        procedure_title = _get_procedure_title(procedure)
        context.set_state('ProjectStructure', 'recipe_name', procedure_title)

    _register_context(loglevel, plotlevel, context)

    if session is None:
        session = ['default'] * len(vis)

    if startstage is None:
        startstage = 0

    task_args_tuple = TaskArgs(vis, infiles, session)
    task_generator = _get_tasks(context, task_args_tuple, procedure)

    try:
        procedure_stage_nr = 0
        while True:
            task_fn, task_args = next(task_generator)
            procedure_stage_nr += 1
            if procedure_stage_nr < startstage:
                continue

            task_name = task_fn.__name__
            summary = run_pipeline_task(task_name=task_name, task_args=task_args)

            if not summary.success:
                return context

            if summary.stage_number is exitstage and exitstage is not None:
                break

    except StopIteration:
        pass
    finally:
        LOG.info('Saving context...')
        cli.h_save()

    return context


# ---------------------------------------------------------------------------
# Prefect @flow: recipereducer.run_named_tasks
# ---------------------------------------------------------------------------


def _run_named_tasks_flow_impl(
    tasks: list[tuple[str, dict[str, Any]]],
) -> Context:
    """Prefect flow implementation for :func:`recipereducer.run_named_tasks`."""
    from pipeline import cli
    from pipeline.infrastructure import launcher

    LOG.info('Initializing context for explicit task list...')
    cli.h_init()

    for task_name, task_args in tasks:
        summary = run_pipeline_task(task_name=task_name, task_args=task_args)

        if not summary.success:
            return launcher.Pipeline(context='last').context

    LOG.info('Saving context after explicit task list execution...')
    cli.h_save()

    return launcher.Pipeline(context='last').context


# ---------------------------------------------------------------------------
# Register Prefect-decorated flows (only when Prefect is available)
# ---------------------------------------------------------------------------


def _get_prefect_config() -> dict:
    """Read ``pipeconfig.prefect`` from config.yaml, with sensible defaults."""
    try:
        from pipeline.config import config

        return config.get('pipeconfig', {}).get('prefect', {})
    except Exception:
        return {}


if _PREFECT_AVAILABLE:
    # Apply config BEFORE defining @flow-decorated functions so that
    # PREFECT_API_URL is set when Prefect resolves the server connection.
    _apply_prefect_config()

    _pcfg = _get_prefect_config()
    _flow_name = _pcfg.get('flow_name', 'CASA Pipeline')
    _log_prints = _pcfg.get('log_prints', True)

    def _ppr_flow_name() -> str:
        """Derive the flow run name from the PPR filename."""
        import prefect.runtime

        ppr_path = prefect.runtime.flow_run.parameters.get('pprXmlFile', 'unknown.xml')
        return os.path.basename(ppr_path).replace('.xml', '')

    def _recipe_flow_name() -> str:
        """Derive the flow run name from the recipe procedure or name."""
        import prefect.runtime

        params = prefect.runtime.flow_run.parameters
        # run_recipe_flow is declared as ``def run_recipe_flow(**kwargs)``,
        # so Prefect binds the call as a single ``kwargs`` parameter.
        kwargs = params.get('kwargs', params)
        if kwargs.get('name'):
            return kwargs['name']
        procedure = kwargs.get('procedure', 'procedure_unknown')
        return os.path.basename(procedure).replace('.xml', '')

    @flow(name=f'{_flow_name} PPR', flow_run_name=_ppr_flow_name, log_prints=_log_prints)
    def run_ppr_flow(pprXmlFile: str, **kwargs) -> None:
        """Prefect flow wrapping :func:`executeppr.executeppr`."""
        _apply_prefect_config()
        _register_dask_observer()
        return _run_ppr_flow_impl(pprXmlFile, **kwargs)

    @flow(name=f'{_flow_name} VLA PPR', flow_run_name=_ppr_flow_name, log_prints=_log_prints)
    def run_vla_ppr_flow(pprXmlFile: str, **kwargs) -> None:
        """Prefect flow wrapping :func:`executevlappr.executeppr`."""
        _apply_prefect_config()
        _register_dask_observer()
        return _run_vla_ppr_flow_impl(pprXmlFile, **kwargs)

    @flow(name=f'{_flow_name} Recipe', flow_run_name=_recipe_flow_name, log_prints=_log_prints, persist_result=False)
    def run_recipe_flow(**kwargs) -> Any:
        """Prefect flow wrapping :func:`recipereducer.reduce`."""
        _apply_prefect_config()
        _register_dask_observer()
        return _run_recipe_flow_impl(**kwargs)

    @flow(name=f'{_flow_name} Named Tasks', log_prints=_log_prints)
    def run_named_tasks_flow(tasks: Any) -> Any:
        """Prefect flow wrapping :func:`recipereducer.run_named_tasks`."""
        _apply_prefect_config()
        _register_dask_observer()
        return _run_named_tasks_flow_impl(tasks)

else:
    # Fallback: plain functions without Prefect decorators.
    run_ppr_flow = _run_ppr_flow_impl  # type: ignore[assignment]
    run_vla_ppr_flow = _run_vla_ppr_flow_impl  # type: ignore[assignment]
    run_recipe_flow = _run_recipe_flow_impl  # type: ignore[assignment]
    run_named_tasks_flow = _run_named_tasks_flow_impl  # type: ignore[assignment]
