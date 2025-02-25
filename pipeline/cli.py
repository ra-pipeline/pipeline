from typing import Callable

from .h.cli import *
from .hif.cli import *
from .hifa.cli import *
from .hifv.cli import *
from .hsd.cli import *
from .hsdn.cli import *

from prefect import flow, task

def get_pipeline_task_with_name(task_name: str) -> Callable:
    """Return Pipeline CLI task with specified name.

    Args:
        task_name: Name of the task.

    Returns:
        Pipeline CLI task
    """
    return flow(globals()[task_name], log_prints=True, name=task_name)
