"""
The utils module contains general-purpose uncategorised utility functions and
classes.
"""
import collections
import copy
import itertools
import operator
import os
import re
import string
from typing import Collection, Dict, List, Tuple, Optional, Sequence, Union

import bisect
import numpy as np

from .conversion import range_to_list, dequote
from .. import casa_tools
from .. import logging

LOG = logging.get_logger(__name__)

__all__ = ['find_ranges', 'dict_merge', 'are_equal', 'approx_equal', 'get_num_caltable_polarizations',
           'flagged_intervals', 'get_field_identifiers', 'get_receiver_type_for_spws', 'get_spectralspec_to_spwid_map',
           'get_casa_quantity', 'get_si_prefix', 'absolute_path', 'relative_path', 'get_task_result_count',
           'place_repr_source_first', 'get_casa_session_details']


def find_ranges(data: Union[str, List[int]]) -> str:
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
        if len(data) is 0:
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


def dict_merge(a: Dict, b: Union[Dict, any]) -> Dict:
    """Recursively merge dictionaries.

    This utility function recursively merges dictionaries. If second argument
    (b) is a dictionary, then a copy of first argument (dictionary a) is created
    and the elements of b are merged into the new dictionary. Otherwise return
    argument b.

    This utility function check the equivalence of array like objects. Two arrays
    are equal if they have the same number of elements and elements of the same
    index are equal.

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


def are_equal(a: Union[List, np.ndarray], b: Union[List, np.ndarray]) -> bool:
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


def get_num_caltable_polarizations(caltable: str) -> int:
    """Obtain number of polarisations from calibration table.

    Seemingly the number of QA ID does not map directly to the number of
    polarisations for the spw in the MS, but the number of polarisations for
    the spw as held in the caltable.
    """
    with casa_tools.TableReader(caltable) as tb:
        col_shapes = set(tb.getcolshapestring('CPARAM'))

    # get the number of pols stored in the caltable, checking that this
    # is consistent across all rows
    fmt = re.compile(r'\[(?P<num_pols>\d+), (?P<num_rows>\d+)\]')
    col_pols = set()
    for shape in col_shapes:
        m = fmt.match(shape)
        if m:
            col_pols.add(int(m.group('num_pols')))
        else:
            raise ValueError('Could not find shape of polarisation from %s' % shape)

    if len(col_pols) is not 1:
        raise ValueError('Got %s polarisations from %s' % (len(col_pols), col_shapes))

    return int(col_pols.pop())


def flagged_intervals(vec: Union[List, np.ndarray]) -> List:
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


def get_field_accessor(ms, field):
    """Returns accessor to field name or field ID, if field name is ambiguous.
    """
    fields = ms.get_fields(name=field.name)
    if len(fields) == 1:
        return operator.attrgetter('name')

    def accessor(x):
        return str(operator.attrgetter('id')(x))
    return accessor


def get_field_identifiers(ms) -> Dict:
    """Maps numeric field IDs to field names.

    Get a dict of numeric field ID to unambiguous field identifier, using the
    field name where possible and falling back to numeric field ID where the
    name is duplicated, for instance in mosaic pointings.
    """
    field_name_accessors = {field.id: get_field_accessor(ms, field) for field in ms.fields}
    return {field.id: field_name_accessors[field.id](field) for field in ms.fields}


def get_receiver_type_for_spws(ms, spwids: Sequence) -> Dict:
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


def get_spectralspec_to_spwid_map(spws: Collection) -> Dict:
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


def get_casa_quantity(value: Union[None, Dict, str, float, int]) -> Dict:
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


def get_si_prefix(value: float, select: str = 'mu', lztol: int = 0) -> tuple:
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


def relative_path(name: str, start: Optional[str]=None) -> str:
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


def get_task_result_count(context, taskname: str = 'hif_makeimages') -> int:
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


def place_repr_source_first(itemlist: Union[List[str], List[Tuple]], repr_source: str) -> Union[List[str], List[Tuple]]:
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


def get_casa_session_details():
    """Get the current CASA session details.

    return a dictionary including the following keys:
        casa_dir: the root directory of the monolithic CASA distribution.
        omp_num_threads: the number of OpenMP threads in the current parallel region.
        data_path: CASA data paths in-use.
        numa_mem: memory properties from the NUMA software perspective.
        numa_cpu: cpu properties from the NUMA software perspective.
            The above CPU/mem properties might be different from the hardware specs obtained from 
            standard Python functions (e.g. os.cpu_count()) or pipeline.environment.
            On the difference between the "software" and hardware nodes, see 
                https://www.kernel.org/doc/html/latest/vm/numa.html
    """
    casa_session_details = casa_tools.utils.hostinfo()
    casa_session_details['casa_dir'] = casa_tools.utils.getrc()
    casa_session_details['omp_num_threads'] = casa_tools.casalog.ompGetNumThreads()
    casa_session_details['data_path'] = casa_tools.utils.defaultpath()
    casa_session_details['numa_cpu'] = casa_session_details.pop('cpus')
    casa_session_details['numa_mem'] = casa_session_details.pop('memory')

    return casa_session_details
