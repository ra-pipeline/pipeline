"""Unit tests for IntervalCalState's application partition (PIPE-2610).

IntervalCalState gives two views of the registered calibration.
application_partition() is what gets applied, or written out as applycal
instructions such as the exported .callibrary, so it must partition the
registered space: per caltable its entries are pairwise disjoint in field x
spw x intent (CASA's callibrary applycal aborts on an overlap) and faithful to
what was registered, every cell keeps its full ordered caltable stack, exact
duplicate applications collapse, and conflicting ones raise a ValueError that
names the caltable and the data selection. merged() is the grouping view used
for solver jobs, the weblog and logging; it keeps its long-standing
consolidation, which may overlap, and on a calstate that is not fragmented the
two views must agree. Because each merged() entry becomes one solver job, a
calibration registered over several fields and spws stays one entry even when
the cells holding data do not form a rectangle. And because merged(),
as_applycal() and str() only describe the calstate, a conflict the partition
rejects passes through them as registered instead of raising.

The driving scenario is a broad hifa_bandpass-style calapp plus sparse
per-field/per-spw TARGET renorm calapps, as
hifa.tasks.renorm.renorm.SerialRenorm._get_calapps registers them, together
with the selections the exported .callibrary of MOUS uid___A002_Xe1f219_X9dbf
aborted on.

The fixture is a hand-built stub MeasurementSet rather than a real
pipeline.domain.MeasurementSet: the real class's get_fields/get_spectral_windows
delegate to utils.field_arg_to_id/spw_arg_to_id, which default to CASA
msselect against an on-disk MS (USE_CASA_PARSING_ROUTINES=True) and would
fail for a fake one, so the stub implements its own minimal selection
parsing instead.
"""

import collections
import re
import types

import pytest

from . import callibrary
from .callibrary import CalApplication, CalFrom, CalTo, IntervalCalState


class _StubAntenna:
    def __init__(self, id):
        self.id = id


class _StubSpectralWindow:
    def __init__(self, id):
        self.id = id


class _StubField:
    def __init__(self, id, name, intents):
        self.id = id
        self.name = name
        self.intents = set(intents)
        self.valid_spws = set()  # filled in by _build_ms() once spws exist


class _StubScan:
    def __init__(self, id, intents, fields, spws):
        self.id = id
        self.intents = set(intents)
        self.fields = set(fields)
        self.spws = set(spws)


def _expand_spw_ranges(arg):
    """Expand a CASA-style '0,1~3' spw selection string to a set of ints."""
    ids = set()
    for token in arg.split(','):
        if '~' in token:
            lo, hi = (int(x) for x in token.split('~'))
            ids.update(range(lo, hi + 1))
        else:
            ids.add(int(token))
    return ids


def _casa_intent(intent):
    """The stub MS's obs_mode for a pipeline intent.

    Deliberately not the pipeline spelling, so a test can tell the export
    converted the intent.
    """
    return f'{intent}#ON_SOURCE'


class _StubMeasurementSet:
    """Minimal stand-in for domain.MeasurementSet.

    Exposes only what the callibrary export path
    (IntervalCalState.create_from_context, CalToIntervalAdapter,
    get_calstate_shape) reads.
    """

    def __init__(self, name, fields, spectral_windows, antennas, scans):
        self.name = name
        self.fields = fields
        self.spectral_windows = spectral_windows
        self.antennas = antennas
        self.scans = scans

    @property
    def basename(self):
        return self.name

    @property
    def intents(self):
        return {intent for field in self.fields for intent in field.intents}

    def get_original_intent(self, intent):
        return {_casa_intent(i) for i in intent.split(',') if i}

    def get_antenna(self, search_term=''):
        # This fixture never registers an antenna-restricted CalTo.
        return self.antennas

    def get_fields(self, task_arg=None, **_ignored):
        if task_arg in (None, ''):
            return list(self.fields)
        if isinstance(task_arg, int):
            return [f for f in self.fields if f.id == task_arg]
        names = {n.strip() for n in str(task_arg).split(',')}
        return [f for f in self.fields if f.name in names]

    def get_spectral_windows(self, task_arg='', science_windows_only=True, **_ignored):
        del science_windows_only  # every spw in this fixture counts as "science"
        if task_arg in (None, ''):
            return list(self.spectral_windows)
        if isinstance(task_arg, int):
            return [s for s in self.spectral_windows if s.id == task_arg]
        ids = _expand_spw_ranges(str(task_arg))
        return [s for s in self.spectral_windows if s.id in ids]

    def get_scans(self, field=None, spw=None):
        pool = list(self.scans)
        if field is not None:
            pool = [s for s in pool if field in {f.id for f in s.fields}]
        if spw is not None:
            pool = [s for s in pool if spw in {sp.id for sp in s.spws}]
        return pool


class _FakeObservingRun:
    def __init__(self, ms):
        self._ms = ms

    def get_ms(self, name=None, intent=None):
        return self._ms

    @property
    def measurement_sets(self):
        return [self._ms]


class _FakeContext:
    def __init__(self, ms):
        self.observing_run = _FakeObservingRun(ms)


def _build_ms(n_targets=2, n_spws=4):
    """1 bandpass calibrator + ``n_targets`` target fields x ``n_spws`` spws x 2 intents.

    Defaults give the small 3-field/4-spw shape; the fragmented fixture
    asks for a wider one so the greedy merge has room to misbehave. The
    name encodes the shape: get_calstate_shape caches on it, so two shapes
    sharing a name would share one cached shape.
    """
    spws = [_StubSpectralWindow(i) for i in range(n_spws)]

    bp = _StubField(0, 'BP', intents={'BANDPASS'})
    targets = [_StubField(i + 1, 'T{}'.format(i + 1), intents={'TARGET'}) for i in range(n_targets)]
    fields = [bp, *targets]
    for field in fields:
        field.valid_spws = set(spws)

    scans = [_StubScan(1, intents={'BANDPASS'}, fields={bp}, spws=spws)]
    for i, target in enumerate(targets):
        scans.append(_StubScan(i + 2, intents={'TARGET'}, fields={target}, spws=spws))

    return _StubMeasurementSet(f'fake_{n_targets}x{n_spws}.ms', fields, spws, [_StubAntenna(0)], scans)


def _build_layout_ms(name, rows):
    """Stub MS from ``(field id, field name, intents, spw ids)`` rows, one scan per field, so a field has data only in the spws listed for it.

    Give every shape its own ``name``: get_calstate_shape caches on it.
    """
    spws = {
        spw_id: _StubSpectralWindow(spw_id) for spw_id in sorted({spw_id for *_, spw_ids in rows for spw_id in spw_ids})
    }
    fields, scans = [], []
    for field_id, field_name, intents, spw_ids in rows:
        field = _StubField(field_id, field_name, intents=intents)
        field.valid_spws = {spws[spw_id] for spw_id in spw_ids}
        fields.append(field)
        scans.append(
            _StubScan(len(scans) + 1, intents=intents, fields={field}, spws=[spws[spw_id] for spw_id in spw_ids])
        )
    return _StubMeasurementSet(name, fields, list(spws.values()), [_StubAntenna(0)], scans)


def _cell_set(ms, calapp):
    """Resolve a CalApplication's selection to the concrete set of (field, spw, intent) cells it covers, restricted to combinations that actually exist: a field only carries its own intents and its own spws.

    Without that restriction a broad ``intent=''`` selection would claim
    every intent for every field (e.g. BANDPASS cells on a target).
    """
    selected_spws = {s.id for s in ms.get_spectral_windows(task_arg=calapp.spw, science_windows_only=False)}
    selected_intents = set(calapp.intent.split(',')) if calapp.intent else set(ms.intents)

    cells = set()
    for field in ms.get_fields(task_arg=calapp.field):
        field_spws = {s.id for s in field.valid_spws} & selected_spws
        field_intents = field.intents & selected_intents
        for spw in field_spws:
            for intent in field_intents:
                cells.add((field.id, spw, intent))
    return cells


def _cells_by_gaintable(ms, calapps):
    """Map each caltable name to the list of cell sets covering it, one per consolidated entry that references it.

    A single entry can reference several caltables (``calapp.gaintable``
    is then a list, not a string), so key on each CalFrom individually.
    """
    by_gaintable = collections.defaultdict(list)
    for calapp in calapps:
        cells = _cell_set(ms, calapp)
        for calfrom in calapp.calfrom:
            by_gaintable[calfrom.gaintable].append(cells)
    return by_gaintable


def _partition_calapps(calstate):
    """The application view of a calstate: the entries written out as applycal instructions, which must partition the registered space."""
    return [
        CalApplication(calto, calfroms) for calto, calfroms in calstate.application_partition(hide_empty=True).items()
    ]


def _merged_calapps(calstate):
    """The legacy grouping view of a calstate, used for solver job grouping, the weblog and logging.

    It may overlap and must not raise.
    """
    return [CalApplication(calto, calfroms) for calto, calfroms in calstate.merged(hide_empty=True).items()]


def _grouping(calapps):
    """Count entries by (fields, spws, intent, ordered caltable stack), ignoring how the selection strings happen to be spelled ('F2,F1', '0~1') but not how many entries there are."""
    return collections.Counter(
        (
            frozenset(calapp.field.split(',')),
            frozenset(_expand_spw_ranges(calapp.spw)),
            calapp.intent,
            tuple(cf.gaintable for cf in calapp.calfrom),
        )
        for calapp in calapps
    )


def _param_key(calfrom):
    """Identify a CalFrom's apply-parameter set (everything bar the caltable name)."""
    return (calfrom.gainfield, calfrom.interp, tuple(calfrom.spwmap), calfrom.calwt)


def _coverage_by_gaintable(ms, calapps):
    """Map each caltable to ``{(field, spw, intent): parameter key}`` -- the per-cell calibration the export prescribes.

    Entry grouping is irrelevant here; only which cell gets which caltable
    with which parameters. Overlaps (one cell, one caltable, twice) are the
    disjointness test's job, so the last write wins.
    """
    coverage = collections.defaultdict(dict)
    for calapp in calapps:
        cells = _cell_set(ms, calapp)
        for calfrom in calapp.calfrom:
            for cell in cells:
                coverage[calfrom.gaintable][cell] = _param_key(calfrom)
    return coverage


def _stacks_by_cell(ms, calapps):
    """Map each (field, spw, intent) cell to the ordered caltable stacks the consolidated entries prescribe for it -- one list element per entry that covers the cell.

    A partition of the registered space yields exactly one stack per cell;
    an overlap yields more than one.
    """
    stacks = collections.defaultdict(list)
    for calapp in calapps:
        stack = [cf.gaintable for cf in calapp.calfrom]
        for cell in _cell_set(ms, calapp):
            stacks[cell].append(stack)
    return stacks


def _register(calstate, context, calapp):
    return calstate + IntervalCalState.from_calapplication(context, calapp.calto, calapp.calfrom)


_LEGACY_FLAG = 'PIPE2610_LEGACY_CONSOLIDATE'


@pytest.fixture(autouse=True)
def _without_legacy_flag(monkeypatch):
    """Run every test on the default consolidation, whatever the environment says: with the flag set, a test comparing the application view against merged() would compare legacy with legacy.

    Tests of the flag set it themselves.
    """
    monkeypatch.delenv(_LEGACY_FLAG, raising=False)


@pytest.fixture
def recorded_callibrary(monkeypatch):
    """Replace CASA's applycaltocallib with a recorder.

    Returns the list of calls, one dict of keyword arguments per
    callibrary entry written, with the target file under 'filename'.
    """
    calls = []

    def record(filename, **kwargs):
        calls.append({'filename': filename, **kwargs})

    monkeypatch.setattr(callibrary, 'applycaltocallib', record)
    return calls


def _written_cells_by_gaintable(ms, calls):
    """The written counterpart of _cells_by_gaintable: map each caltable to the cell sets of the recorded callibrary entries that reference it.

    The intent is mapped back from the stub's obs_mode spelling.
    """
    by_gaintable = collections.defaultdict(list)
    for call in calls:
        intent = ','.join(i.removesuffix('#ON_SOURCE') for i in call['intent'].split(',') if i)
        cells = _cell_set(ms, types.SimpleNamespace(field=call['field'], spw=call['spw'], intent=intent))
        gaintables = [call['gaintable']] if isinstance(call['gaintable'], str) else call['gaintable']
        for gaintable in gaintables:
            by_gaintable[gaintable].append(cells)
    return by_gaintable


@pytest.fixture
def fragmented_calstate():
    """Broad bandpass calapp + sparse per-field/per-spw TARGET renorm calapps, mimicking SerialRenorm._get_calapps -- the PIPE-2610 driving scenario.

    Sized so that consolidating the bandpass-only fragments greedily,
    fusing field and spw independently, grows rectangular hulls that
    intersect: many target fields, many spws, and renorm patches scattered
    so no single fuse order keeps the bandpass entries disjoint. The small
    3-field/4-spw shape does not exercise this -- its bandpass export comes
    out disjoint whatever the fuse order.
    """
    ms = _build_ms(n_targets=5, n_spws=8)
    context = _FakeContext(ms)

    bandpass = CalFrom(gaintable='bandpass.bcal', interp='linear,linear', caltype='bandpass')
    renorm = CalFrom(gaintable='renorm.rcal', interp='nearest,linear', caltype='tsys')

    renorm_patches = {
        'T1': '2~4',
        'T2': '3',
        'T3': '1~2,5~6',
        'T4': '4~5',
        'T5': '2,6~7',
    }

    registered = [
        CalApplication(CalTo(vis=ms.name, field='', spw='0~7', intent=''), bandpass),
    ]
    for field, spw in renorm_patches.items():
        registered.append(CalApplication(CalTo(vis=ms.name, field=field, spw=spw, intent='TARGET'), renorm))

    calstate = IntervalCalState.create_from_context(context)
    for calapp in registered:
        calstate = _register(calstate, context, calapp)

    return ms, calstate, registered


def test_export_entries_are_pairwise_disjoint_per_caltable(fragmented_calstate):
    """Invariant: no two application partition entries for the same caltable may overlap in field x spw x intent."""
    ms, calstate, _ = fragmented_calstate

    for gaintable, cell_sets in _cells_by_gaintable(ms, _partition_calapps(calstate)).items():
        for i, cells_a in enumerate(cell_sets):
            for cells_b in cell_sets[i + 1 :]:
                overlap = cells_a & cells_b
                assert not overlap, f'{gaintable}: overlapping cells {overlap}'


def test_export_is_faithful_to_the_registered_selection(fragmented_calstate):
    """The union of a caltable's partition cells equals the cells where it was registered -- nothing dropped, nothing invented.

    An overlap between two entries would not break this (it double-covers,
    it does not change the union), which is why disjointness is tested
    separately.
    """
    ms, calstate, registered = fragmented_calstate
    exported = _partition_calapps(calstate)

    registered_names = {cf.gaintable for calapp in registered for cf in calapp.calfrom}
    exported_cells = _cells_by_gaintable(ms, exported)

    for gaintable in registered_names:
        expected = set()
        for calapp in registered:
            if any(cf.gaintable == gaintable for cf in calapp.calfrom):
                expected |= _cell_set(ms, calapp)
        actual = set().union(*exported_cells[gaintable]) if exported_cells[gaintable] else set()
        assert actual == expected, f'{gaintable}: exported {actual} != registered {expected}'


def test_registering_broadly_twice_is_idempotent():
    """Registering the identical broad calapp twice must consolidate as if it were registered once.

    No entry may name the caltable more than once, and no cell may be told
    to apply it twice -- calibration is not idempotent, so a repeated
    identical application is never a valid instruction.
    """
    ms = _build_ms()
    context = _FakeContext(ms)
    bandpass = CalFrom(gaintable='bandpass.bcal', interp='linear,linear', caltype='bandpass')
    calapp = CalApplication(CalTo(vis=ms.name, field='', spw='0,1,2,3', intent=''), bandpass)

    once = _register(IntervalCalState.create_from_context(context), context, calapp)
    twice = _register(once, context, calapp)

    entries = _partition_calapps(twice)
    for entry in entries:
        tables = [cf.gaintable for cf in entry.calfrom]
        assert tables.count('bandpass.bcal') <= 1, f'duplicated CalFrom: {tables}'

    assert _coverage_by_gaintable(ms, entries) == _coverage_by_gaintable(ms, _partition_calapps(once))


def test_conflicting_apply_parameters_over_one_cell_raises():
    """Two different apply-parameter sets over the same cell for one caltable are a genuine contradiction and must raise, not be emitted.

    Downstream, the emitted pair would surface only as an opaque CASA
    abort with no field/spw attached.
    """
    ms = _build_ms()
    context = _FakeContext(ms)
    calto = CalTo(vis=ms.name, field='T1', spw='2', intent='TARGET')
    linear = CalApplication(calto, CalFrom(gaintable='bandpass.bcal', interp='linear,linear', caltype='bandpass'))
    nearest = CalApplication(calto, CalFrom(gaintable='bandpass.bcal', interp='nearest,linear', caltype='bandpass'))

    calstate = IntervalCalState.create_from_context(context)
    calstate = _register(calstate, context, linear)
    calstate = _register(calstate, context, nearest)

    with pytest.raises(ValueError) as excinfo:
        _partition_calapps(calstate)

    # ValueError exactly, not a subclass: callers that catch ValueError would
    # swallow a new error type just as silently, so widening it is a decision
    # to take deliberately
    assert excinfo.type is ValueError

    # the diagnostic must name the caltable and the concrete data selection the
    # opaque CASA abort omits. Asserting the axis labels alone would be
    # satisfied by 'field= spw= intent=' -- the very failure being guarded
    message = str(excinfo.value)
    assert 'bandpass.bcal' in message
    for axis_value in ('antenna=0', 'field=T1', 'spw=2', 'intent=TARGET'):
        assert axis_value in message, message

    # both parameter sets reached the check: an over-eager duplicate collapse
    # would leave one and report no conflict at all
    assert '2 incompatible parameter sets' in message, message


def test_conflict_diagnostic_renders_a_field_axis_mixing_names_and_ids():
    """Field names that are not unique within an MS are identified by ID, the unique ones by name, so one selection's field axis can hold both -- here {'T1', 2, 3}.

    The conflict diagnostic must still render that axis and raise
    ValueError; sorting str against int would raise TypeError instead and
    hide the conflict it was about to report.
    """
    spws = [_StubSpectralWindow(i) for i in range(4)]
    fields = [
        _StubField(0, 'BP', intents={'BANDPASS'}),
        _StubField(1, 'T1', intents={'TARGET'}),
        _StubField(2, 'M', intents={'TARGET'}),
        _StubField(3, 'M', intents={'TARGET'}),
    ]
    for field in fields:
        field.valid_spws = set(spws)
    scans = [_StubScan(i + 1, intents=field.intents, fields={field}, spws=spws) for i, field in enumerate(fields)]
    ms = _StubMeasurementSet('mixed_ids.ms', fields, spws, [_StubAntenna(0)], scans)
    context = _FakeContext(ms)

    calto = CalTo(vis=ms.name, field='T1,M', spw='2', intent='TARGET')
    linear = CalApplication(calto, CalFrom(gaintable='bandpass.bcal', interp='linear,linear', caltype='bandpass'))
    nearest = CalApplication(calto, CalFrom(gaintable='bandpass.bcal', interp='nearest,linear', caltype='bandpass'))

    calstate = IntervalCalState.create_from_context(context)
    calstate = _register(calstate, context, linear)
    calstate = _register(calstate, context, nearest)

    with pytest.raises(ValueError) as excinfo:
        _partition_calapps(calstate)

    # compared as a set: the order the diagnostic lists them in is not the point
    message = str(excinfo.value)
    field_token = re.search(r'\bfield=(\S+)', message)
    assert field_token, message
    assert set(field_token.group(1).split(',')) == {'T1', '2', '3'}, message
    assert 'spw=2' in message, message
    assert 'intent=TARGET' in message, message


def test_export_of_a_non_fragmented_calstate_is_faithful():
    """A single broad registration -- today's filled-table production shape, no renorm fragmentation -- exports exactly the cells and parameters it was registered with.

    It need not be a single entry: the calstate tree already splits
    BANDPASS-on-the-calibrator from TARGET-on-the-science, and the
    constructive export keeps those apart rather than widening them into
    one rectangular hull over cells that hold no data.
    """
    ms = _build_ms()
    context = _FakeContext(ms)
    bandpass = CalFrom(gaintable='bandpass.bcal', interp='linear,linear', caltype='bandpass')
    calapp = CalApplication(CalTo(vis=ms.name, field='', spw='0,1,2,3', intent=''), bandpass)

    calstate = _register(IntervalCalState.create_from_context(context), context, calapp)

    coverage = _coverage_by_gaintable(ms, _partition_calapps(calstate))
    assert set(coverage) == {'bandpass.bcal'}
    assert set(coverage['bandpass.bcal']) == _cell_set(ms, calapp)
    assert set(coverage['bandpass.bcal'].values()) == {_param_key(bandpass)}


# The seven data selections CASA aborted on for MOUS uid___A002_Xe1f219_X9dbf
# (PIPE-2610), taken verbatim from its exported .callibrary. Every line names
# the same bandpass caltable with the same apply parameters, so the only thing
# that varies is the field x spw geometry. Two defects: the last two lines are
# byte-identical, and line 1 and line 3 both claim IRAM04191 x spw 16. Worked
# out, the union is the whole target grid -- every target field, every science
# spw -- which is what a bandpass table applies to.
_XE1F219_FIELDS = ['HH_30', '04288+1802', '04287+1801', 'IRAM04191', '04191+1523']
_XE1F219_SPWS = [16, 18, 20, 22, 24, 26, 28, 30]
_XE1F219_SELECTIONS = [
    ('04287+1801,IRAM04191', '16,20,22,24,26,28,30'),
    ('04288+1802', '20,22,24,26,28,30'),
    ('HH_30,IRAM04191,04191+1523', '16,18'),
    ('04287+1801,04288+1802', '18'),
    ('04288+1802', '16'),
    ('HH_30,04191+1523', '20,22,24,26,28,30'),
    ('HH_30,04191+1523', '20,22,24,26,28,30'),
]


def _build_xe1f219_ms():
    """The target-side shape of uid___A002_Xe1f219_X9dbf: five target fields, eight science spws, one intent.

    No bandpass calibrator field -- the aborting export only ever selected
    targets.
    """
    spws = [_StubSpectralWindow(i) for i in _XE1F219_SPWS]
    fields = [_StubField(i, name, intents={'TARGET'}) for i, name in enumerate(_XE1F219_FIELDS)]
    for field in fields:
        field.valid_spws = set(spws)
    scans = [_StubScan(i + 1, intents={'TARGET'}, fields={field}, spws=spws) for i, field in enumerate(fields)]
    return _StubMeasurementSet('xe1f219.ms', fields, spws, [_StubAntenna(0)], scans)


@pytest.fixture
def xe1f219_calstate():
    """The seven overlapping bandpass selections that CASA rejected for MOUS uid___A002_Xe1f219_X9dbf.

    Registered on the xe1f219 stub MS. Returns ``(ms, calstate,
    registered)``, mirroring fragmented_calstate.
    """
    ms = _build_xe1f219_ms()
    context = _FakeContext(ms)
    bandpass = CalFrom(gaintable='bandpass.bcal', interp='linearperobs,linearflag', calwt=True, caltype='bandpass')

    registered = [
        CalApplication(CalTo(vis=ms.name, field=field, spw=spw, intent='TARGET'), bandpass)
        for field, spw in _XE1F219_SELECTIONS
    ]

    calstate = IntervalCalState.create_from_context(context)
    for calapp in registered:
        calstate = _register(calstate, context, calapp)

    return ms, calstate, registered


def test_xe1f219_repro_export_is_disjoint(xe1f219_calstate):
    """The real selections CASA rejected with 'Attempted duplicate MSCalPatchKey!' must export pairwise disjoint per caltable."""
    ms, calstate, _ = xe1f219_calstate

    for gaintable, cell_sets in _cells_by_gaintable(ms, _partition_calapps(calstate)).items():
        for i, cells_a in enumerate(cell_sets):
            for cells_b in cell_sets[i + 1 :]:
                overlap = cells_a & cells_b
                assert not overlap, f'{gaintable}: overlapping cells {overlap}'


def test_xe1f219_repro_export_is_faithful(xe1f219_calstate):
    """Coverage is preserved: the bandpass table still lands on every target field x science spw it was registered for."""
    ms, calstate, _ = xe1f219_calstate
    exported = _cells_by_gaintable(ms, _partition_calapps(calstate))['bandpass.bcal']

    full_grid = {(f.id, s.id, 'TARGET') for f in ms.fields for s in ms.spectral_windows}
    assert set().union(*exported) == full_grid


def test_xe1f219_repro_collapses_to_one_entry(xe1f219_calstate):
    """The seven tangled selections carry one caltable, one parameter set, and together cover the full grid.

    The constructive export therefore states them as a single entry over
    all target fields and all science spws.
    """
    ms, calstate, _ = xe1f219_calstate
    entries = [e for e in _partition_calapps(calstate) if any(cf.gaintable == 'bandpass.bcal' for cf in e.calfrom)]

    assert len(entries) == 1
    entry = entries[0]
    assert {f.strip() for f in entry.field.split(',')} == set(_XE1F219_FIELDS)
    assert {s.id for s in ms.get_spectral_windows(task_arg=entry.spw)} == set(_XE1F219_SPWS)


def test_partition_matches_merged_on_a_non_fragmented_calstate():
    """With no sparse-caltable fragmentation, the application partition and the merged() view must prescribe the same caltable(s) with the same apply parameters for every cell.

    Entry *grouping* may differ -- the partition does not widen a
    selection into a rectangular hull -- but the per-cell calibration may
    not.
    """
    ms = _build_ms(n_targets=3, n_spws=6)
    context = _FakeContext(ms)
    bandpass = CalFrom(gaintable='bandpass.bcal', interp='linear,linear', caltype='bandpass')
    phase = CalFrom(gaintable='phase.gcal', interp='linear,linear', caltype='gaincal')
    amp = CalFrom(gaintable='amp.gcal', gainfield='0', interp='nearest,linear', caltype='gaincal')

    registered = [
        CalApplication(CalTo(vis=ms.name, field='', spw='', intent=''), bandpass),
        CalApplication(CalTo(vis=ms.name, field='', spw='', intent=''), phase),
        CalApplication(CalTo(vis=ms.name, field='T1,T2,T3', spw='0~5', intent='TARGET'), amp),
    ]
    calstate = IntervalCalState.create_from_context(context)
    for calapp in registered:
        calstate = _register(calstate, context, calapp)

    partition_coverage = _coverage_by_gaintable(ms, _partition_calapps(calstate))
    merged_coverage = _coverage_by_gaintable(ms, _merged_calapps(calstate))

    assert partition_coverage == merged_coverage


def test_partition_keeps_each_cells_full_ordered_stack():
    """A cell registered with a two-table stack keeps both tables together in one entry, even when a neighbouring cell shares only the first table.

    The shared table must not be merged across the two cells into an
    entry that splits the stack -- consumers that build one job per entry
    are handed that entry's stack and nothing else.
    """
    ms = _build_ms(n_targets=2, n_spws=1)
    context = _FakeContext(ms)
    x = CalFrom(gaintable='x.bcal', interp='linear,linear', caltype='bandpass')
    y = CalFrom(gaintable='y.gcal', interp='linear,linear', caltype='gaincal')

    calstate = IntervalCalState.create_from_context(context)
    calstate = _register(
        calstate, context, CalApplication(CalTo(vis=ms.name, field='T1', spw='0', intent='TARGET'), [x, y])
    )
    calstate = _register(
        calstate, context, CalApplication(CalTo(vis=ms.name, field='T2', spw='0', intent='TARGET'), [x])
    )

    stacks = _stacks_by_cell(ms, _partition_calapps(calstate))
    assert stacks[(1, 0, 'TARGET')] == [['x.bcal', 'y.gcal']]
    assert stacks[(2, 0, 'TARGET')] == [['x.bcal']]


def test_partition_keeps_per_region_calfrom_order():
    """Two cells that carry the same two tables in opposite order stay separate.

    Apply order is part of the instruction, so it may not be flattened to
    one global order.
    """
    ms = _build_ms(n_targets=2, n_spws=1)
    context = _FakeContext(ms)
    x = CalFrom(gaintable='x.bcal', interp='linear,linear', caltype='bandpass')
    y = CalFrom(gaintable='y.gcal', interp='linear,linear', caltype='gaincal')

    calstate = IntervalCalState.create_from_context(context)
    calstate = _register(
        calstate, context, CalApplication(CalTo(vis=ms.name, field='T1', spw='0', intent='TARGET'), [x, y])
    )
    calstate = _register(
        calstate, context, CalApplication(CalTo(vis=ms.name, field='T2', spw='0', intent='TARGET'), [y, x])
    )

    stacks = _stacks_by_cell(ms, _partition_calapps(calstate))
    assert stacks[(1, 0, 'TARGET')] == [['x.bcal', 'y.gcal']]
    assert stacks[(2, 0, 'TARGET')] == [['y.gcal', 'x.bcal']]


def test_same_caltable_two_parameter_sets_on_disjoint_cells_both_survive():
    """One gaintable applied with different parameters to disjoint cells is not a conflict -- both applications must reach the export."""
    ms = _build_ms(n_targets=2, n_spws=1)
    context = _FakeContext(ms)
    near = CalFrom(gaintable='t.gcal', interp='nearest,linear', caltype='gaincal')
    lin = CalFrom(gaintable='t.gcal', interp='linear,linear', caltype='gaincal')

    calstate = IntervalCalState.create_from_context(context)
    calstate = _register(
        calstate, context, CalApplication(CalTo(vis=ms.name, field='T1', spw='0', intent='TARGET'), near)
    )
    calstate = _register(
        calstate, context, CalApplication(CalTo(vis=ms.name, field='T2', spw='0', intent='TARGET'), lin)
    )

    coverage = _coverage_by_gaintable(ms, _partition_calapps(calstate))['t.gcal']
    assert coverage[(1, 0, 'TARGET')] == _param_key(near)
    assert coverage[(2, 0, 'TARGET')] == _param_key(lin)


def test_merged_keeps_a_combined_solve_over_a_non_rectangular_selection_joint():
    """merged() is also the solvers' work partition: each entry becomes one CASA job.

    F2 has no spw 1 data, so the cells X was registered on form an L
    rather than a rectangle. merged() must still return one entry over
    F1,F2 x 0,1 -- split in two, a solve combining field and spw would run
    as two independent solves whose results are merely appended. The
    extra F2 x 1 cell holds no data, so it costs a solver nothing.
    """
    ms = _build_layout_ms(
        'l_shape.ms',
        [
            (0, 'BP', {'BANDPASS'}, [0, 1]),
            (1, 'F1', {'PHASE'}, [0, 1]),
            (2, 'F2', {'PHASE'}, [0]),
        ],
    )
    context = _FakeContext(ms)
    x = CalFrom(gaintable='x.tbl', interp='linear', caltype='gaincal')
    calapp = CalApplication(CalTo(vis=ms.name, field='F1,F2', spw='0,1', intent='PHASE'), x)

    calstate = _register(IntervalCalState.create_from_context(context), context, calapp)

    assert _grouping(_merged_calapps(calstate)) == collections.Counter({
        (frozenset({'F1', 'F2'}), frozenset({0, 1}), 'PHASE', ('x.tbl',)): 1,
    })


def test_merged_keeps_the_combined_solve_joint_alongside_a_second_stack():
    """The previous case with a second, unrelated calibration: Y applies only to F3 x 2, where X was never registered.

    The X cells are still one L-shaped region and must stay one entry
    over F1,F2 x 0,1; the Y cell is its own entry. A second stack in the
    calstate is no reason to split the X solve.
    """
    ms = _build_layout_ms(
        'l_shape_plus_second_stack.ms',
        [
            (0, 'BP', {'BANDPASS'}, [0, 1, 2]),
            (1, 'F1', {'PHASE'}, [0, 1]),
            (2, 'F2', {'PHASE'}, [0]),
            (3, 'F3', {'PHASE'}, [2]),
        ],
    )
    context = _FakeContext(ms)
    x = CalFrom(gaintable='x.tbl', interp='linear', caltype='gaincal')
    y = CalFrom(gaintable='y.tbl', interp='linear', caltype='gaincal')

    calstate = IntervalCalState.create_from_context(context)
    calstate = _register(
        calstate, context, CalApplication(CalTo(vis=ms.name, field='F1,F2', spw='0,1', intent='PHASE'), x)
    )
    calstate = _register(calstate, context, CalApplication(CalTo(vis=ms.name, field='F3', spw='2', intent='PHASE'), y))

    assert _grouping(_merged_calapps(calstate)) == collections.Counter({
        (frozenset({'F1', 'F2'}), frozenset({0, 1}), 'PHASE', ('x.tbl',)): 1,
        (frozenset({'F3'}), frozenset({2}), 'PHASE', ('y.tbl',)): 1,
    })


def test_merged_and_its_renderings_keep_a_conflict_without_raising():
    """The conflict application_partition() rejects must not raise through merged(), as_applycal() or __str__.

    They back solver job grouping, the weblog and log messages, and an
    exception there would abort a stage over what is only being
    described. The conflicting pair stays as registered, both CalFroms in
    registration order.
    """
    ms = _build_ms()
    context = _FakeContext(ms)
    calto = CalTo(vis=ms.name, field='T1', spw='2', intent='TARGET')
    linear = CalApplication(calto, CalFrom(gaintable='bandpass.bcal', interp='linear,linear', caltype='bandpass'))
    nearest = CalApplication(calto, CalFrom(gaintable='bandpass.bcal', interp='nearest,linear', caltype='bandpass'))

    calstate = IntervalCalState.create_from_context(context)
    calstate = _register(calstate, context, linear)
    calstate = _register(calstate, context, nearest)

    merged = _merged_calapps(calstate)
    assert len(merged) == 1
    assert [(cf.gaintable, cf.interp) for cf in merged[0].calfrom] == [
        ('bandpass.bcal', 'linear,linear'),
        ('bandpass.bcal', 'nearest,linear'),
    ]

    applycal = calstate.as_applycal()
    assert applycal.count('applycal(') == 1, applycal
    assert "interp=['linear,linear', 'nearest,linear']" in applycal, applycal
    assert str(calstate) == applycal


def test_export_writes_the_application_partition(fragmented_calstate, recorded_callibrary):
    """export_to_casa_callibrary writes one callibrary entry per application_partition() entry, in the same order, with the intent converted to the MS's obs_mode spelling and every apply parameter passed through.

    The first entry creates the file, the rest append to it. A phase
    table with non-default gainfield, spwmap and calwt is registered on
    top of the fixture, so a dropped or swapped parameter cannot hide
    behind a default.
    """
    ms, calstate, _ = fragmented_calstate
    context = _FakeContext(ms)
    phase = CalFrom(
        gaintable='phase.gcal', gainfield='BP', interp='linear', spwmap=[0] * 8, calwt=False, caltype='gaincal'
    )
    calstate = _register(
        calstate, context, CalApplication(CalTo(vis=ms.name, field='T2,T4', spw='0~7', intent='TARGET'), phase)
    )

    calstate.export_to_casa_callibrary(ms, 'fake.callibrary')

    expected = [
        {
            'filename': 'fake.callibrary',
            'append': index > 0,
            'field': calapp.field,
            'intent': frozenset(_casa_intent(i) for i in calapp.intent.split(',') if i),
            'spw': calapp.spw,
            'gaintable': calapp.gaintable,
            'gainfield': calapp.gainfield,
            'interp': calapp.interp,
            'spwmap': calapp.spwmap,
            'calwt': calapp.calwt,
        }
        for index, calapp in enumerate(_partition_calapps(calstate))
    ]
    # to_CASA_intent joins a set, so the order of several written intents is arbitrary
    written = [{**call, 'intent': frozenset(i for i in call['intent'].split(',') if i)} for call in recorded_callibrary]
    assert written == expected
    assert any('phase.gcal' in call['gaintable'] for call in recorded_callibrary)


def test_export_writes_disjoint_entries_per_caltable(xe1f219_calstate, recorded_callibrary):
    """The callibrary written for the selections CASA rejected with 'Attempted duplicate MSCalPatchKey!' has no two entries for the same caltable that overlap in field x spw x intent."""
    ms, calstate, _ = xe1f219_calstate

    calstate.export_to_casa_callibrary(ms, 'xe1f219.callibrary')

    assert recorded_callibrary
    for gaintable, cell_sets in _written_cells_by_gaintable(ms, recorded_callibrary).items():
        for i, cells_a in enumerate(cell_sets):
            for cells_b in cell_sets[i + 1 :]:
                overlap = cells_a & cells_b
                assert not overlap, f'{gaintable}: overlapping written cells {overlap}'


def test_export_with_a_conflict_raises_before_writing(recorded_callibrary):
    """A conflict aborts the export before the callibrary is touched: a partially written file would reach applycal with the conflicting cell silently uncalibrated.

    A valid application registered first gives the export something it
    could have written ahead of the conflict.
    """
    ms = _build_ms()
    context = _FakeContext(ms)
    phase = CalApplication(
        CalTo(vis=ms.name, field='T2', spw='0~3', intent='TARGET'),
        CalFrom(gaintable='phase.gcal', interp='linear', caltype='gaincal'),
    )
    calto = CalTo(vis=ms.name, field='T1', spw='2', intent='TARGET')
    linear = CalApplication(calto, CalFrom(gaintable='bandpass.bcal', interp='linear,linear', caltype='bandpass'))
    nearest = CalApplication(calto, CalFrom(gaintable='bandpass.bcal', interp='nearest,linear', caltype='bandpass'))

    calstate = IntervalCalState.create_from_context(context)
    for calapp in (phase, linear, nearest):
        calstate = _register(calstate, context, calapp)

    with pytest.raises(ValueError) as excinfo:
        calstate.export_to_casa_callibrary(ms, 'fake.callibrary')

    assert excinfo.type is ValueError
    assert 'bandpass.bcal' in str(excinfo.value)
    assert recorded_callibrary == []


def _queried_stacks_by_cell(context, calstate, ms):
    """Map every (field, spw, intent) cell holding data to the calibration the calstate gives it, queried one cell at a time.

    One list per entry covering the cell, each the ordered (caltable,
    parameter key) stack. A single-cell query sidesteps how the whole
    calstate would be grouped, so a stack the tree holds twice shows up
    as a doubled stack.
    """
    stacks = {}
    for field in ms.get_fields():
        for spw in field.valid_spws:
            for intent in field.intents:
                calto = CalTo(vis=ms.name, field=field.name, spw=str(spw.id), intent=intent)
                entries = calstate.trimmed(context, calto).merged(hide_empty=True).values()
                stacks[(field.id, spw.id, intent)] = [
                    [(cf.gaintable, _param_key(cf)) for cf in calfroms] for calfroms in entries
                ]
    return stacks


def test_export_import_round_trip_preserves_each_cells_stack(tmp_path):
    """Exporting the active calstate and importing it into a fresh library gives every cell back exactly the ordered stack registered for it, and leaves the cells nothing was registered on uncalibrated.

    An overlap in the exported file would re-import as a doubled stack on
    the shared cells.

    The fragmented scenario, with bandpass registered on the targets
    only, so the bandpass calibrator's cells stay untouched. Caltable
    names follow the ones import_state recognises without opening the
    table.
    """
    ms = _build_ms(n_targets=5, n_spws=8)
    context = _FakeContext(ms)
    bandpass = CalFrom(gaintable='bandpass.bcal', interp='linear,linear', caltype='bandpass')
    renorm = CalFrom(gaintable='renorm.tsys', interp='nearest,linear', caltype='tsys')
    registered = [CalApplication(CalTo(vis=ms.name, field='T1,T2,T3,T4,T5', spw='0~7', intent='TARGET'), bandpass)]
    for field, spw in {'T1': '2~4', 'T2': '3', 'T3': '1~2,5~6', 'T4': '4~5', 'T5': '2,6~7'}.items():
        registered.append(CalApplication(CalTo(vis=ms.name, field=field, spw=spw, intent='TARGET'), renorm))

    library = callibrary.IntervalCalLibrary(context)
    for calapp in registered:
        library.add(calapp.calto, calapp.calfrom)
    filename = str(tmp_path / 'fake.calstate')
    library.export(filename)

    imported = callibrary.IntervalCalLibrary(context)
    imported.import_state(filename)

    expected = collections.defaultdict(list)
    for calapp in registered:
        for cell in _cell_set(ms, calapp):
            expected[cell].extend((cf.gaintable, _param_key(cf)) for cf in calapp.calfrom)
    stacks = _queried_stacks_by_cell(context, imported.active, ms)
    untouched = {cell for cell in stacks if cell not in expected}
    assert untouched == {(0, spw, 'BANDPASS') for spw in range(8)}
    assert stacks == {cell: [expected[cell]] if cell in expected else [] for cell in stacks}


def _applycal_lines(calapps):
    return [calapp.as_applycal() for calapp in calapps]


def test_legacy_flag_reverts_the_partition_but_not_merged(fragmented_calstate, monkeypatch):
    """The legacy flag turns application_partition() into the legacy consolidation merged() gives, and leaves merged() itself alone: solvers, the weblog and logging see the same grouping with or without it.

    Without the flag the partition must differ, or the fixture could not
    tell.
    """
    _, calstate, _ = fragmented_calstate
    merged = _applycal_lines(_merged_calapps(calstate))
    partition = _applycal_lines(_partition_calapps(calstate))

    monkeypatch.setenv(_LEGACY_FLAG, '1')

    assert _applycal_lines(_merged_calapps(calstate)) == merged
    assert _applycal_lines(_partition_calapps(calstate)) == merged
    assert partition != merged


def test_legacy_flag_reverts_the_export(fragmented_calstate, recorded_callibrary, monkeypatch):
    """With the legacy flag, export_to_casa_callibrary writes the merged() entries, overlaps included, instead of the application partition."""
    ms, calstate, _ = fragmented_calstate
    calstate.export_to_casa_callibrary(ms, 'fake.callibrary')
    written_by_default = _written_cells_by_gaintable(ms, recorded_callibrary)
    recorded_callibrary.clear()

    monkeypatch.setenv(_LEGACY_FLAG, '1')
    calstate.export_to_casa_callibrary(ms, 'fake.callibrary')

    legacy = _cells_by_gaintable(ms, _merged_calapps(calstate))
    assert _written_cells_by_gaintable(ms, recorded_callibrary) == legacy
    assert written_by_default != legacy


def test_legacy_flag_reverts_the_calstate_snapshot(fragmented_calstate, tmp_path, monkeypatch):
    """With the legacy flag, IntervalCalLibrary.export() writes the merged() entries as applycal lines instead of the application partition."""
    ms, _, registered = fragmented_calstate
    library = callibrary.IntervalCalLibrary(_FakeContext(ms))
    for calapp in registered:
        library.add(calapp.calto, calapp.calfrom)
    default_file = tmp_path / 'default.calstate'
    legacy_file = tmp_path / 'legacy.calstate'
    library.export(str(default_file))

    monkeypatch.setenv(_LEGACY_FLAG, '1')
    library.export(str(legacy_file))

    legacy = _applycal_lines(_merged_calapps(library.active))
    assert legacy_file.read_text().splitlines() == legacy
    assert default_file.read_text().splitlines() != legacy
