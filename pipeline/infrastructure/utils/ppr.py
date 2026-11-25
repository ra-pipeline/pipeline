"""
The ppr module contains utility functions useful to PPR processing functions.

TODO There is a lot of duplication between executeppr and vlaexecuteppr. Can
this module be eliminated if a common PPR base class was created?
"""
from __future__ import annotations

import datetime
import json
import os
from typing import TYPE_CHECKING
from xml.dom import minidom

from .. import logging, task_registry, workflow

if TYPE_CHECKING:
    from ..launcher import Context

__all__ = [
    'check_ppr',
    'write_errorexit_file',
    'write_pipeline_early_exit_file',
    'write_pipeline_early_exit_file_if_requested',
]

LOG = logging.get_logger(__name__)


def check_ppr(pprfile: str) -> bool:
    """Check PPR to make sure all tasks exist in the CASA task dictionary.

    Compares the <Command> elements of the PPR to the keys of
    the CASA task dictionary.  This is useful as a quick sanity check
    before executing the pipeline.

    Args:
        pprfile: A path to the PPR file (string).
                 e.g. 'PPR_VLAT003.xml' or 'mydata/working/PPR_VLAT003.xml'

    Returns:
        False on error.
        True  on success.
    """
    casatasks = {m.casa_task for m in task_registry.task_map}
    try:
        doc = minidom.parse(pprfile)
    except (IOError, Exception):
        LOG.info('Please provide a valid xml PPR file as input and try again.')
        return False

    tasks_in_ppr = {str(x.firstChild.data) for x in doc.getElementsByTagName('Command')}

    undefined_tasks = (tasks_in_ppr - casatasks)
    for suspect_task in undefined_tasks:
        LOG.info("{} is not a recognized CASA task.  Check your PPR and try again.".format(suspect_task))

    if not undefined_tasks:
        LOG.info("Passed.  All tasks exist in the CASA task dictionary.")
        return True
    else:
        return False


def write_errorexit_file(path: str, root: str, extension: str, content: str | None = None) -> str:
    """Create a timestamped workflow error sentinel.

    Args:
        path: Directory where the sentinel is created.
        root: Filename root.
        extension: Filename extension.
        content: Optional content written to the sentinel.

    Returns:
        The sentinel path, or an empty string if creation failed.
    """
    # Get formatted UTC time
    now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S')

    # Root name is composed of root, the current UTC time, and the extension
    basename = root + '-' + now + '.' + extension

    # Generate the root name
    if path:
        errorfile = os.path.join(path, basename)
    else:
        errorfile = basename
    with open(errorfile, 'w', encoding='utf-8') as stream:
        if content:
            stream.write(content.rstrip() + '\n')

    if os.path.exists(errorfile):
        return errorfile
    else:
        return ''


def write_pipeline_early_exit_file(
    path: str,
    early_exit: workflow.PipelineEarlyExitRequest,
    *,
    task_name: str | None = None,
    stage_number: int | None = None,
) -> str:
    """Create an ``errorexit`` sentinel describing a workflow stop request.

    Args:
        path: Directory where the sentinel is created.
        early_exit: Workflow stop request to describe.
        task_name: Task that requested the stop, when known.
        stage_number: Pipeline stage that requested the stop, when known.

    Returns:
        Path to the created sentinel.
    """
    content = json.dumps(
        {
            'type': 'pipeline_early_exit',
            'message': str(early_exit),
            'task': task_name,
            'stage': stage_number,
        },
        sort_keys=True,
    )
    return write_errorexit_file(path, 'errorexit', 'txt', content)


def write_pipeline_early_exit_file_if_requested(
    path: str,
    context: Context,
    *,
    task_name: str | None = None,
    stage_number: int | None = None,
) -> str:
    """Write the requested workflow stop sentinel, if enabled.

    Args:
        path: Directory where the sentinel is created.
        context: Context containing the workflow stop request.
        task_name: Task that requested the stop, when known.
        stage_number: Pipeline stage that requested the stop, when known.

    Returns:
        Path to the created sentinel, or an empty string when none is requested.
    """
    early_exit = context.pipeline_early_exit
    if not context.pipeline_early_exit_active or early_exit is None or not early_exit.create_errorfile:
        return ''

    return write_pipeline_early_exit_file(
        path,
        early_exit,
        task_name=task_name,
        stage_number=stage_number,
    )
