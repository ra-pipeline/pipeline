"""procedure_add_parallel.py - Add parallel=True to procedure XML tasks that support it.

Background
----------
When re-processing data (e.g. for regression testing), pipeline runs can be
significantly faster by enabling parallel execution in tasks that support it.
Procedure XML files and PPRs delivered by the observatory typically do not set
``parallel=True``, so this script provides a quick way to produce a
parallel-enabled copy without manually editing every task entry.

For each pipeline task in the procedure, probes whether it accepts a
"parallel" CLI parameter.  If so, and the parameter is not already set,
``parallel=True`` is injected into the task's ParameterSet.  The result
is written to a new XML file without modifying the original.

Usage:

    python3 scripts/procedure_add_parallel.py <input_xml> <output_xml>

Examples:

    python3 scripts/procedure_add_parallel.py pipeline/recipes/procedure_hifa_cal.xml procedure_hifa_cal_parallel.xml

    # Convert a PPR file:
    python3 scripts/procedure_add_parallel.py PPR_uid___A001_X362b_X53a.xml PPR_uid___A001_X362b_X53a_parallel.xml
"""

import argparse
import ast
import logging
import os
import sys
import xml.dom.minidom as minidom


# logger
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
LOG = logging.getLogger(os.path.basename(__file__))

# type alias
DOM = minidom.Document | minidom.Element


def _get_indent_from_prev_sibling(node: DOM) -> str:
    r"""Return the leading whitespace of *node* by inspecting its preceding text node.

    For example, if the text node before *node* is ``'\\n        '``, this
    function returns ``'        '`` (8 spaces).

    Args:
        node: A DOM element whose preceding sibling is inspected.

    Returns:
        Whitespace string (portion after the last newline in the preceding text
        node), or an empty string if no such node exists.
    """
    prev = node.previousSibling
    if prev and prev.nodeType == minidom.Node.TEXT_NODE:
        return prev.data.split('\n')[-1]
    return ''


def _get_param_indent(param_set: DOM) -> tuple[str, str]:
    """Derive indentation strings for new ``<Parameter>`` children.

    When the ``ParameterSet`` already contains ``Parameter`` elements the
    indentation is copied from them.  Otherwise it is computed from the
    ``ParameterSet`` element's own position in the document.

    Args:
        param_set: The ``ParameterSet`` DOM element.

    Returns:
        Tuple ``(param_indent, child_indent)`` where *param_indent* is the
        whitespace prefix for ``<Parameter>`` and *child_indent* is the prefix
        for ``<Keyword>``/``<Value>``.
    """
    existing_params = [
        c for c in param_set.childNodes if c.nodeType == minidom.Node.ELEMENT_NODE and c.tagName == 'Parameter'
    ]
    if existing_params:
        param_el = existing_params[0]
        param_indent = _get_indent_from_prev_sibling(param_el)
        kw_children = [c for c in param_el.childNodes if c.nodeType == minidom.Node.ELEMENT_NODE]
        if kw_children:
            child_indent = _get_indent_from_prev_sibling(kw_children[0])
            if child_indent:
                return param_indent or '            ', child_indent
        return param_indent or '            ', (param_indent or '            ') + '    '

    # No existing params: compute from the ParameterSet's own indentation.
    param_set_indent = _get_indent_from_prev_sibling(param_set)
    if param_set_indent:
        return param_set_indent + '    ', param_set_indent + '        '
    # Ultimate fallback (matches standalone procedure XML defaults).
    return '            ', '                '


def _get_pipeline_root() -> str:
    """Return the absolute path to the pipeline package root directory.

    Resolves ``<repo_root>/pipeline/`` regardless of the current working
    directory.  The scripts directory sits at ``<repo_root>/scripts/``, so
    the pipeline package is one level up and then into ``pipeline/``.
    """
    scripts_dir = os.path.dirname(os.path.abspath(__file__))  # <repo_root>/scripts/
    repo_root = os.path.dirname(scripts_dir)  # <repo_root>/
    return os.path.join(repo_root, 'pipeline')  # <repo_root>/pipeline/


def _find_cli_source(task_name: str) -> str | None:
    """Locate the CLI source file for *task_name* without importing it.

    Searches each ``{category}/cli/{task_name}.py`` file under the pipeline
    package root.

    Args:
        task_name: Pipeline task name (e.g. ``hifa_bandpass``).

    Returns:
        Absolute path to the CLI ``.py`` file, or ``None`` if not found.
    """
    pipeline_root = _get_pipeline_root()
    for entry in os.scandir(pipeline_root):
        if not entry.is_dir():
            continue
        candidate = os.path.join(entry.path, 'cli', f'{task_name}.py')
        if os.path.isfile(candidate):
            LOG.debug(f'Found CLI source for {task_name!r}: {candidate}')
            return candidate
    LOG.debug(f'No CLI source file found for {task_name!r}')
    return None


def task_supports_parallel(task_name: str) -> bool:
    """Return True if the CLI function for *task_name* accepts a ``parallel`` parameter.

    The check is performed by parsing the CLI source file with the ``ast``
    module — no pipeline imports are required.

    Args:
        task_name: Pipeline task name (e.g. ``hifa_bandpass``).

    Returns:
        ``True`` when the task's CLI function signature contains ``parallel``,
        ``False`` otherwise (including when the task source file is not found).
    """
    source_path = _find_cli_source(task_name)
    if source_path is None:
        return False
    try:
        with open(source_path, encoding='utf-8') as fh:
            tree = ast.parse(fh.read(), filename=source_path)
    except (OSError, SyntaxError) as exc:
        LOG.debug(f'Could not parse {source_path!r}: {exc}')
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == task_name:
            arg_names = [a.arg for a in node.args.args]
            return 'parallel' in arg_names

    return False


def _create_parameter_node(
    doc: minidom.Document,
    keyword: str,
    value: str,
    param_indent: str,
    child_indent: str,
    add_xmlns: bool = True,
) -> minidom.Element:
    """Build a DOM subtree for a single ``<Parameter>`` element.

    Args:
        doc: The owner document used to create new nodes.
        keyword: Parameter name (e.g. ``parallel``).
        value: Parameter value as a string (e.g. ``True``).
        param_indent: Whitespace prefix used for ``<Parameter>`` itself
            (also becomes the closing indent inside the element).
        child_indent: Whitespace prefix used for ``<Keyword>`` and ``<Value>``.
        add_xmlns: When ``True``, add ``xmlns=""`` to ``Keyword`` and ``Value``
            elements (matches the style of standalone procedure XML files).
            Set to ``False`` for PPR files which omit this attribute.

    Returns:
        A ``Parameter`` DOM element populated with Keyword and Value children.
    """
    param = doc.createElement('Parameter')

    if add_xmlns:
        kw_el = doc.createElementNS('', 'Keyword')
        kw_el.setAttribute('xmlns', '')
        val_el = doc.createElementNS('', 'Value')
        val_el.setAttribute('xmlns', '')
    else:
        kw_el = doc.createElement('Keyword')
        val_el = doc.createElement('Value')

    kw_el.appendChild(doc.createTextNode(keyword))
    val_el.appendChild(doc.createTextNode(value))

    param.appendChild(doc.createTextNode('\n' + child_indent))
    param.appendChild(kw_el)
    param.appendChild(doc.createTextNode('\n' + child_indent))
    param.appendChild(val_el)
    param.appendChild(doc.createTextNode('\n' + param_indent))

    return param


def _parameter_already_set(param_set: DOM, keyword: str) -> bool:
    """Return True if *keyword* is already present in *param_set*.

    Args:
        param_set: The ``ParameterSet`` DOM element to inspect.
        keyword: The parameter name to look for.

    Returns:
        ``True`` when the keyword is found among existing parameters.
    """
    for kw_el in param_set.getElementsByTagName('Keyword'):
        if kw_el.firstChild and kw_el.firstChild.data.strip() == keyword:
            return True
    return False


def _inject_parallel(doc: minidom.Document, param_set: DOM, add_xmlns: bool = True) -> None:
    """Add ``parallel=True`` to *param_set* if not already present.

    The new ``<Parameter>`` node is appended immediately before the closing
    ``</ParameterSet>`` tag, preserving surrounding whitespace.

    Args:
        doc: The owner document (used to create new nodes).
        param_set: The ``ParameterSet`` DOM element to modify.
        add_xmlns: Passed through to :func:`_create_parameter_node`; set
            ``False`` for PPR files.
    """
    if _parameter_already_set(param_set, 'parallel'):
        LOG.debug('parallel already set in ParameterSet – skipping.')
        return

    param_indent, child_indent = _get_param_indent(param_set)
    param_set_indent = _get_indent_from_prev_sibling(param_set)
    if not param_set_indent:
        param_set_indent = param_indent[:-4] if len(param_indent) >= 4 else ''

    # Remove the trailing whitespace text node that provides indentation for
    # the closing </ParameterSet> tag; we will re-add it after the new element.
    last_child = param_set.lastChild
    if last_child and last_child.nodeType == minidom.Node.TEXT_NODE and not last_child.data.strip():
        param_set.removeChild(last_child)

    # Append: indent + Parameter element + closing indent for </ParameterSet>.
    param_node = _create_parameter_node(doc, 'parallel', 'True', param_indent, child_indent, add_xmlns)
    param_set.appendChild(doc.createTextNode('\n' + param_indent))
    param_set.appendChild(param_node)
    param_set.appendChild(doc.createTextNode('\n' + param_set_indent))


def convert(input_path: str, output_path: str) -> None:
    """Parse *input_path*, inject ``parallel=True`` where supported, write *output_path*.

    For every ``ProcessingCommand`` in the procedure XML whose CLI task accepts
    a ``parallel`` parameter the converter adds ``parallel=True`` to the command's
    ``ParameterSet``.  All other tasks are left unchanged.

    Args:
        input_path: Path to the source procedure XML file.
        output_path: Path for the converted output XML file.

    Raises:
        FileNotFoundError: *input_path* does not exist.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f'Input procedure not found: {input_path!r}')

    LOG.info(f'Parsing {input_path}')
    doc = minidom.parse(input_path)

    # Detect file format and adapt output style accordingly.
    root_tag = doc.documentElement.tagName
    if root_tag == 'SciPipeRequest':
        LOG.info('Input format: PPR (SciPipeRequest)')
        add_xmlns = False
        xml_encoding = 'UTF-8'
    else:
        LOG.info(f'Input format: procedure XML ({root_tag})')
        add_xmlns = True
        xml_encoding = ''

    modified_count = 0
    skipped_count = 0

    for cmd_el in doc.getElementsByTagName('ProcessingCommand'):
        command_elements = cmd_el.getElementsByTagName('Command')
        if not command_elements:
            continue

        task_name = command_elements[0].firstChild.data.strip()

        if task_supports_parallel(task_name):
            param_set = cmd_el.getElementsByTagName('ParameterSet')
            if not param_set:
                LOG.warning(f'No ParameterSet found for {task_name!r} – skipping.')
                skipped_count += 1
                continue

            LOG.info(f'  {task_name}: adding parallel=True')
            _inject_parallel(doc, param_set[0], add_xmlns=add_xmlns)
            modified_count += 1
        else:
            LOG.info(f'  {task_name}: no parallel support – unchanged')

    LOG.info(f'Modified {modified_count} task(s), skipped {skipped_count} task(s).')

    with open(output_path, 'w', encoding='utf-8') as fh:
        doc.writexml(fh, encoding=xml_encoding)

    LOG.info(f'Written to {output_path}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description=(
            'Convert a pipeline procedure XML file by adding parallel=True '
            'to every pipeline task that supports the parallel CLI parameter.'
        )
    )
    parser.add_argument(
        'input',
        metavar='INPUT_XML',
        help='Source procedure XML file (e.g. procedure_hifa_cal.xml).',
    )
    parser.add_argument(
        'output',
        metavar='OUTPUT_XML',
        help='Destination XML file for the converted procedure.',
    )
    parser.add_argument(
        '-d',
        '--debug',
        action='store_true',
        help='Enable debug-level logging.',
    )
    args = parser.parse_args()

    if args.debug:
        LOG.setLevel(logging.DEBUG)

    convert(args.input, args.output)
