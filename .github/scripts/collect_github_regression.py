#!/usr/bin/env python3
"""Collect regression tests marked with @pytest.mark.github_runner as a GitHub Actions matrix."""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path


def _is_github_runner_mark(node: ast.expr) -> ast.Call | ast.Attribute | None:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Attribute) and target.attr == 'github_runner':
        return node
    return None


def _extract_marker_args(mark: ast.Call | ast.Attribute, node_id: str) -> tuple[list[str], list[str]]:
    testdata: list[str] = []
    os_list = ['ubuntu-24.04']
    if isinstance(mark, ast.Call):
        for kw in mark.keywords:
            if kw.arg == 'testdata':
                val = ast.literal_eval(kw.value)
                testdata = [str(item) for item in val] if isinstance(val, (list, tuple)) else [str(val)]
            elif kw.arg == 'macos' and ast.literal_eval(kw.value):
                os_list.append('macos-15')
    if not testdata:
        raise ValueError(f'{node_id}: @pytest.mark.github_runner requires a non-empty testdata=[...] argument')
    return testdata, os_list


def collect_tests(
    root: Path,
    *,
    name_filter: str = '',
    os_filter: str = 'all',
) -> list[dict[str, str]]:
    """Scan tests/regression for @pytest.mark.github_runner(testdata=[...]) functions.

    Each testdata entry must be a directory path (e.g. a .ms or dataset directory)
    so git sparse-checkout cone mode can materialize it directly.
    """
    regression_dir = root / 'tests' / 'regression'
    entries: list[dict[str, str]] = []
    needle = name_filter.strip().lower()

    for py_file in sorted(regression_dir.rglob('*_test.py')):
        tree = ast.parse(py_file.read_text(encoding='utf-8'), filename=str(py_file))
        rel_path = py_file.relative_to(root).as_posix()

        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith('test_'):
                continue
            for dec in node.decorator_list:
                mark = _is_github_runner_mark(dec)
                if mark is None:
                    continue
                node_id = f'{rel_path}::{node.name}'
                short_name = re.sub(r'^test_?|_?regression$', '', node.name).strip('_')
                if needle and needle not in short_name.lower() and needle not in node_id.lower():
                    break
                testdata, os_list = _extract_marker_args(mark, node_id)
                for os_name in os_list:
                    if os_filter != 'all' and os_name != os_filter:
                        continue
                    entries.append({
                        'name': short_name,
                        'os': os_name,
                        'node_id': node_id,
                        'testdata_paths': '\n'.join(testdata),
                    })
                break

    return entries


def main() -> None:
    """Print the collected GitHub Actions matrix JSON to stdout."""
    parser = argparse.ArgumentParser(description='Collect @pytest.mark.github_runner tests.')
    parser.add_argument('--filter', default='', help='Optional case-insensitive substring filter on test name')
    parser.add_argument('--os', default='all', help='Target OS filter (all, ubuntu-24.04, macos-15)')
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    entries = collect_tests(root, name_filter=args.filter, os_filter=args.os)
    print(json.dumps({'include': entries}))


if __name__ == '__main__':
    main()
