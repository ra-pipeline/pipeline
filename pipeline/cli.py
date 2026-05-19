from __future__ import annotations

from typing import TYPE_CHECKING

from .h.cli import *
from .hif.cli import *
from .hifa.cli import *
from .hifv.cli import *
from .hsd.cli import *
from .hsdn.cli import *

if TYPE_CHECKING:
    from collections.abc import Callable


def get_pipeline_task_with_name(task_name: str) -> Callable:
    """Return Pipeline CLI task with specified name.

    Args:
        task_name: Name of the task.

    Returns:
        Pipeline CLI task
    """
    return globals()[task_name]
