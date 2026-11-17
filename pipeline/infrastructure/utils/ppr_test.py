"""Tests for Pipeline Processing Request utilities."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.infrastructure import exceptions

from . import ppr


def test_write_pipeline_early_exit_file_includes_stop_details(tmp_path: Path) -> None:
    """A requested error sentinel contains machine-readable stop details."""
    early_exit = exceptions.PipelineEarlyExit('data require manual review', create_errorfile=True)

    path = ppr.write_pipeline_early_exit_file(
        str(tmp_path),
        early_exit,
        task_name='hif_makeimlist',
        stage_number=22,
    )

    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    assert payload == {
        'message': 'data require manual review',
        'stage': 22,
        'task': 'hif_makeimlist',
        'type': 'pipeline_early_exit',
    }
