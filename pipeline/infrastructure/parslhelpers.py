from __future__ import annotations

import os
from typing import Any

import pipeline.infrastructure as infrastructure
from pipeline.infrastructure.utils import get_obj_size, human_file_size

LOG = infrastructure.logging.get_logger(__name__)

__all__ = [
    'is_parsl_ready',
    'get_parsl_exec',
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

        def parsl_exec(tier0_executable, working_dir: str):
            """Execute a pipeline tier0 task on a Parsl worker."""
            # Condor workers often start in scratch directories. We must explicitly change
            # back to the pipeline's working directory so relative paths and casalog work.
            os.chdir(working_dir)

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

            app_name = executable.__class__.__name__
            if hasattr(executable, 'fn') and hasattr(executable.fn, '__name__'):
                app_name = f"Tier0_{executable.fn.__name__}"
            elif hasattr(executable, 'task_cls') and hasattr(executable.task_cls, '__name__'):
                app_name = f"Tier0_{executable.task_cls.__name__}"

            # We pass os.getcwd() to inform the worker of the correct execution directory
            parsl_app = get_parsl_exec(app_name)
            self.future = parsl_app(executable, os.getcwd())

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
