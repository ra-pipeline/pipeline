"""Unit tests for FlagTargetsALMA logical MS and SubMS support."""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pipeline.domain import DataType
from pipeline.infrastructure.launcher import Context
from pipeline.hifa.tasks.flagging.flagtargetsalma import (
    FlagTargetsALMAInputs,
    FlagTargetsALMAResults,
    SerialFlagTargetsALMA,
)


def test_filetemplate_resolution(tmp_path):
    """Test filetemplate resolution with parent and output_dir fallbacks."""
    context = Context()
    context.output_dir = str(tmp_path)
    parent_template = tmp_path / "uid___parent.flagtargetstemplate.txt"
    parent_template.write_text("# parent template\n")

    parent_ms = SimpleNamespace(
        name=str(tmp_path / "uid___parent.ms"),
        basename="uid___parent.ms",
        origin_ms=None,
        parent_ms=None,
    )

    # SubMS pointing to parent_ms
    sub_ms = SimpleNamespace(
        name=str(tmp_path / "uid___parent.helms30.spw0.ms"),
        basename="uid___parent.helms30.spw0.ms",
        parent_ms=parent_ms,
        origin_ms=str(tmp_path / "uid___parent.ms"),
    )

    context.observing_run.get_ms = lambda name: sub_ms

    inputs = FlagTargetsALMAInputs(context, vis=sub_ms.name, output_dir=str(tmp_path))
    assert inputs.filetemplate == str(parent_template)


def test_filter_flag_commands_for_subms():
    """Test filtering and adapting flagging commands for a component SubMS slice."""
    sub16 = SimpleNamespace(
        real_spw_id=16,
        virtual_spw_id=0,
        source_name='helms30',
        get_fields=lambda: [SimpleNamespace(id=1, name='helms30')],
    )

    flag_cmds = [
        "mode='summary' name='before'",
        "mode='manual' spw='16:10~50' antenna='PM02'",
        "mode='manual' spw='18:10~50' antenna='PM02'",
        "mode='manual' field='other_source' antenna='PM02'",
        "mode='manual' field='helms30' antenna='PM02'",
        "mode='manual' antenna='DV01'",
        "mode='summary' name='template'",
    ]

    filtered = SerialFlagTargetsALMA._filter_flag_commands_for_subms(flag_cmds, sub16)

    assert "mode='summary' name='before'" in filtered
    assert "mode='manual' spw='16:10~50' antenna='PM02'" in filtered
    assert not any("18:10~50" in c for c in filtered)
    assert not any("other_source" in c for c in filtered)
    assert "mode='manual' field='helms30' antenna='PM02'" in filtered
    assert "mode='manual' antenna='DV01'" in filtered
    assert "mode='summary' name='template'" in filtered


def test_merge_flagdata_summaries():
    """Test merging SubMS flagdata summary dictionaries with SPW remapping."""
    accum = {}
    sub16 = SimpleNamespace(real_spw_id=16)
    sub18 = SimpleNamespace(real_spw_id=18)

    rep_sub16 = {
        'report0': {
            'name': 'before',
            'type': 'summary',
            'flagged': 100.0,
            'total': 1000.0,
            'scan': {'10': {'flagged': 100.0, 'total': 1000.0}},
            'spw': {'0': {'flagged': 100.0, 'total': 1000.0}},
            'antenna': {'PM02': {'flagged': 100.0, 'total': 1000.0}},
        }
    }

    rep_sub18 = {
        'report0': {
            'name': 'before',
            'type': 'summary',
            'flagged': 250.0,
            'total': 2000.0,
            'scan': {'10': {'flagged': 250.0, 'total': 2000.0}},
            'spw': {'0': {'flagged': 250.0, 'total': 2000.0}},
            'antenna': {'PM02': {'flagged': 250.0, 'total': 2000.0}},
        }
    }

    SerialFlagTargetsALMA._merge_flagdata_summaries(accum, rep_sub16, sub16)
    SerialFlagTargetsALMA._merge_flagdata_summaries(accum, rep_sub18, sub18)

    assert accum['report0']['flagged'] == 350.0
    assert accum['report0']['total'] == 3000.0
    assert accum['report0']['scan']['10']['flagged'] == 350.0
    assert accum['report0']['antenna']['PM02']['flagged'] == 350.0

    # Verify SPW 0 in each slice is remapped to its real parent SPW ID (16 and 18)
    assert '16' in accum['report0']['spw']
    assert accum['report0']['spw']['16']['flagged'] == 100.0
    assert '18' in accum['report0']['spw']
    assert accum['report0']['spw']['18']['flagged'] == 250.0


def test_serial_flagtargets_logical_ms_prepare(tmp_path):
    """Test SerialFlagTargetsALMA.prepare execution when inputs.ms is a logical MS."""
    context = Context()
    context.output_dir = str(tmp_path)

    sub1 = SimpleNamespace(
        name=str(tmp_path / "sub1.ms"),
        basename="sub1.ms",
        real_spw_id=16,
        virtual_spw_id=0,
        source_name='target1',
        get_fields=lambda: [],
    )
    sub2 = SimpleNamespace(
        name=str(tmp_path / "sub2.ms"),
        basename="sub2.ms",
        real_spw_id=18,
        virtual_spw_id=1,
        source_name='target1',
        get_fields=lambda: [],
    )

    logical_ms = SimpleNamespace(
        name=str(tmp_path / "targets.ms"),
        basename="targets.ms",
        is_logical=True,
        has_subms=lambda: True,
        get_subms=lambda: [sub1, sub2],
        sub_mses=[sub1, sub2],
    )

    context.observing_run.get_ms = lambda name: logical_ms

    inputs = FlagTargetsALMAInputs(context, vis=logical_ms.name, output_dir=str(tmp_path))
    task = SerialFlagTargetsALMA(inputs)

    # Mock executor
    mock_executor = MagicMock()
    def mock_exec(job):
        vis = job.kw.get('vis')
        return {
            'report0': {
                'name': 'before',
                'type': 'summary',
                'flagged': 50.0,
                'total': 500.0,
                'spw': {'0': {'flagged': 50.0, 'total': 500.0}},
            },
            'report1': {
                'name': 'template',
                'type': 'summary',
                'flagged': 60.0,
                'total': 500.0,
                'spw': {'0': {'flagged': 60.0, 'total': 500.0}},
            },
        }
    mock_executor.execute.side_effect = mock_exec
    task._executor = mock_executor

    result = task.prepare()

    assert isinstance(result, FlagTargetsALMAResults)
    assert len(result.summaries) == 2
    # Combined across both slices: total = 1000, flagged = 100 before, 120 after template
    assert result.summaries[0]['name'] == 'before'
    assert result.summaries[0]['total'] == 1000.0
    assert result.summaries[0]['flagged'] == 100.0

    assert result.summaries[1]['name'] == 'template'
    assert result.summaries[1]['total'] == 1000.0
    assert result.summaries[1]['flagged'] == 120.0

    # Ensure per-slice cmd files were written
    assert os.path.exists(tmp_path / "sub1.flagtargetscmds.txt")
    assert os.path.exists(tmp_path / "sub2.flagtargetscmds.txt")
    assert os.path.exists(tmp_path / "targets.flagtargetscmds.txt")

