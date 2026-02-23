"""general-purpose uncategorised utility functions and classes."""
from __future__ import annotations

import ast
import bisect
import collections
import contextlib
import copy
import errno
import fcntl
import glob
import inspect
import itertools
import json
import operator
import os
import pickle
import re
import shutil
import string
import tarfile
import time
from collections.abc import Callable, Collection, Iterable, Iterator, Sequence
from datetime import datetime
from functools import wraps
from numbers import Number
from typing import TYPE_CHECKING, Any, DefaultDict, OrderedDict, TextIO, TypedDict
from urllib.parse import urlparse

import numpy as np
import numpy.typing as npt

from pipeline import infrastructure
from pipeline.infrastructure import casa_tools
from .conversion import commafy, dequote, range_to_list

if TYPE_CHECKING:
    from pipeline.domain import Field, MeasurementSet
    from pipeline.infrastructure.filenamer import PipelineProductNameBuilder
    from pipeline.infrastructure.launcher import Context

LOG = infrastructure.logging.get_logger(__name__)

__all__ = [
    'absolute_path',
    'approx_equal',
    'are_equal',
    'clear_time_cache',
    'compute_zenith_distance',
    'deduplicate',
    'dict_merge',
    'ensure_products_dir_exists',
    'export_weblog_as_tar',
    'fieldname_clean',
    'fieldname_for_casa',
    'filter_intents_for_ms',
    'find_ranges',
    'flagged_intervals',
    'get_casa_quantity',
    'get_field_identifiers',
    'get_obj_size',
    'get_products_dir',
    'get_receiver_type_for_spws',
    'get_row_count',
    'get_si_prefix',
    'get_spectralspec_to_spwid_map',
    'get_stokes',
    'get_task_result_count',
    'get_taskhistory_fromimage',
    'get_valid_url',
    'glob_ordered',
    'ignore_pointing',
    'imstat_items',
    'list_to_str',
    'nested_dict',
    'obs_long_lat',
    'obs_midtime',
    'open_with_lock',
    'place_repr_source_first',
    'relative_path',
    'remove_trailing_string',
    'string_to_val',
    'validate_url',
    'DirectionDict',
    'EpochDict',
    'QuantityDict',
]


class QuantityDict(TypedDict):
    unit: str
    value: float


class DirectionDict(TypedDict):
    m0: QuantityDict
    m1: QuantityDict
    refer: str
    type: str


class EpochDict(TypedDict):
    m0: QuantityDict
    refer: str
    type: str


def find_ranges(data: str | list[int]) -> str:
    """Identify numeric ranges in string or list.

    This utility function takes a string or a list of integers (e.g. spectral
    window lists) and returns a string containing identified ranges.

    Examples:
    >>> find_ranges([1,2,3])
    '1~3'
    >>> find_ranges('1,2,3,5~12')
    '1~3,5~12'
    """
    if isinstance(data, str):
        # barf if channel ranges are also in data, eg. 23:1~10,24
        if ':' in data:
            return data

        data = range_to_list(data)
        if len(data) == 0:
            return ''

    try:
        integers = [int(d) for d in data]
    except ValueError:
        return ','.join(data)

    s = sorted(integers)
    ranges = []
    for _, g in itertools.groupby(enumerate(s), lambda i_x: i_x[0] - i_x[1]):
        rng = list(map(operator.itemgetter(1), g))
        if len(rng) == 1:
            ranges.append('%s' % rng[0])
        else:
            ranges.append('%s~%s' % (rng[0], rng[-1]))
    return ','.join(ranges)


def dict_merge(a: dict, b: dict | Any) -> dict:
    """Recursively merge dictionaries.

    This utility function recursively merges dictionaries. If second argument
    (b) is a dictionary, then a copy of first argument (dictionary a) is created
    and the elements of b are merged into the new dictionary. Otherwise return
    argument b.

    Examples:
    >>> dict_merge({'a': {'b': 1}}, {'c': 2})
    {'a': {'b': 1}, 'c': 2}
    """
    if not isinstance(b, dict):
        return b
    result = copy.deepcopy(a)
    for k, v in b.items():
        if k in result and isinstance(result[k], dict):
            result[k] = dict_merge(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result


def are_equal(a: list | np.ndarray, b: list | np.ndarray) -> bool:
    """Return True if the contents of the given arrays are equal.

    This utility function check the equivalence of array like objects. Two arrays
    are equal if they have the same number of elements and elements of the same
    index are equal.

    Examples:
    >>> are_equal([1, 2, 3], [1, 2, 3])
    True
    >>> are_equal([1, 2, 3], [1, 2, 3, 4])
    False
    """
    return len(a) == len(b) and len(a) == sum([1 for i, j in zip(a, b) if i == j])


def approx_equal(x: float, y: float, tol: float = 1e-15) -> bool:
    """Return True if two numbers are equal within the given tolerance.

    This utility function returns True if two numbers are equal within the
    given tolerance.

    Examples:
    >>> approx_equal(1.0e-2, 1.2e-2, 1e-2)
    True
    >>> approx_equal(1.0e-2, 1.2e-2, 1e-3)
    False
    """
    lo = min(x, y)
    hi = max(x, y)
    return (lo + 0.5 * tol) >= (hi - 0.5 * tol)


def flagged_intervals(vec: list | np.ndarray) -> list:
    """Idendity isnads of ones in input array or list.

    This utility function finds islands of ones in array or list provided in argument.
    Used to find contiguous flagged channels in a given spw.  Returns a list of
    tuples with the start and end channels.

    Examples:
    >>> flagged_intervals([0, 1, 0, 1, 1])
    [(1, 1), (3, 4)]
    """
    if len(vec) == 0:
        return []
    elif not isinstance(vec, np.ndarray):
        vec = np.array(vec)

    edges, = np.nonzero(np.diff((vec == True) * 1))
    edge_vec = [edges + 1]
    if vec[0] != 0:
        edge_vec.insert(0, [0])
    if vec[-1] != 0:
        edge_vec.append([len(vec)])
    edges = np.concatenate(edge_vec)
    return list(zip(edges[::2], edges[1::2] - 1))


def fieldname_for_casa(field: str) -> str:
    """Prepare field string to be used as CASA argument.

    This utility function ensures that field string can be used as CASA argument.

    If field contains special characters, then return field string enclose in
    quotation marks, otherwise return unchanged string.

    Examples:
    >>> fieldname_for_casa('helm=30')
    '"helm=30"'
    """
    if field.isdigit() or field != fieldname_clean(field):
        return '"{0}"'.format(field)
    return field


def fieldname_clean(field: str) -> str:
    """Indicate if the fieldname is allowed as-is.

    This utility function replaces special characters in string with underscore.
    The return string is used in fieldname_for_casa() function to determine
    whether the field name, when given as a CASA argument, should be enclosed
    in quotes.

    Examples:
    >>> fieldname_clean('helm=30')
    'helm_30'
    """
    allowed = string.ascii_letters + string.digits + '+-'
    return ''.join([c if c in allowed else '_' for c in field])


def filter_intents_for_ms(ms: MeasurementSet, intents: str) -> str:
    """
    Filter string of comma-separated intents to keep only those that are present
    in the given MS.
    """
    intents = set(intents.split(','))
    removed_intents = intents - ms.intents
    if removed_intents:
        LOG.debug(f"The following intents are not present in the MS {ms.basename} and will be skipped:"
                  f" {commafy(removed_intents)}")
    intents.intersection_update(ms.intents)
    return ','.join(sorted(intents))


def get_field_accessor(ms: MeasurementSet, field: Field) -> operator.attrgetter:
    """Returns accessor to field name or field ID, if field name is ambiguous.
    """
    fields = ms.get_fields(name=field.name)
    if len(fields) == 1:
        return operator.attrgetter('name')

    def accessor(x):
        return str(operator.attrgetter('id')(x))
    return accessor


def get_field_identifiers(ms: MeasurementSet) -> dict[int, str | int]:
    """Maps numeric field IDs to field names.

    Get a dict of numeric field ID to unambiguous field identifier, using the
    field name where possible and falling back to numeric field ID where the
    name is duplicated, for instance in mosaic pointings.
    """
    field_name_accessors = {field.id: get_field_accessor(ms, field) for field in ms.fields}
    return {field.id: field_name_accessors[field.id](field) for field in ms.fields}


def get_receiver_type_for_spws(ms: MeasurementSet, spwids: Sequence) -> dict[int, str]:
    """Return dictionary of receiver types for requested spectral window IDs.

    If spwid is not found in MeasurementSet instance, then detector type is
    set to "N/A".

    Args:
        ms: MeasurementSet to query for receiver types.
        spwids: list of spw ids (integers) to query for.

    Returns:
        A dictionary assigning receiver types as values to spwid keys.
    """
    rxmap = {}
    for spwid in spwids:
        spw = ms.get_spectral_windows(spwid, science_windows_only=False)
        if not spw:
            rxmap[spwid] = "N/A"
        else:
            rxmap[spwid] = spw[0].receiver
    return rxmap


def get_spectralspec_to_spwid_map(spws: Collection) -> DefaultDict[str | None, list[int]]:
    """
    Returns a dictionary of spectral specs mapped to corresponding spectral
    window IDs for requested list of spectral window objects.

    :param spws: list of spectral window objects
    :return: dictionary with spectral spec as keys, and corresponding
    list of spectral window IDs as values.
    """
    spwmap = collections.defaultdict(list)
    for spw in sorted(spws, key=lambda s: s.id):
        spwmap[spw.spectralspec].append(spw.id)
    return spwmap


def imstat_items(
        image: Any,
        items: list[str] = ['min', 'max'],
        mask: str | None = None,
        ) -> OrderedDict[str, Any]:
    """Extract desired stats properties (per Stokes) using ia.statistics().

    Beside the standard output, some additional stats property keys are supported.
    Note: 'image' is expected to an instance of CASA ia tool.
    """

    imstats = image.statistics(robust=True, axes=[0, 1, 3], mask=mask)
    stats = collections.OrderedDict()

    for item in items:
        if item.lower() == 'madrms':
            stats['madrms'] = imstats['medabsdevmed']*1.4826  # see CAS-9631
        elif item.lower() == 'max/madrms':
            stats['max/madrms'] = imstats['max']/imstats['medabsdevmed']*1.4826  # see CAS-9631
        elif item.lower() == 'maxabs':
            stats['maxabs'] = np.maximum(np.abs(imstats['max']), np.abs(imstats['min']))
        elif 'pct<' in item:
            threshold = float(item.replace('pct<', ''))
            imstats_threshold = image.statistics(robust=True, axes=[0, 1, 3], includepix=[0, threshold], mask=mask)
            if len(imstats_threshold['npts']) == 0:
                # if no pixel is selected from the restricted pixel value range, the return of ia.statitics() would be empty.
                imstats_threshold['npts'] = np.zeros(4)
            stats[item] = imstats_threshold['npts']/imstats['npts']
        elif item.lower() == 'pct_masked':
            im_shape = (imstats['trc']-imstats['blc'])+1
            stats[item] = 1.-imstats['npts']/im_shape[0]/im_shape[1]
        elif item.lower() == 'peak':  # Here 'peak' means the pixel value with largest deviation from zero.
            stats[item] = np.where(np.abs(imstats['max']) > np.abs(imstats['min']), imstats['max'], imstats['min'])
        elif item.lower() == 'peak/madrms':
            peak = np.where(np.abs(imstats['max']) > np.abs(imstats['min']), imstats['max'], imstats['min'])
            madrms = imstats['medabsdevmed']*1.4826  # see CAS-9631
            stats['peak/madrms'] = peak/madrms
        else:
            stats[item] = imstats[item.lower()]

    return stats


def get_stokes(imagename: str) -> list[str]:
    """Get the labels of all stokes planes present in a CASA image."""

    with casa_tools.ImageReader(imagename) as image:
        cs = image.coordsys()
        stokes_labels = cs.stokes()
        stokes_present = [stokes_labels[idx] for idx in range(image.shape()[2])]
        cs.done()

    return stokes_present


def get_casa_quantity(value: None | dict | str | float | int) -> QuantityDict:
    """Wrapper around quanta.quantity() that handles None input.

    Starting with CASA 6, quanta.quantity() no longer accepts None as input. This
    utility function handles None values when calling CASA quanta.quantity() tool
    method.

    Returns:
        A CASA quanta.quantity (dictionary)

    Examples:
    >>> get_casa_quantity(None)
    {'unit': '', 'value': 0.0}
    >>> get_casa_quantity('10klambda')
    {'unit': 'klambda', 'value': 10.0}
    """
    if value is not None:
        return casa_tools.quanta.quantity(value)
    else:
        return casa_tools.quanta.quantity(0.0)


def get_si_prefix(value: float, select: str = 'mu', lztol: int = 0) -> tuple[str, float]:
    """Obtain the best SI unit prefix option for a numeric value.

    A "best" SI prefix from a specified prefix collection is defined by minimizing :
        * leading zeros (possibly to a specified tolerance limit, see `lztol`)
        * significant digits before the decimal point
    , after the prefix is applied.

    Args:
        value (float): the numerical value for picking the prefix.
        select (str, optional): SI prefix candidates, a substring of "yzafpnum kMGTPEZY").
            Defaults to 'mu'.
        lztol (int, optional): leading zeros tolerance.
            Defaults to 0 (avoid any leading zeros when possible).

    Returns:
        tuple: (prefix_string, prefix_scale)

    Examples:

    e.g. for frequency value in Hz
    >>> get_si_prefix(10**7,select='kMGT')
    ('M', 1000000.0)

    e.g. for flux value in Jy
    >>> get_si_prefix(1.0,select='um')
    ('', 1.0)
    >>> get_si_prefix(0.0,select='um')
    ('', 1.0)
    >>> get_si_prefix(-0.9,select='um')
    ('m', 0.001)
    >>> get_si_prefix(0.9,select='um',lztol=1)
    ('', 1.0)
    >>> get_si_prefix(1e-7,select='um')
    ('u', 1e-06)
    >>> get_si_prefix(1e3,select='um')
    ('', 1.0)

    """
    if value == 0:
        return '', 1.0
    else:
        sp_tab = "yzafpnum kMGTPEZY"
        sp_list, sp_pow = zip(*[(p, (idx-8)*3.0)
                                for idx, p in enumerate(sp_tab) if p in select+' '])
        idx = bisect.bisect(sp_pow, np.log10(abs(value))+lztol)
        idx = max(idx-1, 0)

        return sp_list[idx].strip(), 10.**sp_pow[idx]


def absolute_path(name: str) -> str:
    """Return an absolute path of a given file."""
    return os.path.abspath(os.path.expanduser(os.path.expandvars(name)))


def relative_path(name: str, start: str | None = None) -> str:
    """
    Retun a relative path of a given file with respect a given origin.

    Args:
        name: A path to file.
        start: An origin of relative path. If the start is not given, the
            current directory is used as the origin of relative path.

    Examples:
    >>> relative_path('/root/a/b.txt', '/root/c')
    '../a/b.txt'
    >>> relative_path('../a/b.txt', './c')
    '../../a/b.txt'
    """
    if start is not None:
        start = absolute_path(start)
    return os.path.relpath(absolute_path(name), start)


def get_task_result_count(context: Context, taskname: str = 'hif_makeimages') -> int:
    """Count occurrences of a task result in the context.results list.

    Loop over the content of the context.results list and compare taskname to the pipeline_casa_task
    attribute of each result object. Increase counter if taskname substring is found in the attribute.

    The order number is determined by counting the number of previous execution of
    the task, based on the content of the context.results list. The introduction
    of this method is necessary because VLASS-SE-CONT imaging happens in multiple
    stages (hif_makeimages calls). Imaging parameters change from stage to stage,
    therefore it is necessary to know what is the current stage ordinal number.
    """
    count = 0
    for r in context.results:
        # Work around the fact that r has read() method in some cases (e.g. editimlist)
        # but not in others (e.g. in tclean renderer)
        try:
            if taskname in r.read().pipeline_casa_task:
                count += 1
        except AttributeError:
            if taskname in r.pipeline_casa_task:
                count += 1
    return count


def place_repr_source_first(itemlist: list[str] | list[tuple], repr_source: str) -> list[str] | list[tuple]:
    """
    Place representative source first in a list of source names
    or tuples with source name as first tuple element.
    """
    try:
        itemtype = type(itemlist[0])
        if itemtype is str:
            repr_source_index = [dequote(item) for item in itemlist].index(dequote(repr_source))
        elif itemtype is tuple or itemtype is list:
            repr_source_index = [dequote(item[0]) for item in itemlist].index(dequote(repr_source))
        else:
            raise Exception('Cannot handle items of type {}'.format(itemtype))
        repr_source_entry = itemlist.pop(repr_source_index)
        itemlist = [repr_source_entry] + itemlist
    except ValueError:
        LOG.warning('Could not reorder field list to place representative source first')

    return itemlist


def get_taskhistory_fromimage(imagename: str):
    """Retrieve past CASA/tclean() call parameters from the image history.

    Note: the tclean history is only added to images/logtable in CASA ver>=6.2 (see CAS-13247)
    For tclean products generated by earlier CASA versions, an empty list will be returned.
    """
    taskhistory_list = []

    with casa_tools.ImageReader(imagename) as image:
        history_list = image.history(list=False)
        is_fromtask = False
        for line in history_list:
            if 'taskname' in line and '=' in line:
                is_fromtask = True
                k, v = line.partition('=')[::2]
                k = k.strip()
                v = v.strip()
                taskhistory_list.append(collections.OrderedDict([('taskname', v), ('taskversion', 'unkown')]))
                continue
            if 'version:' in line and 'CASAtools:' in line and is_fromtask:
                taskhistory_list[-1]['taskversion'] = line
                continue
            if '=' in line and is_fromtask:
                k, v = line.partition('=')[::2]
                k = k.strip()
                v = v.strip()
                taskhistory_list[-1][k] = ast.literal_eval(v)
            else:
                is_fromtask = False

    LOG.info(f'Found {len(taskhistory_list)} task history entry/entries from {imagename}')

    return taskhistory_list


def get_obj_size(obj: Any, serialize: bool = True) -> int:
    """Estimate the size of a Python object.

    If serialize is True, returns the size of the serialized object. Note that this is NOT
    the same as the object size in memory.

    When serialize is False, returns the memory consumption of the object via the asizeof
    method of Pympler (https://pypi.org/project/Pympler).
    An alternative is the get_deep_size() function from objsize (https://pypi.org/project/objsize).

    The serialization-based approach was a fallback solution for the issues described in PIPE-1698/PIPE-2877.
    The `asize.py` bug described in PIPE-2877 remain unresolved as of Pympler ver 1.1.

    See the GH issues for details and PIPE-1698 and PIPE-2877 for background:
        https://github.com/pympler/pympler/issues/155
        https://github.com/pympler/pympler/issues/151

    Args:
        obj: The Python object to measure.
        serialize: If True, measure serialized size; if False, measure memory size using Pympler.

    Returns:
        The size of the object in bytes.

    Raises:
        Exception: If serialize is False and Pympler is not installed.
    """
    if serialize:
        return len(pickle.dumps(obj, protocol=-1))
    try:
        from pympler.asizeof import asizeof
        return asizeof(obj)
    except ImportError as err:
        LOG.debug('Pympler import failed: %s', err)
        raise ModuleNotFoundError(
            'Pympler is required for in-memory size calculation. Please install it with: pip install pympler'
        ) from err


def glob_ordered(pattern: str, *args, order: str | None = None, **kwargs) -> list[str]:
    """Return a sorted list of paths matching a pathname pattern."""
    path_list = glob.glob(pattern, *args, **kwargs)

    if order == 'mtime':
        path_list.sort(key=os.path.getmtime)
    elif order == 'ctime':
        path_list.sort(key=os.path.getctime)
    else:
        if order is not None:
            LOG.warning("Unknown sorting order requested: order=%r. Only 'mtime', 'ctime', or None is allowed.", order)
            LOG.warning("We will use the default alphabetically/numerically ascending order (order=None) instead.")
        path_list = sorted(path_list)

    return path_list


def deduplicate(items: list) -> list:
    """Remove duplicate entries from a list, but preserve the order.

    Note that the use of list(set(x)) can cause random order in the output.
    The return of this function is guaranteed to be in the order that unique items show up in the input, unlike
    a deduplicate-resorting solution like sorted(set(x).
    Ref: https://stackoverflow.com/questions/480214/how-do-i-remove-duplicates-from-a-list-while-preserving-order
    This solution only works for Python 3.7+.
    """
    deduplicated_items = list(dict.fromkeys(items))

    return deduplicated_items


@contextlib.contextmanager
def ignore_pointing(vis: str | list[str] | set[str]):
    """A context manager to ignore pointing tables of MSes during I/O operations.

    The original pointing table will be temperarily renamed to POINTING_ORIGIN, and a new empty pointing table
    is created. When the context manager exits, the original table is restored.

    For example, to ignore the pointing table of a MS during mstransform() calls, use:

        with ignore_pointing('test.ms'):
            casatasks.mstransform(vis='test.ms',outputvis='test_output.ms',scan='16',datacolumn='data')

    The pointing table of the output MS should be empty.

    On the other hand, if the pointing table is needed in the output vis, e.g. for imaging with tclean(usepointing=True),
    we can manually create hardlinks of pointing table afterwards while minimizing the disk space usage:

        import shutil, os
        shutil.rmtree('test_small.ms/POINTING')
        shutil.copytree('test.ms/POINTING', 'test_output.ms/POINTING', copy_function=os.link)

    One can verify the inodes of the pointing table files, which should be the same:

        ls -lih test.ms/POINTING
        ls -lih test_small.ms/POINTING

    """
    if isinstance(vis, (list, set)):
        vis_list = vis
    else:
        vis_list = [vis]

    vis_list_ignore = []
    try:
        for ms in vis_list:
            if not os.path.isdir(ms+'/POINTING') and not os.path.isdir(ms+'/POINTING_ORIGIN'):
                LOG.warning(f'No pointing table found in {ms}.')
                continue
            vis_list_ignore.append(ms)
            if not os.path.isdir(ms+'/POINTING_ORIGIN'):
                LOG.info(f'backup the pointing table for {ms}')
                shutil.move(ms+'/POINTING', ms+'/POINTING_ORIGIN')
            with casa_tools.TableReader(ms+'/POINTING_ORIGIN', nomodify=True) as table:
                tabdesc = table.getdesc()
                dminfo = table.getdminfo()
            if os.path.isdir(ms+'/POINTING'):
                shutil.rmtree(ms+'/POINTING')
            LOG.info(f'empty the pointing table for {ms}')
            tb = casa_tools.table
            tb.create(ms+'/POINTING', tabdesc, dminfo=dminfo)
            tb.close()
        yield
    finally:
        for ms in vis_list_ignore:
            if os.path.isdir(ms+'/POINTING_ORIGIN'):
                if os.path.isdir(ms+'/POINTING'):
                    shutil.rmtree(ms+'/POINTING')
                LOG.info(f'restore the pointing table for {ms}')
                shutil.move(ms+'/POINTING_ORIGIN', ms+'/POINTING')


@contextlib.contextmanager
def open_with_lock(filename: str, mode: str = 'r', *args: Any, **kwargs: Any) -> Iterator[TextIO]:
    """Open a file with an exclusive lock.

    This context manager attempts to acquire an exclusive lock on the file upon opening.
    Other processes using `open_with_lock` will wait until the lock is automatically released
    when exiting the context.
    
    Args:
        filename: Path to the file to open and lock.
        mode: File open mode (e.g., 'rt', 'wt', 'a', 'rb').
        *args: Additional positional arguments to the built-in `open()` function.
        **kwargs: Additional keyword arguments to the built-in `open()` function.

    Yields:
        The opened file object with an exclusive lock acquired (if supported by the filesystem).

    Notes:
        All file open calls with `open_with_lock` will block other `open_with_lock` usages
        (even from different processes/Lustre clients) from read/write until the lock is
        released. However, this locking/blocking mechanism does not prevent file access
        (which could potentially cause IO errors) from other file openers (e.g., the
        built-in `open()` function).

        **Filesystem Support:**
        The Python `fcntl` API's behavior depends on the underlying OS/storage
        implementation: https://docs.python.org/3/library/fcntl.html. Not all
        OS/file systems fully support file locking.        
        - **Lustre**: Requires mount option `-o flock`. Check with: `mount -l | grep lustre`
            e.g. : `192.168.1.30@o2ib:/aoclst03 on /.lustre/aoc type lustre (rw,flock,user_xattr,lazystatfs)`
        - **NFS**: Support varies by configuration (see PIPE-2051 for details)
        - **Local filesystems**: Generally well-supported on Unix-like systems        

        **Testing Lock Behavior:**
        To verify exclusive locking works on your system, run this from multiple processes:

        ```python
        import fcntl
        with open(filename, 'w') as fd:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # Should block/fail on second process
        ```
    """
    needs_truncate = 'w' in mode
    is_binary = 'b' in mode
    base_mode = 'r+b' if is_binary else 'r+'

    try:
        fd = open(filename, base_mode, *args, **kwargs)
    except FileNotFoundError:
        base_mode = 'w+b' if is_binary else 'w+'
        fd = open(filename, base_mode, *args, **kwargs)

    LOG.debug('Attempting to acquire lock on %s', filename)
    lock_acquired = False
    try:
        try:
            # Acquire an exclusive lock on the file
            fcntl.flock(fd, fcntl.LOCK_EX)
            lock_acquired = True
            LOG.debug('Successfully acquired lock on %s', filename)
        except OSError as ex:
            LOG.warning('Failed to acquire file lock for %s due to filesystem limitation, '
                        'which might cause racing conditions if multiple processes access '
                        'the file simultaneously: %s', filename, ex)

        if lock_acquired and needs_truncate:
            fd.truncate(0)
            fd.seek(0)
            LOG.debug('Truncated file after acquiring lock: %s', filename)

        yield fd

    finally:
        if lock_acquired:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
                LOG.debug('Successfully released lock on %s', filename)
            except OSError as ex:
                LOG.warning('Failed to release file lock for %s due to filesystem limitation, '
                            'which might cause racing conditions if multiple processes access '
                            'the file simultaneously: %s', filename, ex)
        fd.close()



def ensure_products_dir_exists(products_dir: str) -> None:
    try:
        LOG.trace(f"Creating products directory: {products_dir}")
        os.makedirs(products_dir)
    except OSError as exc:
        if exc.errno != errno.EEXIST:
            raise


def export_weblog_as_tar(context: Context, products_dir: str, name_builder: PipelineProductNameBuilder) -> str:
    # Construct filename prefix from oussid and recipe name if available.
    prefix = context.get_oussid()
    recipe_name = context.get_recipe_name()
    if recipe_name:
        prefix = prefix + '.' + recipe_name

    # Construct filename for weblog output tar archive.
    tarfilename = name_builder.weblog(project_structure=context.project_structure,
                                      ousstatus_entity_id=prefix)

    # Save weblog directory to tar archive.
    LOG.info(f"Saving weblog in {tarfilename}")
    tar = tarfile.open(os.path.join(products_dir, tarfilename), "w:gz")
    tar.add(os.path.join(os.path.basename(os.path.dirname(context.report_dir)), 'html'))
    tar.close()
    return tarfilename


def get_products_dir(context: Context) -> str:
    if context.products_dir is None:
        return os.path.abspath('./')
    else:
        return context.products_dir


class pl_defaultdict(collections.defaultdict):
    def __repr__(self) -> str:
        return str(dict(self))

    def as_plain_dict(self) -> dict:
        return to_plain_dict(self)


def nested_dict() -> dict:
    return pl_defaultdict(nested_dict)


def to_plain_dict(default_dict: dict) -> dict:
    plain_dict = dict()
    for k, v in default_dict.items():
        if isinstance(v, collections.defaultdict):
            plain_dict[k] = to_plain_dict(v)
        else:
            plain_dict[k] = v

    return plain_dict


def string_to_val(s: str) -> Any:
    """
    Convert a string to a Python data type.
    """
    try:
        pyobj = ast.literal_eval(s)
        # PIPE-1030: prevent a string like "1,2,3" from being unexpectedly translated into tuple
        if type(pyobj) is tuple and s.strip()[0] != '(':
            pyobj = s
        return pyobj
    except ValueError:
        return s
    except SyntaxError:
        return s


def remove_trailing_string(s: str, t: str) -> str:
    """
    Remove a trailing string if it exists.
    """
    if s.endswith(t):
        return s[:-len(t)]
    else:
        return s


ConditionType = Callable | dict[str, dict[str, dict[str, Any]]]


def function_io_dumper(to_pickle: bool=True, to_json: bool=False, json_max_depth: int=5,
                       condition: ConditionType | None = None, timestamp: bool=True):
    """
    Dump arguments and return-objects of a function implement the decolator into pickle files and/or JSON(-like) file.
    
    This function is a helper method for development. It should not be used in production codes.
    
    Usage:
    @function_io_dumper()
    def foobar(self, bar):
        ...
        return ret
    
    When foobar() is executed, the decolator makes a directory 'foobar.[timestamp]', then it dumps
    all objects of arguments and return values of foobar() as pickle files and|or JSON files.
    We can get the same behavior of foobar() with the pickles as when they were dumped:
    
    with open('bar.pickle', 'rb') as f:
        bar = pickle.load(f)
    foobar(bar)
    
    or, understand input/result of the function by JSON-like output. To avoid recursive or tremendous output,
    it sets max depth of recursive (default to 5).

    Args:
        to_pickle (bool, optional): Dump pickle or not. Defaults to True.
        to_json (bool, optional): Dump JSON-like file or not. Defaults to False.
        json_max_depth (int, optional): Set depth of dumping JSON tree. Defaults to 5.
        condition (ConditionType): Set callable function user defined, or conditions of
            argument dumping. Defaults to None.
            ex1) Callable condition
                condition = my_condition
                And, a function my_condition() must be defined as:
                    def my_condition(kwargs) -> bool:
                        # Serialize only if the keyword argument 'spw' is 10 or True.
                        return kwargs.get("spw") in (10, True)
            ex2) Dict condition
                condition = {'self', {'spw':10}}
        timestamp (bool, optional): Add timestamp to the names of output directories. If not and the same function was
            executed multiple times, the output directory will be overwritten. Defaults to True.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            
            # create timestamp
            epoch_time = time.time()
            dt = datetime.fromtimestamp(epoch_time)
            ns = int((epoch_time - int(epoch_time)) * 1_000_000_000)
            _timestamp = dt.strftime(f'%Y%m%d-%H%M%S.{ns}')
            
            # make signatures of args
            sig = inspect.signature(func)
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()

            try:
                if callable(condition):
                    exec_dumpargs = condition(bound_args)
                else:
                    exec_dumpargs = _eval_condition(condition, bound_args)
            except Exception as e:
                    LOG.warning(f'Error evaluating condition callable: {e}')
                    exec_dumpargs = False

            extention = ''
            if timestamp:
                extention = f'.{_timestamp}'
                
            output_folder_name = f"{func.__name__}{extention}"

            json_dict = None
            if to_json:
                json_dict = object_to_dict(bound_args.arguments, max_depth=json_max_depth)
            
            try:
                os.makedirs(output_folder_name, exist_ok=True)

                LOG.info(f"Function '{_get_full_method_path(func)}' called at {_timestamp}")

                for arg_name, arg_value in bound_args.arguments.items():
                    _dump(arg_value, output_folder_name, arg_name, dump_pickle=to_pickle, dump_json=to_json, json_dict=json_dict)

            except pickle.PicklingError as e:
                exec_dumpargs = False
                LOG.warning(f'Contained unpickleable object: {e}')
            except Exception as e:
                exec_dumpargs = False
                LOG.warning(f'Exception occurred: {e}')

            result = func(*args, **kwargs)

            if exec_dumpargs and result is not None:
                try:
                    _name = f'{output_folder_name}.result'
                    if to_json:
                        json_dict = object_to_dict({_name:result}, max_depth=json_max_depth)
                    _dump({_name:result}, output_folder_name, _name, dump_pickle=to_pickle, dump_json=to_json, json_dict=json_dict)
                except pickle.PicklingError as e:
                    LOG.warning(f'Contained unpickleable object: {e}')
                except Exception as e:
                    LOG.warning(f'Exception occurred: {e}')

            return result
        return wrapper
    return decorator


def _dump(obj: object, path: str, name: str, dump_pickle: bool=True, dump_json: bool=False, json_dict={}) -> None:
    file_path = os.path.join(path, f'{name}')
    
    if dump_pickle:
        with open(file_path+'.pickle', 'wb') as f:
            pickle.dump(obj, f)
    if dump_json:
        with open(file_path+'.json', 'w') as f:
            f.write(json.dumps(json_dict[name], default=str))


def _get_full_method_path(func: Callable) -> str:
    module_name = func.__module__
    if hasattr(func, '__qualname__'):
        qualname = func.__qualname__
    else:
        qualname = func.__name__
    return f'{module_name}.{qualname}'


def _eval_condition(condition: dict | None, args: dict) -> bool:
    # {'self', {'spw':10}}, need unittest
    if condition is None:
        return True
    
    LOG.info(f'condition: {condition}')
    
    for key, val in condition:
        arg = args.get(key, False)
        if arg:
            for propname, propval in val:
                if isinstance(arg, dict) and arg.get(propname, False):
                    obj = arg.getattr(propname)
                    if obj == propval:
                        return True
    return False


def object_to_dict(obj: object, max_depth: int = 5, current_depth: int = 0) -> object | dict | None:

    if current_depth > max_depth:
        return None

    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if hasattr(value, '__dict__') or isinstance(value, Iterable):
                result[key] = object_to_dict(value, max_depth=max_depth, current_depth=current_depth + 1)
            else:
                result[key] = value
        return result

    elif isinstance(obj, Iterable) and not isinstance(obj, (str, bytes)):
        result = []
        for item in obj:
            if hasattr(item, '__dict__') or isinstance(item, Iterable):
                result.append(object_to_dict(item, max_depth=max_depth, current_depth=current_depth + 1))
            else:
                result.append(item)
        return result

    elif hasattr(obj, '__dict__'):
        result = {}
        for key, value in obj.__dict__.items():
            if hasattr(value, '__dict__') or isinstance(value, Iterable):
                result[key] = object_to_dict(value, max_depth=max_depth, current_depth=current_depth + 1)
            else:
                result[key] = value
        return result

    else:
        return obj


def decorate_io_dumper(cls: object, functions: list[str | None] = [], *args: Any, **kwargs: Any) -> None:
    """Apply function_io_dumper dynamically.

    Usage:
    ...
    import pipeline.infrastructure.utils.utils as ut
    
    ut.decorate_io_dumper(SDInspection, ['execute'])
    
    ...
    hsd_importdata()  # -> dump args of SDInspection.execute()

    Args:
        cls (object): the class has functions to be decorated.
        functions (list[str], optional): Function names to decodate. If not specified or
            set empty list, then all functions of the class are decorated. Defaults to [].
    """
    if len(functions) == 0:
        _functions = inspect.getmembers(cls, predicate=inspect.isfunction)
    else:
        _functions = []
        for _f in functions:
            _c = _str_to_func(cls, _f)
            if _c:
                _functions.append(_c)
    for _func in _functions:
        _name = _func.__name__
        decorated_func = function_io_dumper(*args, **kwargs)(_func)
        setattr(cls, _name, decorated_func)


def _str_to_func(cls: object, _name: str) -> Callable | bool:
    if hasattr(cls, _name):
        _c = getattr(cls, _name)
        if callable(_c):
            return _c
    return False


def list_to_str(value: list[Number | str] | npt.NDArray) -> str:
    """Convert list or numpy.ndarray into string.

    The list/ndarray should be 1-dimensional. In that case, the function
    returns comma-separated sequence of its elements. Otherwise it just
    returns default string representation of the value, str(value).

    Args:
        value: 1-dimensional list or numpy array

    Returns:
        String representation of the value. If input value is in
        compliance with the requirement, it will be comma-separated
        sequence of elements.
    """
    if isinstance(value, (list, np.ndarray)) \
       and all(isinstance(x, (Number, str)) for x in value):
        # use np.ndarray.tolist to ensure all the elements
        # have Python builtin types
        ret = str(np.asarray(value).tolist())
    else:
        ret = str(value)
    return ret


def validate_url(url: str) -> bool:
    """Validates whether a given URL is properly formatted.

    This function checks if the URL follows a valid format using a regular expression.
    It also ensures that the parsed URL contains both a scheme (e.g., "http" or "https")
    and a network location (netloc), which are required components for a valid URL.

    Args:
        url (str): The URL to validate.

    Returns:
        bool: True if the URL is valid, False otherwise.
    """
    url_regex = re.compile(
        r'^(https?:\/\/)?'  # HTTP or HTTPS
        r'([\w.-]+)'        # Domain name or IP address
        r'(:\d+)?'          # Optional port
        r'(\/[^\s]*)?$',    # Optional path
        re.IGNORECASE
    )

    if not url_regex.match(url):
        return False

    parsed = urlparse(url)

    return all([parsed.scheme, parsed.netloc])


def obs_long_lat(observatory: str) -> tuple[QuantityDict, QuantityDict]:
    """Return longitude and latitude values of the given observatory."""
    observatory = casa_tools.measures.observatory(observatory)
    return observatory['m0'], observatory['m1']


def obs_midtime(start_time: datetime, end_time: datetime) -> EpochDict:
    """Returns the mid time in a CASA measures dictionary."""
    mid_time = start_time + (end_time - start_time) / 2
    return casa_tools.measures.epoch('utc', mid_time.isoformat())


def compute_zenith_distance(
        field_direction: DirectionDict,
        epoch: EpochDict,
        observatory: str,
        coordinate_frame: str = 'AZELGEO',
        ) -> QuantityDict:
    """Calculate zenith distance for a field at a given time and observatory.

    This function uses CASA measures to calculate the zenith distance, similar to
    how compute_az_el_to_field works in htmlrenderer.py.

    Args:
        field_direction: CASA direction measure dictionary for the field.
        epoch: CASA epoch measure dictionary for the observation time.
        observatory: Name of the observatory (e.g., 'VLA', 'ALMA').
        coordinate_frame: Coordinate frame for the calculation (e.g., 'AZELGEO', 'AZEL').
            Defaults to 'AZELGEO'.

    Returns:
        A CASA quantity dictionary containing the zenith distance in radians.

    Examples:
        >>> direction = {'m0': {'value': 4.18879, 'unit': 'rad'},
        ...              'm1': {'value': 0.58534, 'unit': 'rad'},
        ...              'refer': 'J2000', 'type': 'direction'}
        >>> epoch = {'m0': {'value': 58089.82, 'unit': 'd'}, 'refer': 'UTC', 'type': 'epoch'}
        >>> zd = compute_zenith_distance(direction, epoch, 'VLA')
        >>> print(f"{casa_tools.quanta.convert(zd, 'deg')['value']:.2f} degrees")
    """
    me = casa_tools.measures

    # Set the reference frame with the epoch and observatory
    me.doframe(epoch)
    me.doframe(me.observatory(observatory))

    # Convert field direction to horizontal coordinates
    horizontal = me.measure(field_direction, coordinate_frame)
    elevation_rad = horizontal['m1']['value']
    zenith_distance_rad = np.pi / 2.0 - elevation_rad

    return casa_tools.quanta.quantity(zenith_distance_rad, 'rad')


def get_row_count(table_name: str, taql: str) -> int:
    """Return the number of rows in the specified table that match the given TaQL query.

    Parameters:
        table_name: Path to the CASA table.
        taql: The TaQL query string used to filter the table rows.

    Returns:
        The number of rows matching the query, or 0 if an error occurs.
    """

    nrows = 0
    try:
        with casa_tools.TableReader(table_name) as table:
            subtb = table.query(taql)
            nrows = subtb.nrows()
            subtb.close()
    except Exception as ex:
        nrows = 0
        LOG.warning(ex)

    return nrows


def get_valid_url(env_var: str, default: str | list[str]) -> str | list[str]:
    """
    Fetches one or more URLs from an environment variable. If a comma-delimited string is provided,
    it is split and each URL is validated. Falls back to the default if any URL is invalid or not set.

    Args:
        env_var: The name of the environment variable.
        default: A single default URL or a list of default URLs.

    Returns:
        A valid URL string or a list of valid URL strings.
    """
    envvar_value = os.getenv(env_var)
    if not envvar_value:
        LOG.info('Environment variable %s not defined. Switching to default %s.', env_var, default)
        return default

    urls = [u.strip() for u in envvar_value.split(',') if u.strip()]
    if not urls:
        LOG.warning('Environment variable %s is empty after parsing. Switching to default %s.', env_var, default)
        return default

    for url in urls:
        if not validate_url(url):
            LOG.warning('Environment variable %s URL was set to %s but is misconfigured.', env_var, url)
            LOG.info('Switching to default %s.', default)
            return default

    if len(urls) == 1:
        LOG.info('Environment variable %s set to URL %s.', env_var, urls[0])
        return urls[0]

    LOG.info('Environment variable %s set to list of URLs %s.', env_var, urls)
    return urls


def clear_time_cache():
    """Clear the time cache in the CASA measures tool.

    See details in PIPE-2891/PIPEREQ-402/CAS-13831.
    A workaround solution provided by T. Nakazato (NAOJ), 2025-10-16.
    """
    # Define constants for the dummy conversion.
    DUMMY_EPOCH_MJD = 37665.0 # MJD corresponds to beginning of IERS data coverage: 1962-01-01
    DUMMY_AZIMUTH_DEG = 0.0
    DUMMY_ELEVATION_DEG = 90.0
    OBSERVATORY = 'ALMA'

    with contextlib.closing(casa_tools.measures) as measures_tool:
        quanta_tool = casa_tools.quanta

        # Set a time frame well before any real observation.
        epoch = measures_tool.epoch(rf='UTC', v0=quanta_tool.quantity(DUMMY_EPOCH_MJD, 'd'))
        measures_tool.doframe(epoch)

        # Set an observatory position frame.
        position = measures_tool.observatory(OBSERVATORY)
        measures_tool.doframe(position)

        # Perform the dummy direction conversion that triggers the cache clear.
        dummy_direction = measures_tool.direction(
            rf='AZELGEO',
            v0=quanta_tool.quantity(DUMMY_AZIMUTH_DEG, 'deg'),
            v1=quanta_tool.quantity(DUMMY_ELEVATION_DEG, 'deg'),
        )

        measures_tool.measure(rf='ICRS', v=dummy_direction)

    LOG.debug('Successfully cleared the CASA measures tool time cache.')