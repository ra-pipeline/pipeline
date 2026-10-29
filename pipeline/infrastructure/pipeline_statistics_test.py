"""Unit tests for the pipeline statistics framework, definitions and extractors."""
import collections
import inspect
import json
import re
import types

import numpy as np
import pytest

from pipeline.hifv.tasks.flagging.checkflag import Checkflag, CheckflagResults
from pipeline.infrastructure import basetask, pipeline_stats_definitions, pipeline_stats_extractors, pipelineqa
from pipeline.infrastructure import pipeline_statistics as ps

DEFS = ps.build_definitions([
    ps.StatDefinition('mous_stat', 'a MOUS-level stat'),
    ps.StatDefinition('eb_stat', 'an EB-level stat', units='m'),
    ps.StatDefinition('spw_stat', 'a spw-wide stat'),
    ps.StatDefinition('source_stat', 'a per-source stat'),
    ps.StatDefinition('per_spw_stat', 'varies by EB and spw', rel_tol=0.1),
    ps.StatDefinition('stage_stat', 'describes a stage', per_stage=True),
    ps.StatDefinition('test_stat', 'test only', audience=ps.Audience.TEST),
    ps.StatDefinition('ignored_stat', 'never compared', compare=False),
])
MOUS = 'uid://A001/X1/X2'


def make_collection():
    records = [
        ps.StatRecord('mous_stat', 'a value'),
        ps.StatRecord('eb_stat', 12.5, {'eb': 'uid_X.ms'}),
        ps.StatRecord('spw_stat', 2.0, {'spw': '17'}),
        ps.StatRecord('source_stat', 3, {'source': 'M100'}),
        ps.StatRecord('per_spw_stat', 45.2, {'eb': 'uid_X.ms', 'spw': '17'}, stage=12, task='hifa_bandpass'),
        ps.StatRecord('per_spw_stat', 38.1, {'eb': 'uid_X.ms', 'spw': '19'}, stage=12, task='hifa_bandpass'),
        ps.StatRecord('stage_stat', 0.5, stage=3, task='hifa_importdata'),
        ps.StatRecord('test_stat', [1, 2, 3], {'eb': 'uid_X.ms'}, stage=5, task='hif_applycal'),
        ps.StatRecord('ignored_stat', 'anything'),
    ]
    return ps.StatsCollection(records=records, errors=[])


def keyed(records):
    return sorted((r.key, json.dumps(r.value)) for r in records)


# ---- Definitions -----------------------------------------------------------------------------------------------------

def test_build_definitions_rejects_duplicates_and_reserved_names():
    with pytest.raises(ValueError):
        ps.build_definitions([ps.StatDefinition('x', ''), ps.StatDefinition('x', '')])
    with pytest.raises(ValueError):
        ps.build_definitions([ps.StatDefinition('EB', '')])
    with pytest.raises(ValueError):
        ps.build_definitions([ps.StatDefinition('STAGE', '')])


def test_every_name_emitted_by_the_extractors_is_defined():
    source = inspect.getsource(pipeline_stats_extractors)
    names = set(re.findall(r"emit\('(\w+)'", source))
    for base in re.findall(r"_emit_flagged_rows\(emit, '(\w+)'", source):
        names |= {base, f'{base}_per_scan'}
    for prefix in re.findall(r"_bpdcals_flags\('(\w+)'\)", source):
        names |= {f'{prefix}_bandpass_flagged_solutions', f'{prefix}_delay_flagged_solutions'}
    assert names, 'no statistic names found'
    assert names <= set(pipeline_stats_definitions.DEFINITIONS)


# ---- Emitting --------------------------------------------------------------------------------------------------------

def test_emit_normalizes_values_and_dims():
    collection = ps.StatsCollection()
    emit = ps._Emitter(collection, DEFS, stage=4, task='hifa_x')
    emit('eb_stat', np.float64(1.5), eb='a.ms', spw=np.int64(3))
    emit('test_stat', {3, 1, 2}, eb='a.ms', spw=None)
    emit('stage_stat', np.arange(3), stage=7, task='other')

    assert [r.to_dict() for r in collection.records] == [
        {'name': 'eb_stat', 'stage': 4, 'task': 'hifa_x', 'dims': {'eb': 'a.ms', 'spw': '3'}, 'value': 1.5},
        {'name': 'test_stat', 'stage': 4, 'task': 'hifa_x', 'dims': {'eb': 'a.ms'}, 'value': [1, 2, 3]},
        {'name': 'stage_stat', 'stage': 7, 'task': 'other', 'value': [0, 1, 2]},
    ]
    assert isinstance(collection.records[0].value, float)


@pytest.mark.parametrize('call', [
    lambda emit: emit('not_defined', 1),
    lambda emit: emit('eb_stat', 1, not_a_dimension='x'),
    lambda emit: emit('eb_stat', object()),
])
def test_bad_emits_are_recorded_as_errors_and_discard_partial_output(call):
    collection = ps.StatsCollection()

    def extractor(emit):
        emit('mous_stat', 'kept only if the extractor succeeds')
        call(emit)

    ps._run_extractor(collection, 'extractor', extractor, (), ps._Emitter(collection, DEFS, 2, 'task'), 2, 'task')
    assert collection.records == []
    assert len(collection.errors) == 1
    assert collection.errors[0]['extractor'] == 'extractor'
    assert collection.errors[0]['stage'] == 2


# ---- Collecting from a context ---------------------------------------------------------------------------------------

class LeafTask:
    pass


class OtherTask:
    pass


class LeafResults(basetask.Results):
    pass


def make_leaf(vis, task=LeafTask):
    result = LeafResults()
    result.task = task
    result.stage_number = 6
    result.vis = vis
    return result


def make_context(results):
    proxies = [types.SimpleNamespace(read=lambda r=r: r) for r in results]
    return types.SimpleNamespace(results=proxies, get_oussid=lambda: MOUS)


def test_collect_stats_walks_results_lists_and_matches_generating_task():
    registry = ps.ExtractorRegistry()
    calls = collections.Counter()

    @registry.results(LeafResults, LeafTask)
    def leaf(result, context, emit):
        calls['leaf'] += 1
        emit('eb_stat', 1.0, eb=result.vis)

    @registry.results(basetask.Results, top_level_only=True)
    def top(result, context, emit):
        calls['top'] += 1
        emit('stage_stat', 1.0)

    @registry.context
    def from_context(context, emit):
        emit('mous_stat', context.get_oussid())

    results_list = basetask.ResultsList([make_leaf('a.ms'), make_leaf('b.ms'), make_leaf('c.ms', OtherTask)])
    results_list.stage_number = 6
    collection = ps.collect_stats(make_context([results_list]), DEFS, registry)

    assert calls == {'leaf': 2, 'top': 1}
    assert collection.errors == []
    by_name = collections.defaultdict(list)
    for record in collection.records:
        by_name[record.name].append(record)
    assert [r.dims['eb'] for r in by_name['eb_stat']] == ['a.ms', 'b.ms']
    assert {(r.stage, r.task) for r in by_name['eb_stat'] + by_name['stage_stat']} == {(6, 'LeafTask')}
    assert by_name['mous_stat'][0].value == MOUS
    assert by_name['mous_stat'][0].stage is None


def test_failing_extractor_does_not_stop_others():
    registry = ps.ExtractorRegistry()

    @registry.results(LeafResults)
    def broken(result, context, emit):
        raise RuntimeError('boom')

    @registry.results(LeafResults)
    def working(result, context, emit):
        emit('eb_stat', 1.0, eb=result.vis)

    collection = ps.collect_stats(make_context([make_leaf('a.ms')]), DEFS, registry)
    assert [r.name for r in collection.records] == ['eb_stat']
    assert collection.errors == [{'extractor': 'broken', 'stage': 6, 'task': 'LeafTask',
                                  'error': 'RuntimeError: boom'}]


# ---- Documents -------------------------------------------------------------------------------------------------------

def test_nested_document_keeps_current_layout_for_single_dimension_stats():
    document = ps.build_document(make_collection(), DEFS, MOUS, ps.OutputFormat.NESTED, ps.ALL_AUDIENCES)
    mous = document[MOUS]
    assert mous['mous_stat'] == {'value': 'a value', 'longdescription': 'a MOUS-level stat'}
    assert mous['EB']['uid_X.ms']['eb_stat'] == {'value': 12.5, 'units': 'm', 'longdescription': 'an EB-level stat'}
    assert mous['SPW']['17']['spw_stat']['value'] == 2.0
    assert mous['TARGET']['M100']['source_stat']['value'] == 3
    # A value that varies by EB and spw nests the spw under the EB
    leaf = mous['EB']['uid_X.ms']['SPW']['17']['per_spw_stat']
    assert leaf == {'value': 45.2, 'longdescription': 'varies by EB and spw', 'origin': 'hifa_bandpass', 'stage': 12}
    # Per-stage statistics go under STAGE.<n>
    assert document['STAGE']['3']['stage_stat']['value'] == 0.5
    assert document['header']['format'] == 'nested'
    assert document['errors'] == []
    assert set(document['definitions']) == set(DEFS)


def test_product_document_excludes_test_statistics():
    document = ps.build_document(make_collection(), DEFS, MOUS, ps.OutputFormat.FLAT)
    names = {r['name'] for r in document['stats']}
    assert 'test_stat' not in names and 'test_stat' not in document['definitions']
    assert 'eb_stat' in names


def test_nested_leaf_becomes_a_list_when_records_collide():
    collection = ps.StatsCollection(records=[
        ps.StatRecord('eb_stat', 1.0, {'eb': 'a.ms'}, stage=4, task='hifv_checkflag'),
        ps.StatRecord('eb_stat', 2.0, {'eb': 'a.ms'}, stage=9, task='hifv_checkflag'),
    ])
    document = ps.build_document(collection, DEFS, MOUS, ps.OutputFormat.NESTED)
    leaf = document[MOUS]['EB']['a.ms']['eb_stat']
    assert [entry['value'] for entry in leaf] == [1.0, 2.0]
    assert keyed(ps.document_to_records(document)) == keyed(collection.records)


@pytest.mark.parametrize('fmt', list(ps.OutputFormat))
def test_documents_round_trip_through_json(fmt):
    collection = make_collection()
    document = ps.build_document(collection, DEFS, MOUS, fmt, ps.ALL_AUDIENCES)
    text = ps.dumps_document(document)
    reloaded = json.loads(text)
    assert reloaded == json.loads(json.dumps(document))
    assert keyed(ps.document_to_records(reloaded)) == keyed(collection.records)


def test_flat_file_has_one_record_per_line_sorted_by_stage():
    document = ps.build_document(make_collection(), DEFS, MOUS, ps.OutputFormat.FLAT, ps.ALL_AUDIENCES)
    lines = ps.dumps_document(document).splitlines()
    record_lines = [line for line in lines if '"name": ' in line]
    assert len(record_lines) == len(make_collection().records)
    stages = [json.loads(line.strip().rstrip(',')).get('stage') for line in record_lines]
    assert stages == sorted(stages, key=lambda s: (s is not None, s or 0))


# ---- Comparing -------------------------------------------------------------------------------------------------------

def flat(records, errors=()):
    return ps.build_document(ps.StatsCollection(records=list(records), errors=list(errors)), DEFS, MOUS,
                             ps.OutputFormat.FLAT, ps.ALL_AUDIENCES)


def test_identical_documents_match_across_formats():
    collection = make_collection()
    nested = ps.build_document(collection, DEFS, MOUS, ps.OutputFormat.NESTED, ps.ALL_AUDIENCES)
    assert ps.compare_stats(flat(collection.records), nested) == []


def test_tolerance_comes_from_definition_then_default():
    reference = flat([ps.StatRecord('per_spw_stat', 100.0, {'spw': '1'}), ps.StatRecord('eb_stat', 100.0)])
    within_definition = flat([ps.StatRecord('per_spw_stat', 105.0, {'spw': '1'}), ps.StatRecord('eb_stat', 100.0)])
    assert ps.compare_stats(reference, within_definition) == []

    outside_default = flat([ps.StatRecord('per_spw_stat', 100.0, {'spw': '1'}), ps.StatRecord('eb_stat', 100.1)])
    differences = ps.compare_stats(reference, outside_default, default_rel_tol=1e-7)
    assert len(differences) == 1 and differences[0].startswith('eb_stat: expected 100.0, got 100.1')
    assert ps.compare_stats(reference, outside_default, default_rel_tol=0.01) == []


def test_missing_unexpected_and_ignored_statistics():
    reference = flat([ps.StatRecord('eb_stat', 1, {'eb': 'a.ms'}, 3, 't'), ps.StatRecord('ignored_stat', 'x')])
    new = flat([ps.StatRecord('eb_stat', 1, {'eb': 'b.ms'}, 3, 't')])
    assert ps.compare_stats(reference, new) == ['Missing: eb_stat [stage 3 t] eb=a.ms',
                                                'Unexpected: eb_stat [stage 3 t] eb=b.ms']


def test_stage_number_is_part_of_the_address():
    reference = flat([ps.StatRecord('eb_stat', 1, stage=3, task='t')])
    new = flat([ps.StatRecord('eb_stat', 1, stage=4, task='t')])
    assert len(ps.compare_stats(reference, new)) == 2


def test_duplicate_addresses_are_matched_in_order():
    reference = flat([ps.StatRecord('eb_stat', 1), ps.StatRecord('eb_stat', 2)])
    assert ps.compare_stats(reference, flat([ps.StatRecord('eb_stat', 1), ps.StatRecord('eb_stat', 2)])) == []
    assert len(ps.compare_stats(reference, flat([ps.StatRecord('eb_stat', 2), ps.StatRecord('eb_stat', 1)]))) == 2
    assert ps.compare_stats(reference, flat([ps.StatRecord('eb_stat', 1)])) == [
        'eb_stat: expected 2 value(s), got 1']


def test_nested_values_and_paths_in_messages():
    reference = flat([ps.StatRecord('test_stat', {'a': [1.0, 2.0], 'b': 'x'})])
    new = flat([ps.StatRecord('test_stat', {'a': [1.0, 3.0], 'c': 'x'})])
    differences = ps.compare_stats(reference, new)
    assert differences == ['test_stat.b: missing', 'test_stat.c: unexpected',
                           'test_stat.a[1]: expected 2.0, got 3.0 (rel_tol=1e-07, abs_tol=1e-12)']


def test_extraction_errors_in_new_file_are_differences():
    error = {'extractor': 'x', 'stage': 2, 'task': 't', 'error': 'KeyError: y'}
    assert ps.compare_stats(flat([]), flat([], [error])) == [
        'Extraction error in new results: x (stage 2, t): KeyError: y']


# ---- Extractors on real Results classes ------------------------------------------------------------------------------

def run(func, result, context=None):
    collection = ps.StatsCollection()
    ps._run_extractor(collection, func.__name__, func, (result, context),
                      ps._Emitter(collection, pipeline_stats_definitions.DEFINITIONS, 8, 'hifv_checkflag'), 8, 'x')
    return collection


def test_checkflag_extractor():
    summaries = [{'name': 'before', 'flagged': 10, 'scan': {1: {'flagged': 4}, 2: {'flagged': 6}}}]
    result = CheckflagResults(summaries=summaries)
    result.inputs = {'vis': '/data/a.ms'}
    result.task = Checkflag

    handlers = [e for e in ps.default_registry().results_extractors if e.handles(result)]
    assert {e.name for e in handlers} == {'checkflag_flags', 'qa_scores'}

    collection = run(pipeline_stats_extractors.checkflag_flags, result)
    assert collection.errors == []
    assert [(r.name, r.dims, r.value) for r in collection.records] == [
        ('checkflag_num_rows_flagged', {'eb': 'a.ms', 'summary': 'before'}, 10),
        ('checkflag_num_rows_flagged_per_scan', {'eb': 'a.ms', 'summary': 'before', 'scan': '1'}, 4),
        ('checkflag_num_rows_flagged_per_scan', {'eb': 'a.ms', 'summary': 'before', 'scan': '2'}, 6),
        ('checkflag_num_rows_flagged', {'eb': 'a.ms', 'summary': 'after'}, None),
    ]


def test_qa_scores_extractor():
    result = basetask.Results()
    applies_to = pipelineqa.TargetDataSelection(vis={'/data/a.ms'}, spw={17, 19}, intent={'PHASE'})
    origin = pipelineqa.QAOrigin(metric_name='%Flagged', metric_score=np.float32(0.25))
    result.qa.pool[:] = [pipelineqa.QAScore(0.9, applies_to=applies_to, origin=origin),
                         pipelineqa.QAScore(1.0)]

    collection = run(pipeline_stats_extractors.qa_scores, result)
    assert collection.errors == []
    dims = {'metric': '%Flagged', 'eb': 'a.ms', 'intent': 'PHASE', 'spw': '17,19'}
    assert [(r.name, r.dims, r.value) for r in collection.records] == [
        ('qa_score', dims, 0.9),
        ('qa_metric', dims, 0.25),
        ('qa_score', {'metric': 'Unknown metric'}, 1.0),
        ('qa_metric', {'metric': 'Unknown metric'}, 'N/A'),
    ]
