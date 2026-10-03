from __future__ import annotations

import os
from typing import Any

import pipeline.infrastructure as infrastructure
from pipeline.infrastructure.utils import get_obj_size, human_file_size

LOG = infrastructure.logging.get_logger(__name__)

__all__ = [
    'is_parsl_ready',
    'is_parsl_worker',
    'get_parsl_exec',
    'parallel_map',
    'ParslTask',
]

try:
    import parsl
    from parsl import python_app
    PARSL_AVAILABLE = True
except ImportError:
    PARSL_AVAILABLE = False
    parsl = None


def is_parsl_ready() -> bool:
    """Check if Parsl is initialized and ready for parallel task execution."""
    if not PARSL_AVAILABLE:
        return False

    try:
        # If Parsl has a dataflow kernel configured and not cleaning up, it is ready
        dfk = parsl.dfk()
        return dfk is not None and not getattr(dfk, 'cleanup_called', False)
    except Exception:
        return False


def is_parsl_worker() -> bool:
    """Check if the current process is executing as a Parsl worker."""
    if os.environ.get('PARSL_WORKER') == '1':
        return True
    if any(k in os.environ for k in ('PARSL_WORKER_RANK', 'PARSL_WORKER_POOL_ID', 'PARSL_WORKER_COUNT')):
        return True
    import sys
    if any('process_worker_pool' in arg for arg in sys.argv):
        return True
    return False


if PARSL_AVAILABLE:
    _PARSL_APPS: dict[tuple[int, str], Any] = {}

    def get_parsl_exec(app_name: str):
        """Return a cached Parsl App wrapper targeted to the appropriate executor pool."""
        dfk = parsl.dfk()
        dfk_id = id(dfk)
        key = (dfk_id, app_name)
        if key in _PARSL_APPS:
            return _PARSL_APPS[key]

        target_executors = ['tier0_executor'] if (dfk and 'tier0_executor' in dfk.executors) else 'all'

        def parsl_exec(tier0_executable, working_dir: str, casalog_file: str | None = None, log2term: bool | None = None):
            """Execute a pipeline tier0 task on a Parsl worker."""
            os.environ['PARSL_WORKER'] = '1'
            # Condor workers often start in scratch directories. We must explicitly change
            # back to the pipeline's working directory so relative paths and casalog work.
            os.chdir(working_dir)

            if casalog_file or log2term is not None:
                try:
                    from casaconfig import config
                    if casalog_file:
                        config.logfile = os.path.abspath(casalog_file)
                    if log2term is not None:
                        config.log2term = bool(log2term)
                except Exception:
                    pass
                try:
                    import casatasks
                    if casalog_file:
                        last_logfile = casatasks.casalog.logfile()
                        if casalog_file != last_logfile:
                            casatasks.casalog.setlogfile(casalog_file)
                            if last_logfile and os.path.exists(last_logfile) and last_logfile != casalog_file:
                                try:
                                    os.remove(last_logfile)
                                except OSError:
                                    pass
                    if log2term is not None:
                        casatasks.casalog.showconsole(bool(log2term))
                except Exception as e:
                    LOG.warning('Could not redirect worker casalog: %s', e)

            executable = tier0_executable.get_executable()
            ret = executable()

            return ret, tier0_executable

        parsl_exec.__name__ = app_name
        app = python_app(parsl_exec, executors=target_executors)
        _PARSL_APPS[key] = app
        return app

    class ParslTask:
        """Encapsulates the submission and retrieval of results from Parsl futures."""

        def __init__(self, executable):
            """Submits a tier0 executable to the Parsl engine."""
            LOG.debug('submitting a ParslTask %s to the parsl engine: %s',
                      executable, human_file_size(get_obj_size(executable)))

            task_cls = getattr(executable, 'task_cls', getattr(executable, '_Tier0PipelineTask__task_cls', None))
            if hasattr(executable, 'fn') and hasattr(executable.fn, '__name__'):
                app_name = f"Tier0_{executable.fn.__name__}"
            elif task_cls and hasattr(task_cls, '__name__'):
                app_name = f"Tier0_{task_cls.__name__}"
            else:
                app_name = f"Tier0_{executable.__class__.__name__}"

            # Obtain client-side casalog file and log2term to propagate to the worker
            casalog_file = None
            log2term = None
            try:
                from casaconfig import config
                casalog_file = getattr(config, 'logfile', None)
                log2term = getattr(config, 'log2term', None)
            except Exception:
                pass
            if not casalog_file:
                try:
                    import casatasks
                    casalog_file = casatasks.casalog.logfile()
                except Exception:
                    pass

            # We pass os.getcwd() to inform the worker of the correct execution directory
            parsl_app = get_parsl_exec(app_name)
            self.future = parsl_app(executable, os.getcwd(), casalog_file=casalog_file, log2term=log2term)

        def get_result(self):
            """Retrieves the result and merges CASA logs from the worker."""
            task_result, tier0_executable = self.future.result()

            LOG.debug('Received task execution result (%s) from a parsl worker for %s',
                      human_file_size(get_obj_size(task_result)), tier0_executable)

            self._merge_casa_commands(getattr(tier0_executable, 'logs', {}))
            return task_result

        def _merge_casa_commands(self, logs: dict[str, str] | None):
            """Merges CASA command logs from a worker into the client-side log."""
            if not isinstance(logs, dict):
                return
            client_cmdfile = logs.get('casa_commands')
            tier0_cmdfile = logs.get('casa_commands_tier0')

            if all(isinstance(f, str) and os.path.exists(f) for f in [client_cmdfile, tier0_cmdfile]):
                LOG.info('Merge %s into %s', tier0_cmdfile, client_cmdfile)
                with open(client_cmdfile, 'a', encoding='utf-8') as client:
                    with open(tier0_cmdfile, 'r', encoding='utf-8') as tier0:
                        client.write(tier0.read())
                    os.remove(tier0_cmdfile)
            else:
                LOG.debug('Cannot find Tier0 casa_commands.log; no merge needed')
else:
    # Dummy fallbacks for when Parsl is not installed
    def get_parsl_exec(app_name: str):
        raise NotImplementedError("Parsl is not installed in this environment.")

    class ParslTask:
        def __init__(self, executable):
            raise NotImplementedError("Parsl is not installed in this environment.")

        def get_result(self):
            pass


def parallel_map(fn, items: list) -> list:
    """Run fn(item) for each item, in parallel via Parsl when available, else sequentially.

    When Parsl is ready, submits each item as a python_app to tier0_executor and
    collects results. Falls back to a plain list comprehension when Parsl is not
    initialized or not installed (e.g. in background weblog workers).

    Workers receive the active casalog file and log2term settings so CASA output
    is routed to the pipeline's consolidated log rather than stray per-worker files.

    Args:
        fn: Picklable callable accepting a single item.
        items: Sequence of inputs to map over.

    Returns:
        List of results in the same order as items.
    """
    if not items:
        return []

    if not is_parsl_ready():
        return [fn(item) for item in items]

    dfk = parsl.dfk()
    target_executors = ['tier0_executor'] if 'tier0_executor' in dfk.executors else 'all'

    # Capture casalog settings from the orchestrator process to propagate to workers.
    casalog_file = None
    log2term = None
    try:
        from casaconfig import config as _cc
        casalog_file = getattr(_cc, 'logfile', None)
        log2term = getattr(_cc, 'log2term', None)
    except Exception:
        pass
    if not casalog_file:
        try:
            import casatasks as _ct
            casalog_file = _ct.casalog.logfile()
        except Exception:
            pass

    @python_app(executors=target_executors)
    def _parsl_apply(fn, item, casalog_file, log2term):
        import os as _os
        _os.environ['PARSL_WORKER'] = '1'
        if casalog_file or log2term is not None:
            try:
                from casaconfig import config as _cc
                if casalog_file:
                    _cc.logfile = _os.path.abspath(casalog_file)
                if log2term is not None:
                    _cc.log2term = bool(log2term)
            except Exception:
                pass
        return fn(item)

    futures = [_parsl_apply(fn, item, casalog_file, log2term) for item in items]
    return [f.result() for f in futures]
