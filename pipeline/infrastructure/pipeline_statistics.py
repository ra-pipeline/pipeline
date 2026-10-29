"""Pipeline statistics framework.

Pipeline statistics are individual values describing a pipeline run (e.g. the number of antennas in an EB, the
percentage of data flagged by a stage, a QA score). They are written to a JSON file that is delivered as a pipeline
product, and the same machinery writes the file used by the regression tests.

Data model:

    * StatDefinition: what a statistic *is* -- its name, description, units, tolerance, etc. There is one
      definition per name, kept in pipeline_stats_definitions.py.
    * StatRecord: one *measurement* of a statistic -- its name, the stage and task it came from, its dimensions
      (e.g. {'eb': 'uid___A002_X1.ms', 'spw': '17'}) and its value. A statistic that varies by spw has one record
      per spw. The address of a record is (name, stage, task, dims).

Extractors are plain functions registered with the module-level ``registry`` (see pipeline_stats_extractors.py).
Results extractors are called for every matching Results object; context extractors are called once per run.
Both produce records by calling ``emit(name, value, **dims)``. Any exception raised by an extractor is recorded in
the ``errors`` section of the output instead of stopping the run.

Output formats (both contain the sections header, definitions and errors):

    * flat: a ``stats`` list with one record per line, sorted by stage. Used for regression test files.
    * nested: records nested under the MOUS by dimension, e.g. ``<mous>.EB.<eb>.SPW.<spw>.<name>``, with per-stage
      statistics under ``STAGE.<stage number>``. This is the format of the delivered product.

Both formats can be read back into records with ``document_to_records``, which is what the comparator uses.
"""
from __future__ import annotations

import collections.abc
import dataclasses
import datetime
import enum
import json
import math
import numbers
import os
import re
import traceback
from typing import TYPE_CHECKING, Any, Callable, Iterable, Iterator

import numpy as np

import pipeline.infrastructure as infrastructure
from pipeline.infrastructure import basetask
from pipeline.infrastructure.taskregistry import task_registry

if TYPE_CHECKING:
    from pipeline.infrastructure.basetask import Results
    from pipeline.infrastructure.launcher import Context

LOG = infrastructure.logging.get_logger(__name__)

# Version of the pipeline stats file format. Bump when the structure of the file changes.
FILE_FORMAT_VERSION = '2.0'

# Dimension vocabulary. The order of this dict is the order in which dimensions are nested in nested output, and
# the values are the labels used for each dimension in nested output.
DIMENSIONS: dict[str, str] = {
    'eb': 'EB',
    'session': 'SESSION',
    'source': 'TARGET',
    'field': 'FIELD',
    'intent': 'INTENT',
    'band': 'BAND',
    'spw': 'SPW',
    'ant': 'ANT',
    'scan': 'SCAN',
    'pol': 'POL',
    'stokes': 'STOKES',
    'specmode': 'SPECMODE',
    'datatype': 'DATATYPE',
    'reason': 'REASON',
    'summary': 'SUMMARY',
    'metric': 'METRIC',
}
_LABEL_TO_DIMENSION = {label: dim for dim, label in DIMENSIONS.items()}

# Top-level keys of a stats document other than the MOUS.
HEADER_KEY = 'header'
DEFINITIONS_KEY = 'definitions'
ERRORS_KEY = 'errors'
STATS_KEY = 'stats'
STAGE_KEY = 'STAGE'
_RESERVED_KEYS = {HEADER_KEY, DEFINITIONS_KEY, ERRORS_KEY, STATS_KEY, STAGE_KEY}


class Audience(enum.Enum):
    """Who a statistic is for. Product statistics are delivered; test statistics are only used by regression tests."""
    PRODUCT = 'product'
    TEST = 'test'


ALL_AUDIENCES = frozenset(Audience)


class OutputFormat(enum.Enum):
    """Layout of a pipeline stats file."""
    FLAT = 'flat'
    NESTED = 'nested'


@dataclasses.dataclass(frozen=True)
class StatDefinition:
    """Definition of a pipeline statistic. There is exactly one definition per statistic name.

    Attributes:
        name: Name of the statistic.
        description: Long description of the statistic.
        units: Units of the value, if any.
        audience: Whether the statistic is delivered in the product file or only used by regression tests.
        per_stage: If True, the statistic describes a stage (e.g. its duration or QA scores) and is placed under
            STAGE.<stage number> in nested output.
        priority: Priority from the pipeline statistics specification, if any.
        rel_tol: Relative tolerance used when comparing values in regression tests. None means use the test default.
        abs_tol: Absolute tolerance used when comparing values in regression tests. None means use the test default.
        compare: If False, regression tests ignore this statistic (e.g. run times and version strings).
    """
    name: str
    description: str
    units: str = ''
    audience: Audience = Audience.PRODUCT
    per_stage: bool = False
    priority: int | None = None
    rel_tol: float | None = None
    abs_tol: float | None = None
    compare: bool = True

    def to_dict(self) -> dict:
        return {
            'description': self.description,
            'units': self.units,
            'audience': self.audience.value,
            'per_stage': self.per_stage,
            'priority': self.priority,
            'rel_tol': self.rel_tol,
            'abs_tol': self.abs_tol,
            'compare': self.compare,
        }

    @classmethod
    def from_dict(cls, name: str, d: dict) -> StatDefinition:
        return cls(name=name,
                   description=d.get('description', ''),
                   units=d.get('units', ''),
                   audience=Audience(d.get('audience', Audience.PRODUCT.value)),
                   per_stage=d.get('per_stage', False),
                   priority=d.get('priority'),
                   rel_tol=d.get('rel_tol'),
                   abs_tol=d.get('abs_tol'),
                   compare=d.get('compare', True))


def build_definitions(definitions: Iterable[StatDefinition]) -> dict[str, StatDefinition]:
    """Index definitions by name, checking that names are unique and cannot be confused with nesting labels."""
    by_name = {}
    for definition in definitions:
        if definition.name in by_name:
            raise ValueError(f'Duplicate pipeline statistic definition: {definition.name}')
        if definition.name in _LABEL_TO_DIMENSION or definition.name in _RESERVED_KEYS:
            raise ValueError(f'Pipeline statistic name {definition.name} clashes with a reserved key')
        by_name[definition.name] = definition
    return by_name


@dataclasses.dataclass
class StatRecord:
    """One measurement of a pipeline statistic.

    Attributes:
        name: Name of the statistic; must have a StatDefinition.
        value: JSON-serializable value: a scalar, a list (e.g. a spectrum) or a dict.
        dims: Dimensions the value applies to, e.g. {'eb': 'uid___A002_X1.ms', 'spw': '17'}. Values are strings.
        stage: Number of the stage that produced the value, or None for values not tied to a stage.
        task: Name of the task the value came from (e.g. 'hifa_bandpass'), or None.
    """
    name: str
    value: Any
    dims: dict[str, str] = dataclasses.field(default_factory=dict)
    stage: int | None = None
    task: str | None = None

    @property
    def key(self) -> tuple:
        """The address of this record: (name, stage, task, dims)."""
        return self.name, self.stage, self.task, tuple(sorted(self.dims.items()))

    def to_dict(self) -> dict:
        d = {'name': self.name}
        if self.stage is not None:
            d['stage'] = self.stage
        if self.task is not None:
            d['task'] = self.task
        if self.dims:
            d['dims'] = dict(self.dims)
        d['value'] = self.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> StatRecord:
        return cls(name=d['name'], value=d.get('value'), dims=dict(d.get('dims', {})),
                   stage=d.get('stage'), task=d.get('task'))


def format_address(key: tuple) -> str:
    """Human-readable form of a record address, used in log and test failure messages."""
    name, stage, task, dims = key
    parts = [name]
    if stage is not None or task is not None:
        parts.append('[' + ' '.join(str(x) for x in ('stage', stage, task) if x is not None) + ']')
    parts.extend(f'{k}={v}' for k, v in dims)
    return ' '.join(parts)


def to_serializable(value: Any) -> Any:
    """Convert a value from the pipeline into something json can write.

    Raises TypeError for values that cannot be converted, so the extractor that produced them is reported.
    """
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        return float(value)
    if isinstance(value, np.ndarray):
        return [to_serializable(v) for v in value.tolist()]
    if isinstance(value, (set, frozenset)):
        return sorted((to_serializable(v) for v in value), key=_natural_key)
    if isinstance(value, (list, tuple)):
        return [to_serializable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): to_serializable(v) for k, v in value.items()}
    raise TypeError(f'Cannot serialize value of type {type(value).__name__}: {value!r}')


def _natural_key(value: Any) -> tuple:
    """Sort key that orders '2' before '10' and copes with mixed types."""
    s = str(value)
    return tuple((0, int(part), '') if part.isdigit() else (1, 0, part) for part in re.split(r'(\d+)', s))


def _record_sort_key(record: StatRecord) -> tuple:
    return (record.stage is not None, record.stage or 0, record.task or '', record.name,
            tuple((k, _natural_key(v)) for k, v in sorted(record.dims.items())))


# ---------------------------------------------------------------------------------------------------------------------
# Extractor registry
# ---------------------------------------------------------------------------------------------------------------------

# Signature of the emit function given to extractors: emit(name, value, *, stage=None, task=None, **dims)
Emit = Callable[..., None]


@dataclasses.dataclass(frozen=True)
class ResultsExtractor:
    """A function that extracts statistics from one type of Results object.

    Attributes:
        func: Called as func(result, context, emit).
        result_cls: The Results class (or tuple of classes) handled.
        generating_task: The task class that generated the results, or None to handle results of result_cls
            regardless of which task generated them.
        top_level_only: If True, only the stage's top-level Results (or ResultsList) is offered to the extractor,
            not the Results it contains.
    """
    func: Callable[[Results, Context, Emit], None]
    result_cls: type | tuple[type, ...]
    generating_task: type | None = None
    top_level_only: bool = False

    @property
    def name(self) -> str:
        return self.func.__name__

    def handles(self, result: Results) -> bool:
        if not isinstance(result, self.result_cls):
            return False
        if self.generating_task is None:
            return True
        task = getattr(result, 'task', None)
        return task is self.generating_task or task is getattr(self.generating_task, 'Task', None)


@dataclasses.dataclass(frozen=True)
class ContextExtractor:
    """A function that extracts statistics from the context, called once per run as func(context, emit)."""
    func: Callable[[Context, Emit], None]

    @property
    def name(self) -> str:
        return self.func.__name__


class ExtractorRegistry:
    """Registry of statistics extractors. Extractors register themselves at import time with the decorators."""

    def __init__(self):
        self.results_extractors: list[ResultsExtractor] = []
        self.context_extractors: list[ContextExtractor] = []

    def results(self, result_cls: type | tuple[type, ...], generating_task: type | None = None,
                top_level_only: bool = False) -> Callable:
        """Decorator registering a results extractor: func(result, context, emit)."""
        def decorator(func):
            self.results_extractors.append(ResultsExtractor(func, result_cls, generating_task, top_level_only))
            return func
        return decorator

    def context(self, func: Callable) -> Callable:
        """Decorator registering a context extractor: func(context, emit)."""
        self.context_extractors.append(ContextExtractor(func))
        return func


registry = ExtractorRegistry()


# ---------------------------------------------------------------------------------------------------------------------
# Collecting statistics
# ---------------------------------------------------------------------------------------------------------------------

@dataclasses.dataclass
class StatsCollection:
    """The records and extraction errors gathered from one pipeline run."""
    records: list[StatRecord] = dataclasses.field(default_factory=list)
    errors: list[dict] = dataclasses.field(default_factory=list)


class _Emitter:
    """The emit function handed to an extractor. Validates and stores records with the current stage and task."""

    def __init__(self, collection: StatsCollection, definitions: dict[str, StatDefinition],
                 stage: int | None = None, task: str | None = None):
        self._collection = collection
        self._definitions = definitions
        self._stage = stage
        self._task = task

    def __call__(self, name: str, value: Any, *, stage: int | None = None, task: str | None = None, **dims) -> None:
        if name not in self._definitions:
            raise KeyError(f'No definition for pipeline statistic {name!r}')
        unknown = set(dims) - set(DIMENSIONS)
        if unknown:
            raise KeyError(f'Unknown dimension(s) {sorted(unknown)} for pipeline statistic {name!r}')
        record = StatRecord(
            name=name,
            value=to_serializable(value),
            dims={k: _dimension_value(v) for k, v in dims.items() if v is not None},
            stage=stage if stage is not None else self._stage,
            task=task if task is not None else self._task,
        )
        self._collection.records.append(record)


def _dimension_value(value: Any) -> str:
    """Dimension values are strings so that flat and nested files (where they are JSON keys) agree."""
    if isinstance(value, (set, frozenset, list, tuple)):
        return ','.join(str(v) for v in sorted(value, key=_natural_key))
    return str(value)


def _run_extractor(collection: StatsCollection, extractor_name: str, func: Callable, args: tuple,
                   emit: _Emitter, stage: int | None, task: str | None) -> None:
    """Call an extractor, recording any exception in the errors section rather than raising it."""
    n_before = len(collection.records)
    try:
        func(*args, emit)
    except Exception as e:
        # Discard partial output so a failed extractor never leaves half its values in the file.
        del collection.records[n_before:]
        LOG.warning('Pipeline statistics extractor %s failed for stage %s (%s): %s', extractor_name, stage, task, e)
        LOG.debug(traceback.format_exc())
        collection.errors.append({
            'extractor': extractor_name,
            'stage': stage,
            'task': task,
            'error': f'{type(e).__name__}: {e}',
        })


def stage_number(result: Results) -> int | None:
    """Stage number of a Results or ResultsList."""
    stage = getattr(result, 'stage_number', None)
    if stage is None and isinstance(result, basetask.ResultsList) and len(result):
        return stage_number(result[0])
    return stage


def task_name(result: Results) -> str | None:
    """CASA task name (e.g. 'hifa_bandpass') of the task that produced a Results or ResultsList."""
    if isinstance(result, basetask.FailedTaskResults):
        task_cls = result.origtask_cls
    elif isinstance(result, basetask.ResultsList):
        return task_name(result[0]) if len(result) else None
    else:
        task_cls = getattr(result, 'task', None)
    if task_cls is None:
        return None
    try:
        return task_registry.get_casa_task(task_cls)
    except KeyError:
        return getattr(task_cls, '__name__', str(task_cls))


def _walk_results(result: Results) -> Iterator[Results]:
    """Yield a result and, for results containers, every Results it contains (depth first, children first)."""
    if isinstance(result, collections.abc.Iterable) and not isinstance(result, (str, bytes, dict)):
        for child in result:
            if isinstance(child, (basetask.Results, basetask.ResultsList)):
                yield from _walk_results(child)
    yield result


def collect_stats(context: Context, definitions: dict[str, StatDefinition] | None = None,
                  extractor_registry: ExtractorRegistry | None = None) -> StatsCollection:
    """Run every registered extractor over the context and its results."""
    if definitions is None:
        definitions = default_definitions()
    if extractor_registry is None:
        extractor_registry = default_registry()

    collection = StatsCollection()

    LOG.info('Gathering pipeline statistics from the context')
    for extractor in extractor_registry.context_extractors:
        emit = _Emitter(collection, definitions)
        _run_extractor(collection, extractor.name, extractor.func, (context,), emit, None, None)

    LOG.info('Gathering pipeline statistics from results')
    for results_proxy in context.results:
        top_level = results_proxy.read()
        for result in _walk_results(top_level):
            stage = stage_number(result)
            if stage is None:
                stage = stage_number(top_level)
            task = task_name(result) or task_name(top_level)
            for extractor in extractor_registry.results_extractors:
                if extractor.top_level_only and result is not top_level:
                    continue
                if extractor.handles(result):
                    emit = _Emitter(collection, definitions, stage=stage, task=task)
                    _run_extractor(collection, extractor.name, extractor.func, (result, context), emit, stage, task)

    return collection


def default_definitions() -> dict[str, StatDefinition]:
    from pipeline.infrastructure import pipeline_stats_definitions
    return pipeline_stats_definitions.DEFINITIONS


def default_registry() -> ExtractorRegistry:
    # Importing the extractors module registers its extractors with the module-level registry.
    from pipeline.infrastructure import pipeline_stats_extractors  # noqa: F401
    return registry


# ---------------------------------------------------------------------------------------------------------------------
# Building documents (the content of a stats file)
# ---------------------------------------------------------------------------------------------------------------------

def _generate_header(fmt: OutputFormat, audiences: frozenset[Audience], mous: str) -> dict:
    now = datetime.datetime.now(datetime.timezone.utc)
    return {
        'version': FILE_FORMAT_VERSION,
        'format': fmt.value,
        'audiences': sorted(a.value for a in audiences),
        'mous': mous,
        'stats_file_creation_date': now.strftime('%Y/%m/%d %H:%M:%S %Z'),
    }


def build_document(collection: StatsCollection, definitions: dict[str, StatDefinition], mous: str,
                   fmt: OutputFormat = OutputFormat.NESTED,
                   audiences: Iterable[Audience] = (Audience.PRODUCT,)) -> dict:
    """Build the JSON-serializable content of a stats file from collected statistics.

    Args:
        collection: Records and errors from collect_stats.
        definitions: Definitions by name.
        mous: MOUS identifier; the key under which nested statistics are placed.
        fmt: Flat or nested layout.
        audiences: Only statistics for these audiences are included.
    """
    audiences = frozenset(audiences)
    records = sorted((r for r in collection.records if definitions[r.name].audience in audiences),
                     key=_record_sort_key)
    used = sorted({r.name for r in records})

    document = {
        HEADER_KEY: _generate_header(fmt, audiences, mous),
        DEFINITIONS_KEY: {name: definitions[name].to_dict() for name in used},
        ERRORS_KEY: list(collection.errors),
    }
    if fmt is OutputFormat.FLAT:
        document[STATS_KEY] = [r.to_dict() for r in records]
    else:
        document.update(_nest_records(records, definitions, mous))
    return document


def _nest_records(records: list[StatRecord], definitions: dict[str, StatDefinition], mous: str) -> dict:
    """Nest records by dimension, in DIMENSIONS order, under the MOUS (or STAGE.<n> for per-stage statistics).

    The leaf is {value, units, longdescription, origin (the task), stage}. If several records end up at the same
    leaf (e.g. a statistic produced by two stages with the same dims), the leaf is a list of these dicts.
    """
    nested = {mous: {}}
    for record in records:
        definition = definitions[record.name]
        if definition.per_stage and record.stage is not None:
            node = nested.setdefault(STAGE_KEY, {}).setdefault(str(record.stage), {})
        else:
            node = nested[mous]
        for dim in sorted(record.dims, key=list(DIMENSIONS).index):
            node = node.setdefault(DIMENSIONS[dim], {}).setdefault(record.dims[dim], {})

        leaf = {'value': record.value}
        if definition.units:
            leaf['units'] = definition.units
        leaf['longdescription'] = definition.description
        if record.task is not None:
            leaf['origin'] = record.task
        if record.stage is not None:
            leaf['stage'] = record.stage

        existing = node.get(record.name)
        if existing is None:
            node[record.name] = leaf
        elif isinstance(existing, list):
            existing.append(leaf)
        else:
            node[record.name] = [existing, leaf]
    return nested


def document_to_records(document: dict) -> list[StatRecord]:
    """Read the records back out of a flat or nested stats document."""
    if STATS_KEY in document:
        return [StatRecord.from_dict(d) for d in document[STATS_KEY]]

    records = []
    for key, node in document.items():
        if key == STAGE_KEY:
            for stage, stage_node in node.items():
                _unnest(stage_node, {}, int(stage), records)
        elif key not in _RESERVED_KEYS:
            _unnest(node, {}, None, records)
    return records


def _unnest(node: dict, dims: dict, stage: int | None, records: list[StatRecord]) -> None:
    for key, value in node.items():
        if key in _LABEL_TO_DIMENSION:
            dim = _LABEL_TO_DIMENSION[key]
            for dim_value, child in value.items():
                _unnest(child, {**dims, dim: dim_value}, stage, records)
        else:
            for leaf in (value if isinstance(value, list) else [value]):
                records.append(StatRecord(name=key, value=leaf.get('value'), dims=dict(dims),
                                          stage=leaf.get('stage', stage), task=leaf.get('origin')))


def document_definitions(document: dict) -> dict[str, StatDefinition]:
    return {name: StatDefinition.from_dict(name, d) for name, d in document.get(DEFINITIONS_KEY, {}).items()}


# ---------------------------------------------------------------------------------------------------------------------
# Writing and reading files
# ---------------------------------------------------------------------------------------------------------------------

def dumps_document(document: dict) -> str:
    """Serialize a stats document.

    Flat documents are written with one definition, error and record per line so that diffs of regression
    reference files show the full address of every changed value. Nested documents are indented.
    """
    if STATS_KEY not in document:
        return json.dumps(document, ensure_ascii=False, indent=4, sort_keys=True)

    def one_per_line(items: list[str]) -> str:
        if not items:
            return ''
        return '\n' + ',\n'.join(f'    {item}' for item in items) + '\n  '

    def dumps(obj):
        return json.dumps(obj, ensure_ascii=False, sort_keys=True)

    header = json.dumps(document[HEADER_KEY], ensure_ascii=False, indent=4, sort_keys=True).replace('\n', '\n  ')
    definitions = [f'{dumps(name)}: {dumps(d)}' for name, d in sorted(document[DEFINITIONS_KEY].items())]
    errors = [dumps(e) for e in document[ERRORS_KEY]]
    stats = [dumps(r) for r in document[STATS_KEY]]
    return (
        '{\n'
        f'  {dumps(HEADER_KEY)}: {header},\n'
        f'  {dumps(DEFINITIONS_KEY)}: {{{one_per_line(definitions)}}},\n'
        f'  {dumps(ERRORS_KEY)}: [{one_per_line(errors)}],\n'
        f'  {dumps(STATS_KEY)}: [{one_per_line(stats)}]\n'
        '}\n'
    )


def generate_stats(context: Context, fmt: OutputFormat = OutputFormat.NESTED,
                   audiences: Iterable[Audience] = (Audience.PRODUCT,)) -> dict:
    """Gather statistics from the context and results and return the content of a stats file."""
    definitions = default_definitions()
    collection = collect_stats(context, definitions)
    return build_document(collection, definitions, mous=context.get_oussid(), fmt=fmt, audiences=audiences)


def write_stats_file(context: Context, filename: str, fmt: OutputFormat = OutputFormat.NESTED,
                     audiences: Iterable[Audience] = (Audience.PRODUCT,)) -> str:
    """Generate statistics for a pipeline run and write them to filename.

    The defaults produce the delivered product file. Regression tests use fmt=OutputFormat.FLAT and
    audiences=ALL_AUDIENCES.

    Returns:
        The filename written.
    """
    document = generate_stats(context, fmt=fmt, audiences=audiences)
    n_errors = len(document[ERRORS_KEY])
    if n_errors:
        LOG.warning('%d pipeline statistics extractor(s) failed; see the errors section of %s', n_errors, filename)
    LOG.info('Writing pipeline statistics to %s', filename)
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(dumps_document(document))
    return filename


def read_stats_file(filename: str) -> dict:
    with open(filename, encoding='utf-8') as f:
        return json.load(f)


# ---------------------------------------------------------------------------------------------------------------------
# Comparing stats files (regression tests)
# ---------------------------------------------------------------------------------------------------------------------

def compare_stats(reference: dict, new: dict, default_rel_tol: float = 1e-7,
                  default_abs_tol: float = 1e-12) -> list[str]:
    """Compare two stats documents (flat or nested) and return a list of differences; empty means they match.

    Records are matched by address (name, stage, task, dims). Records sharing an address are matched in order.
    Numbers are compared with the tolerances from the statistic's definition, falling back to the defaults.
    Statistics whose definition has compare=False are ignored. Any extraction error recorded in the new document is
    reported as a difference.
    """
    differences = [f'Extraction error in new results: {_format_error(e)}' for e in new.get(ERRORS_KEY, [])]

    definitions = {**document_definitions(reference), **document_definitions(new)}

    def group(document):
        grouped = collections.defaultdict(list)
        for record in document_to_records(document):
            definition = definitions.get(record.name)
            if definition is None or definition.compare:
                grouped[record.key].append(record.value)
        return grouped

    ref_records, new_records = group(reference), group(new)

    for key in sorted(ref_records.keys() - new_records.keys(), key=format_address):
        differences.append(f'Missing: {format_address(key)}')
    for key in sorted(new_records.keys() - ref_records.keys(), key=format_address):
        differences.append(f'Unexpected: {format_address(key)}')

    for key in sorted(ref_records.keys() & new_records.keys(), key=format_address):
        ref_values, new_values = ref_records[key], new_records[key]
        address = format_address(key)
        if len(ref_values) != len(new_values):
            differences.append(f'{address}: expected {len(ref_values)} value(s), got {len(new_values)}')
            continue
        definition = definitions.get(key[0])
        rel_tol = definition.rel_tol if definition and definition.rel_tol is not None else default_rel_tol
        abs_tol = definition.abs_tol if definition and definition.abs_tol is not None else default_abs_tol
        for ref_value, new_value in zip(ref_values, new_values):
            for path, message in _compare_values(ref_value, new_value, rel_tol, abs_tol, ''):
                differences.append(f'{address}{path}: {message}')

    return differences


def compare_stats_files(reference_file: str, new_file: str, default_rel_tol: float = 1e-7,
                        default_abs_tol: float = 1e-12) -> list[str]:
    """Compare two stats files. See compare_stats."""
    return compare_stats(read_stats_file(reference_file), read_stats_file(new_file),
                         default_rel_tol=default_rel_tol, default_abs_tol=default_abs_tol)


def _format_error(error: dict) -> str:
    return f"{error.get('extractor')} (stage {error.get('stage')}, {error.get('task')}): {error.get('error')}"


def _is_number(value: Any) -> bool:
    return isinstance(value, numbers.Real) and not isinstance(value, bool)


def _compare_values(ref: Any, new: Any, rel_tol: float, abs_tol: float, path: str) -> Iterator[tuple[str, str]]:
    """Yield (path within the value, message) for every difference between two values."""
    if _is_number(ref) and _is_number(new):
        if math.isnan(ref) and math.isnan(new):
            return
        if not math.isclose(ref, new, rel_tol=rel_tol, abs_tol=abs_tol):
            yield path, f'expected {ref}, got {new} (rel_tol={rel_tol}, abs_tol={abs_tol})'
    elif isinstance(ref, list) and isinstance(new, list):
        if len(ref) != len(new):
            yield path, f'expected {len(ref)} element(s), got {len(new)}'
            return
        for i, (r, n) in enumerate(zip(ref, new)):
            yield from _compare_values(r, n, rel_tol, abs_tol, f'{path}[{i}]')
    elif isinstance(ref, dict) and isinstance(new, dict):
        for k in sorted(ref.keys() - new.keys(), key=_natural_key):
            yield f'{path}.{k}', 'missing'
        for k in sorted(new.keys() - ref.keys(), key=_natural_key):
            yield f'{path}.{k}', 'unexpected'
        for k in sorted(ref.keys() & new.keys(), key=_natural_key):
            yield from _compare_values(ref[k], new[k], rel_tol, abs_tol, f'{path}.{k}')
    elif ref != new:
        yield path, f'expected {ref!r}, got {new!r}'


# ---------------------------------------------------------------------------------------------------------------------
# Helpers for extractors
# ---------------------------------------------------------------------------------------------------------------------

def vis_name(vis: str | list[str]) -> str:
    """EB name used in the 'eb' dimension: the basename of the MS (the first one if given a list)."""
    if isinstance(vis, (list, tuple)):
        vis = vis[0]
    return os.path.basename(os.path.normpath(vis))
