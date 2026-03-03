#!/usr/bin/env python3
"""
Survey all task result objects to identify those with potentially large attributes.

This tool scans the pipeline codebase to find:
1. All result object classes inheriting from FlaggableViewResults
2. All result objects with 'view' attributes (defaultdict pattern)
3. All result objects storing ImageResult or SpectrumResult objects
4. Potential bloat patterns (array copies, large dictionaries)

Usage:
    python survey_result_objects.py

    # Export findings to JSON
    python survey_result_objects.py --json survey_results.json

    # Verbose output
    python survey_result_objects.py --verbose
"""

import argparse
import ast
import json
import sys
from collections import defaultdict
from pathlib import Path


class ResultObjectFinder(ast.NodeVisitor):
    """AST visitor to find result object classes and their attributes."""

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.classes = []
        self.current_class = None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definition nodes."""
        # Check if class inherits from Results or related base classes
        base_names = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                base_names.append(base.id)
            elif isinstance(base, ast.Attribute):
                base_names.append(f'{base.value.id}.{base.attr}' if isinstance(base.value, ast.Name) else base.attr)

        is_result = any(
            'Results' in name or 'FlaggableViewResults' in name
            for name in base_names
        )

        if is_result:
            self.current_class = {
                'name': node.name,
                'bases': base_names,
                'file': str(self.filepath),
                'line': node.lineno,
                'attributes': [],
                'has_view': False,
                'has_components': False,
                'has_transient_fields': False,
                'inherits_flaggableview': 'FlaggableViewResults' in ' '.join(base_names),
            }
            self.classes.append(self.current_class)

        # Visit child nodes
        self.generic_visit(node)
        self.current_class = None

    def visit_Assign(self, node: ast.Assign) -> None:
        """Visit assignment nodes to find attribute assignments."""
        if self.current_class is None:
            self.generic_visit(node)
            return

        for target in node.targets:
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
                if target.value.id == 'self':
                    attr_name = target.attr
                    attr_type = self._get_value_type(node.value)

                    self.current_class['attributes'].append({
                        'name': attr_name,
                        'type': attr_type,
                        'line': node.lineno,
                    })

                    # Check for specific patterns
                    if attr_name == 'view':
                        self.current_class['has_view'] = True
                    elif attr_name == 'components':
                        self.current_class['has_components'] = True
                    elif attr_name == '_transient_fields':
                        self.current_class['has_transient_fields'] = True

        self.generic_visit(node)

    def _get_value_type(self, value: ast.expr) -> str:
        """Extract type information from assignment value."""
        if isinstance(value, ast.Call):
            if isinstance(value.func, ast.Name):
                return value.func.id
            elif isinstance(value.func, ast.Attribute):
                return f'{value.func.value.id}.{value.func.attr}' if isinstance(value.func.value, ast.Name) else value.func.attr
        elif isinstance(value, ast.List):
            return 'list'
        elif isinstance(value, ast.Dict):
            return 'dict'
        elif isinstance(value, ast.Set):
            return 'set'
        return 'unknown'


def find_result_objects() -> list[dict]:
    """
    Scan pipeline codebase for result object classes.

    Returns:
        List of dictionaries with result object information
    """
    workspace = Path(__file__).parent.parent
    pipeline_dir = workspace / 'pipeline'

    if not pipeline_dir.exists():
        print(f'Error: Pipeline directory not found: {pipeline_dir}', file=sys.stderr)
        return []

    result_files = list(pipeline_dir.glob('**/resultobjects.py'))
    print(f'Found {len(result_files)} resultobjects.py files to scan')

    all_classes = []
    for filepath in result_files:
        try:
            with open(filepath, 'r') as f:
                source = f.read()

            tree = ast.parse(source, filename=str(filepath))
            finder = ResultObjectFinder(filepath)
            finder.visit(tree)

            if finder.classes:
                all_classes.extend(finder.classes)
                print(f'  {filepath.relative_to(workspace)}: {len(finder.classes)} result class(es)')

        except Exception as e:
            print(f'  Error parsing {filepath} in workspace {workspace}: {e}', file=sys.stderr)

    return all_classes


def categorize_results(result_classes: list[dict]) -> dict:
    """
    Categorize result classes by potential bloat risk.

    Args:
        result_classes: List of result class information

    Returns:
        Dictionary with categorized results
    """
    categories = {
        'high_risk': [],  # Inherits FlaggableViewResults or has view/components
        'medium_risk': [],  # Has transient fields or large collections
        'low_risk': [],  # Simple result objects
    }

    for cls in result_classes:
        if cls['inherits_flaggableview'] or cls['has_view'] or cls['has_components']:
            categories['high_risk'].append(cls)
        elif cls['has_transient_fields'] or any(
            attr['type'] in ('dict', 'list', 'defaultdict', 'OrderedDict')
            for attr in cls['attributes']
        ):
            categories['medium_risk'].append(cls)
        else:
            categories['low_risk'].append(cls)

    return categories


def print_summary(categories: dict) -> None:
    """Print summary of findings."""
    print(f'\n{"=" * 80}')
    print('Result Object Survey Summary')
    print(f'{"=" * 80}')

    total = sum(len(cat) for cat in categories.values())
    print(f'Total result classes found: {total}')
    print(f'  High risk (FlaggableViewResults or view/components): {len(categories["high_risk"])}')
    print(f'  Medium risk (transient fields or collections): {len(categories["medium_risk"])}')
    print(f'  Low risk: {len(categories["low_risk"])}')

    print(f'\n{"=" * 80}')
    print('HIGH RISK: Classes with FlaggableViewResults or view/components')
    print(f'{"=" * 80}')

    # Group by task module
    by_task = defaultdict(list)
    for cls in categories['high_risk']:
        task_match = Path(cls['file']).parent.name
        by_task[task_match].append(cls)

    for task, classes in sorted(by_task.items()):
        print(f'\n{task}/ ({len(classes)} class(es)):')
        for cls in classes:
            indicators = []
            if cls['inherits_flaggableview']:
                indicators.append('inherits FlaggableViewResults')
            if cls['has_view']:
                indicators.append('has .view')
            if cls['has_components']:
                indicators.append('has .components')
            if cls['has_transient_fields']:
                indicators.append('has _transient_fields')

            print(f'  - {cls["name"]} [{", ".join(indicators)}]')
            print(f'    {Path(cls["file"]).relative_to(Path(__file__).parent.parent)}:{cls["line"]}')


def print_detailed_report(categories: dict) -> None:
    """Print detailed report with all attributes."""
    print(f'\n{"=" * 80}')
    print('DETAILED HIGH RISK CLASS BREAKDOWN')
    print(f'{"=" * 80}')

    for cls in categories['high_risk']:
        print(f'\n{cls["name"]} ({Path(cls["file"]).name}:{cls["line"]})')
        print(f'  Bases: {", ".join(cls["bases"])}')
        print(f'  File: {Path(cls["file"]).relative_to(Path(__file__).parent.parent)}')

        if cls['attributes']:
            print(f'  Attributes:')
            for attr in cls['attributes']:
                print(f'    - {attr["name"]}: {attr["type"]} (line {attr["line"]})')
        else:
            print(f'  Attributes: (none found, may be inherited)')

        print(f'  Flags:')
        print(f'    - inherits_flaggableview: {cls["inherits_flaggableview"]}')
        print(f'    - has_view: {cls["has_view"]}')
        print(f'    - has_components: {cls["has_components"]}')
        print(f'    - has_transient_fields: {cls["has_transient_fields"]}')


def main():
    parser = argparse.ArgumentParser(
        description='Survey pipeline result objects for potential bloat',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        '--json',
        metavar='FILE',
        help='Export results to JSON file',
    )
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Print detailed breakdown of all high-risk classes',
    )

    args = parser.parse_args()

    # Find all result classes
    result_classes = find_result_objects()

    if not result_classes:
        print('No result classes found.', file=sys.stderr)
        return 1

    # Categorize by risk
    categories = categorize_results(result_classes)

    # Print summary
    print_summary(categories)

    # Print detailed report if requested
    if args.verbose:
        print_detailed_report(categories)

    # Export JSON if requested
    if args.json:
        json_path = Path(args.json)
        print(f'\nExporting results to {json_path}...')

        export_data = {
            'summary': {
                'total': len(result_classes),
                'high_risk': len(categories['high_risk']),
                'medium_risk': len(categories['medium_risk']),
                'low_risk': len(categories['low_risk']),
            },
            'categories': categories,
        }

        with open(json_path, 'w') as f:
            json.dump(export_data, f, indent=2)

        print('Export complete.')

    # Print recommendations
    print(f'\n{"=" * 80}')
    print('RECOMMENDATIONS')
    print(f'{"=" * 80}')
    print(f'\n{len(categories["high_risk"])} high-risk classes should be investigated:')
    print('  1. Profile with tools/profile_result_objects.py on large datasets')
    print('  2. Consider adding _transient_fields for .view and .components')
    print('  3. Evaluate if full arrays needed or summary stats sufficient')
    print('  4. Consider external storage for presentation data')

    return 0


if __name__ == '__main__':
    sys.exit(main())
