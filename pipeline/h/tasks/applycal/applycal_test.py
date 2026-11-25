"""Unit tests for SerialApplycal.prepare's data selections (PIPE-2610).

The calibration hif_applycal applies, whether written to a CASA callibrary or
passed as per-selection applycal jobs, must come from the calstate's
application partition: per caltable pairwise disjoint in field x spw x intent
and faithful to what was registered. The calstate reaches it through
callibrary.fix_cycle0_data_selection, which these tests run for real.

The context and MeasurementSet are the stubs from
pipeline.infrastructure.callibrary_test, with the driving fragmented
bandpass + sparse renorm registrations; see that module for why a stub MS.
The Inputs are a spec'd MagicMock and the executor records jobs instead of
running them, so prepare() never calls CASA applycal.
"""

import collections
from unittest.mock import MagicMock

import pytest

from pipeline.infrastructure import callibrary
from pipeline.infrastructure.callibrary_test import (
    _LEGACY_FLAG,
    _cell_set,
    _cells_by_gaintable,
    _FakeContext,
    _param_key,
    _queried_stacks_by_cell,
    _without_legacy_flag,  # noqa: F401 -- an autouse fixture
    _written_cells_by_gaintable,
    fragmented_calstate,  # noqa: F401 -- a fixture
)

from .applycal import ApplycalInputs, SerialApplycal

# MJD 60000 (2023-02-25): after Cycle 0, so fix_cycle0_data_selection does not
# take its Cycle 0 path
_POST_CYCLE0_EPOCH = {'m0': {'unit': 'd', 'value': 60000.0}, 'refer': 'UTC', 'type': 'epoch'}


@pytest.fixture
def applycal_context(fragmented_calstate):  # noqa: F811 -- the imported fixture
    """A fake context whose callibrary holds the fragmented registrations.

    The registrations are active calibration. Returns the context, its MS and
    the registered CalApplications.
    """
    ms, _, registered = fragmented_calstate
    ms.start_time = _POST_CYCLE0_EPOCH

    context = _FakeContext(ms)
    context.task_counter = 1
    context.subtask_counter = 0
    context.callibrary = callibrary.IntervalCalLibrary(context)
    for calapp in registered:
        context.callibrary.add(calapp.calto, calapp.calfrom)

    return context, ms, registered


@pytest.fixture
def written_callibrary(monkeypatch, tmp_path):
    """Replace CASA's applycaltocallib with a recorder that creates the file.

    jobs_with_calapply only schedules applycal when the file exists. Runs in
    tmp_path, where prepare() writes its callibrary and calstate files.
    Returns the recorded calls, one dict of keyword arguments per entry.
    """
    monkeypatch.chdir(tmp_path)
    calls = []

    def record(filename, **kwargs):
        calls.append({'filename': filename, **kwargs})
        (tmp_path / filename).touch()

    monkeypatch.setattr(callibrary, 'applycaltocallib', record)
    return calls


def _run_prepare(context, ms):
    """Run SerialApplycal.prepare() over the whole MS with flag summaries off.

    Returns the result and the jobs handed to the executor, in order.
    """
    inputs = MagicMock(spec=ApplycalInputs)
    inputs.context = context
    inputs.ms = ms
    inputs.vis = ms.name
    inputs.field = ''
    inputs.spw = ''
    inputs.intent = ''
    inputs.antenna = ''
    inputs.applymode = 'calflagstrict'
    inputs.flagsum = False
    # jobs_without_calapply sets field/spw/intent on the inputs before each job
    inputs.to_casa_args.side_effect = lambda: {
        'vis': inputs.vis,
        'field': inputs.field,
        'spw': inputs.spw,
        'intent': inputs.intent,
    }

    task = SerialApplycal(inputs)
    jobs = []
    task._executor = MagicMock()
    task._executor.execute.side_effect = jobs.append

    return task.prepare(), jobs


def test_callibrary_branch_writes_disjoint_faithful_entries(applycal_context, written_callibrary, monkeypatch):
    """The callibrary branch writes the application partition.

    Per caltable the written entries are pairwise disjoint in field x spw x
    intent, so CASA does not abort on a duplicate MSCalPatchKey, and together
    cover exactly the registered cells. A single applycal job runs the file.
    """
    monkeypatch.delenv('DISABLE_CASA_CALLIBRARY', raising=False)
    context, ms, registered = applycal_context

    _, jobs = _run_prepare(context, ms)

    assert [(job.fn_name, job.kw['docallib'], job.kw['callib']) for job in jobs] == [
        ('applycal', True, written_callibrary[0]['filename'])
    ]

    written = _written_cells_by_gaintable(ms, written_callibrary)
    for gaintable, cell_sets in written.items():
        for i, cells_a in enumerate(cell_sets):
            for cells_b in cell_sets[i + 1 :]:
                overlap = cells_a & cells_b
                assert not overlap, f'{gaintable}: overlapping written cells {overlap}'

    expected = {
        gaintable: set().union(*cell_sets) for gaintable, cell_sets in _cells_by_gaintable(ms, registered).items()
    }
    assert {gaintable: set().union(*cell_sets) for gaintable, cell_sets in written.items()} == expected


def test_calstate_file_lists_the_same_entries_as_the_written_callibrary(
    applycal_context, written_callibrary, monkeypatch, tmp_path
):
    """The .calstate snapshot prepare() writes alongside the callibrary file lists the same entries.

    The callibrary branch computes application_partition() once and both
    files come from it.
    """
    monkeypatch.delenv('DISABLE_CASA_CALLIBRARY', raising=False)
    context, ms, _ = applycal_context

    _run_prepare(context, ms)

    calstate_file = tmp_path / f'{ms.name}.s{context.task_counter}.{context.subtask_counter}.calstate'
    assert calstate_file.exists()
    lines = [line for line in calstate_file.read_text().splitlines() if line.startswith('applycal(')]
    assert lines

    # Parsed as plain literals (not CalApplication.from_export, which guesses
    # a caltype from the gaintable name or opens the table -- irrelevant
    # here, since only the data selection and gaintable list are compared).
    parsed = [eval(line.replace('applycal(', 'dict(')) for line in lines]
    from_file = _entries(_written_cells_by_gaintable(ms, parsed))
    written = _entries(_written_cells_by_gaintable(ms, written_callibrary))
    assert from_file == written


def test_non_callibrary_branch_runs_disjoint_faithful_jobs(applycal_context, written_callibrary, monkeypatch):
    """The per-selection branch runs one applycal job per partition entry.

    With the CASA callibrary disabled, prepare() passes each entry's selection
    and caltables to its own applycal job. Per caltable the job selections are
    pairwise disjoint in field x spw x intent, so no cell is calibrated twice
    by the same table, and together cover exactly the registered cells.
    """
    monkeypatch.setenv('DISABLE_CASA_CALLIBRARY', '1')
    context, ms, registered = applycal_context

    _, jobs = _run_prepare(context, ms)

    assert not written_callibrary
    assert jobs
    assert all(job.fn_name == 'applycal' and 'docallib' not in job.kw for job in jobs)

    # the job keywords carry the same selection and gaintable keys as a
    # recorded callibrary entry, with the pipeline's intent spelling
    run = _written_cells_by_gaintable(ms, [job.kw for job in jobs])
    for gaintable, cell_sets in run.items():
        for i, cells_a in enumerate(cell_sets):
            for cells_b in cell_sets[i + 1 :]:
                overlap = cells_a & cells_b
                assert not overlap, f'{gaintable}: overlapping job cells {overlap}'

    expected = {
        gaintable: set().union(*cell_sets) for gaintable, cell_sets in _cells_by_gaintable(ms, registered).items()
    }
    assert {gaintable: set().union(*cell_sets) for gaintable, cell_sets in run.items()} == expected


def test_applied_calapps_are_disjoint_and_faithful(applycal_context, written_callibrary, monkeypatch):
    """results.applied, which merge_with_context marks applied, is the partition.

    Per caltable the applied CalApplications are pairwise disjoint in field x
    spw x intent, so no cell is marked applied twice by the same table, and
    together cover exactly the registered cells.
    """
    monkeypatch.delenv('DISABLE_CASA_CALLIBRARY', raising=False)
    context, ms, registered = applycal_context

    result, _ = _run_prepare(context, ms)

    assert result.applied
    applied = _cells_by_gaintable(ms, result.applied)
    for gaintable, cell_sets in applied.items():
        for i, cells_a in enumerate(cell_sets):
            for cells_b in cell_sets[i + 1 :]:
                overlap = cells_a & cells_b
                assert not overlap, f'{gaintable}: overlapping applied cells {overlap}'

    expected = {
        gaintable: set().union(*cell_sets) for gaintable, cell_sets in _cells_by_gaintable(ms, registered).items()
    }
    assert {gaintable: set().union(*cell_sets) for gaintable, cell_sets in applied.items()} == expected


def test_accepting_the_result_moves_each_cells_stack_from_active_to_applied(
    applycal_context, written_callibrary, monkeypatch
):
    """merge_with_context marks every applied cell's calibration applied.

    Queried one cell at a time, the active state is left with no calibration,
    since the task applied everything registered, and the applied state holds
    each cell's registered stack once and in registration order.
    """
    monkeypatch.delenv('DISABLE_CASA_CALLIBRARY', raising=False)
    context, ms, registered = applycal_context

    result, _ = _run_prepare(context, ms)
    # execute() would attach the inputs; the data column bookkeeping that
    # follows the marking reads them, and the stub MS has no data columns
    result.inputs = {'vis': ms.name}
    ms.get_data_column = MagicMock(return_value=None)
    ms.set_data_column = MagicMock()
    result.merge_with_context(context)

    expected = collections.defaultdict(list)
    for calapp in registered:
        for cell in _cell_set(ms, calapp):
            expected[cell].extend((cf.gaintable, _param_key(cf)) for cf in calapp.calfrom)
    active = _queried_stacks_by_cell(context, context.callibrary.active, ms)
    applied = _queried_stacks_by_cell(context, context.callibrary.applied, ms)
    assert set(expected) == set(applied)
    assert active == {cell: [] for cell in expected}
    assert applied == {cell: [stack] for cell, stack in expected.items()}


def _entries(cells_by_gaintable):
    """Count each caltable's entries by the cells they cover, ignoring order: results.applied is a set."""
    return {
        gaintable: collections.Counter(map(frozenset, cell_sets)) for gaintable, cell_sets in cells_by_gaintable.items()
    }


def test_legacy_flag_reverts_what_prepare_applies_and_writes(applycal_context, written_callibrary, monkeypatch):
    """With the legacy flag, prepare() applies and writes the merged() entries.

    Both results.applied and the written callibrary follow the legacy
    consolidation of the calstate prepare() works on, overlaps included.
    Without the flag they must differ, or the fixture could not tell.
    """
    monkeypatch.delenv('DISABLE_CASA_CALLIBRARY', raising=False)
    context, ms, _ = applycal_context
    result, _ = _run_prepare(context, ms)
    applied_by_default = _cells_by_gaintable(ms, result.applied)
    written_callibrary.clear()

    monkeypatch.setenv(_LEGACY_FLAG, '1')
    result, _ = _run_prepare(context, ms)

    calstate = callibrary.fix_cycle0_data_selection(
        context, context.callibrary.get_calstate(callibrary.CalTo(vis=ms.name))
    )
    legacy = _cells_by_gaintable(
        ms, [callibrary.CalApplication(calto, calfroms) for calto, calfroms in calstate.merged(hide_empty=True).items()]
    )
    assert _entries(_cells_by_gaintable(ms, result.applied)) == _entries(legacy)
    assert _written_cells_by_gaintable(ms, written_callibrary) == legacy
    assert _entries(applied_by_default) != _entries(legacy)
