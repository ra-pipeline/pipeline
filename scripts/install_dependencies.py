#!/usr/bin/env python3
"""Install Pipeline dependencies from pyproject.toml without installing Pipeline itself.

Designed for monolithic CASA environments where third-party packages must be
installed into CASA's internal Python site-packages while keeping the Pipeline
source code separate (e.g., paired at runtime via sys.path or PIPE_PATH).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description="Install Pipeline dependencies from pyproject.toml without installing Pipeline itself.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Include development, testing, and linting dependencies.",
    )
    parser.add_argument(
        "--docs",
        action="store_true",
        help="Include documentation building dependencies.",
    )
    parser.add_argument(
        "--exp",
        action="store_true",
        help="Include experimental toolbox dependencies.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include all optional dependencies (dev, docs, exp).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the dependencies and pip command without installing.",
    )
    parser.add_argument(
        "--upgrade-strategy",
        default="only-if-needed",
        help="Pip upgrade strategy (e.g. 'only-if-needed', 'eager').",
    )
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=_ROOT / "pyproject.toml",
        help="Path to pyproject.toml.",
    )
    return parser.parse_known_args()


def get_dependencies(
    pyproject_path: Path,
    include_dev: bool = False,
    include_docs: bool = False,
    include_exp: bool = False,
) -> list[str]:
    """Parse dependencies and selected extras from pyproject.toml."""
    if not pyproject_path.is_file():
        raise FileNotFoundError(f"pyproject.toml not found at: {pyproject_path}")

    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    project = data.get("project", {})
    deps: list[str] = list(project.get("dependencies", []))
    extras = project.get("optional-dependencies", {})

    def add_extra(name: str):
        for item in extras.get(name, []):
            if item.startswith("Pipeline[") or item.startswith("pipeline["):
                # Self-referential extra (e.g. Pipeline[dev])
                sub_extra = item.split("[", 1)[1].rstrip("]")
                for sub in sub_extra.split(","):
                    add_extra(sub.strip())
            elif item not in deps:
                deps.append(item)

    if include_dev:
        add_extra("dev")
    if include_docs:
        add_extra("docs")
    if include_exp:
        add_extra("exp")

    return deps


def main() -> int:
    args, extra_pip_args = parse_args()

    include_dev = args.dev or args.all
    include_docs = args.docs or args.all
    include_exp = args.exp or args.all

    deps = get_dependencies(
        args.pyproject,
        include_dev=include_dev,
        include_docs=include_docs,
        include_exp=include_exp,
    )

    pip_cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
    ]
    if args.upgrade_strategy:
        pip_cmd.append(f"--upgrade-strategy={args.upgrade_strategy}")

    pip_cmd.extend(extra_pip_args)
    pip_cmd.extend(deps)

    if args.dry_run:
        print(f"Target pyproject: {args.pyproject}")
        print(f"Resolved {len(deps)} dependencies:")
        for dep in deps:
            print(f"  - {dep}")
        print("\nEquivalent pip command:")
        print(" ".join(pip_cmd))
        return 0

    print(f"Installing {len(deps)} dependencies using {sys.executable}...")
    env = os.environ.copy()
    return subprocess.call(pip_cmd, env=env)


if __name__ == "__main__":
    sys.exit(main())
