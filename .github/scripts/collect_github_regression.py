#!/usr/bin/env python3
"""Collect regression tests marked with @pytest.mark.github_runner as a GitHub Actions matrix."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path


def _is_github_runner_mark(node: ast.expr) -> ast.Call | ast.Attribute | None:
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Attribute) and target.attr == 'github_runner':
        return node
    return None


def _extract_testdata(mark: ast.Call | ast.Attribute, node_id: str) -> list[str]:
    if isinstance(mark, ast.Call):
        for kw in mark.keywords:
            if kw.arg == 'testdata':
                val = ast.literal_eval(kw.value)
                paths = [str(item) for item in val] if isinstance(val, (list, tuple)) else [str(val)]
                if paths:
                    return paths
    raise ValueError(f'{node_id}: @pytest.mark.github_runner requires a non-empty testdata=[...] argument')


def collect_tests(root: Path) -> list[dict[str, str]]:
    """Scan tests/regression for @pytest.mark.github_runner(testdata=[...]) functions.

    Each testdata entry must be a directory path (e.g. a .ms or dataset directory)
    so git sparse-checkout cone mode can materialize it directly.
    """
    regression_dir = root / 'tests' / 'regression'
    entries: list[dict[str, str]] = []

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
                testdata = _extract_testdata(mark, node_id)
                entries.append({
                    'name': short_name,
                    'node_id': node_id,
                    'testdata_paths': '\n'.join(testdata),
                })
                break

    return entries


def main() -> None:
    """Print the collected GitHub Actions matrix JSON to stdout."""
    root = Path(__file__).resolve().parents[2]
    entries = collect_tests(root)
    print(json.dumps({'include': entries}))


if __name__ == '__main__':
    main()
