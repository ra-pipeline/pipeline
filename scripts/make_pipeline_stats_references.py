#!/usr/bin/env python3
"""Turn the NEW pipeline stats files from a regression test run into reference files.

For every regression test, this finds <run-dir>/<output_dir>/working/*.NEW.pipeline_stats.json, names it
pipeline_stats_<output_dir>.casa-<version>-pipeline-<version>.json using the versions recorded in the file,
and copies it into the test's reference directory under <testdata>.

Dry run by default; pass --copy to copy.

Usage:
    python3 scripts/make_pipeline_stats_references.py --run-dir <dir with test output folders> \
        --testdata <datapath dir containing pl-regressiontest> [--copy] [--force] [-k <substring>]
"""

import argparse
import ast
import glob
import json
import os
import re
import shutil
import sys
from collections import namedtuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TESTS_DIR = os.path.join(REPO_ROOT, 'tests', 'regression')

TestInfo = namedtuple('TestInfo', 'name path output_dir reference_dir reference_file use_json')


def _evaluate(node, names):
    """Evaluate the simple string expressions used in test definitions; return None if not possible."""
    if isinstance(node, ast.Constant):
        return node.value
    if sys.version_info < (3, 8) and isinstance(node, ast.Str):
        return node.s
    if isinstance(node, ast.Name):
        return names.get(node.id)
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            part = _evaluate(value.value if isinstance(value, ast.FormattedValue) else value, names)
            if part is None:
                return None
            parts.append(str(part))
        return ''.join(parts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _evaluate(node.left, names), _evaluate(node.right, names)
        if isinstance(left, str) and isinstance(right, str):
            return left + right
    if isinstance(node, ast.List):
        return [_evaluate(element, names) for element in node.elts]
    return None


def default_output_dir(test_name):
    """Same rule as the autouse fixture in tests/conftest.py."""
    return re.sub(r'^test_?|_?regression$', '', test_name).strip('_')


def find_tests(tests_dir):
    """Yield a TestInfo for every test function that creates a PipelineTester."""
    for path in sorted(glob.glob(os.path.join(tests_dir, '**', '*_test.py'), recursive=True)):
        with open(path, encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=path)
        for func in tree.body:
            if not (isinstance(func, ast.FunctionDef) and func.name.startswith('test_')):
                continue
            names = {}
            for statement in ast.walk(func):
                if isinstance(statement, ast.Assign) and len(statement.targets) == 1 \
                        and isinstance(statement.targets[0], ast.Name):
                    value = _evaluate(statement.value, names)
                    if value is not None:
                        names[statement.targets[0].id] = value
                if isinstance(statement, ast.Call) and getattr(statement.func, 'id', None) == 'PipelineTester':
                    kwargs = {kw.arg: _evaluate(kw.value, names) for kw in statement.keywords}
                    reference_file = kwargs.get('expectedoutput_file')
                    reference_dir = kwargs.get('expectedoutput_dir')
                    if reference_file and not reference_file.endswith('.json'):
                        reference_dir, reference_file = os.path.dirname(reference_file), None
                    yield TestInfo(
                        name=func.name,
                        path=path,
                        output_dir=kwargs.get('output_dir') or default_output_dir(func.name),
                        reference_dir=reference_dir,
                        reference_file=reference_file,
                        use_json=kwargs.get('use_json', True) is not False,
                    )
                    break


def stat_value(document, name):
    for record in document.get('stats', []):
        if record.get('name') == name:
            return record.get('value')
    return None


def reference_name(output_dir, document):
    """Build the reference file name from the versions recorded in a flat stats document."""
    casa = re.match(r'[\d.]+(?:-\d+)?', str(stat_value(document, 'casa_version') or ''))
    pipeline = re.match(r'[\d.]+', str(stat_value(document, 'pipeline_version') or ''))
    if not casa or not pipeline:
        return None
    return (f'pipeline_stats_{os.path.basename(os.path.normpath(output_dir))}.'
            f'casa-{casa.group(0).strip(".")}-pipeline-{pipeline.group(0).strip(".")}.json')


def process(test, run_dir, testdata, copy, force):
    """Return (status, detail) for one test, copying its reference file if requested."""
    if not test.use_json:
        return 'skip', 'use_json=False'
    if not (test.reference_dir or test.reference_file):
        return 'skip', 'no expectedoutput_dir/expectedoutput_file'
    run_folder = os.path.join(run_dir, test.output_dir)
    if not os.path.isdir(run_folder):
        return 'missing', f'no run folder {run_folder}'
    new_files = glob.glob(os.path.join(run_folder, 'working', '*.NEW.pipeline_stats.json'))
    if len(new_files) != 1:
        return 'missing', f'expected 1 NEW stats file in {run_folder}/working, found {len(new_files)}'
    new_file = new_files[0]
    try:
        with open(new_file, encoding='utf-8') as f:
            document = json.load(f)
    except ValueError as e:
        return 'error', f'cannot read {new_file}: {e}'

    if test.reference_file:
        target = os.path.join(testdata, test.reference_file)
    else:
        name = reference_name(test.output_dir, document)
        if name is None:
            return 'error', f'no casa_version/pipeline_version stats in {new_file}'
        target = os.path.join(testdata, test.reference_dir, name)
    if not os.path.isdir(os.path.dirname(target)):
        return 'error', f'reference directory does not exist: {os.path.dirname(target)}'

    errors = len(document.get('errors', []))
    note = f' (WARNING: {errors} extraction error(s) in file)' if errors else ''
    if os.path.exists(target) and not force:
        return 'exists', f'{target} (use --force to overwrite){note}'
    if copy:
        shutil.copyfile(new_file, target)
        return 'copied', f'{new_file}\n      -> {target}{note}'
    return 'would copy', f'{new_file}\n      -> {target}{note}'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--run-dir', required=True, help='directory containing the test output folders')
    parser.add_argument('--testdata', required=True, help='datapath directory that contains pl-regressiontest/')
    parser.add_argument('--tests-dir', default=DEFAULT_TESTS_DIR, help=f'default: {DEFAULT_TESTS_DIR}')
    parser.add_argument('-k', dest='select', help='only tests whose name contains this substring')
    parser.add_argument('--copy', action='store_true', help='copy the files (default is a dry run)')
    parser.add_argument('--force', action='store_true', help='overwrite existing reference files')
    args = parser.parse_args()

    counts = {}
    for test in find_tests(args.tests_dir):
        if args.select and args.select not in test.name:
            continue
        status, detail = process(test, args.run_dir, args.testdata, args.copy, args.force)
        counts[status] = counts.get(status, 0) + 1
        print(f'[{status}] {test.name}\n      {detail}')

    print('\n' + ', '.join(f'{n} {s}' for s, n in sorted(counts.items())))
    if not args.copy:
        print('Dry run: nothing was copied. Re-run with --copy.')
    return 1 if counts.get('error') else 0


if __name__ == '__main__':
    sys.exit(main())
