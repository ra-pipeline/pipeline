"""Entry point for ``python -m pipeline``.

Usage::

    python -m pipeline run  test.yaml           # run locally (blocking)
    python -m pipeline submit test.yaml         # submit as SLURM batch job
    python -m pipeline submit --dry-run test.yaml  # preview sbatch script

The YAML argument follows the same format as ``config.yaml`` (pipeconfig /
casaconfig sections).  It is merged on top of the built-in defaults, so you
only need to override the keys you care about.  The pipeline then dispatches
based on the merged config:

* ``pipeconfig.ppr`` is set → :func:`pipeline.infrastructure.executeppr.executeppr`
* ``pipeconfig.vis`` is set → :func:`pipeline.recipereducer.reduce`

Any ``--loglevel`` / ``--plotlevel`` / ``--importonly`` flags given on the
command line override the corresponding values in the YAML.

After ``pip install -e .`` the ``pipeline`` console script is also available::

    pipeline run  test.yaml
    pipeline submit test.yaml
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import textwrap
from pathlib import Path


# ---------------------------------------------------------------------------
# Shared argument definitions
# ---------------------------------------------------------------------------

def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        'config_yaml',
        metavar='CONFIG_YAML',
        help='Pipeline config YAML (same format as config.yaml). '
             'Sets pipeconfig.ppr / pipeconfig.vis / pipeconfig.procedure '
             'and any other config overrides.',
    )
    parser.add_argument(
        '--loglevel',
        default=None,
        choices=['critical', 'error', 'warning', 'attention', 'info', 'debug', 'todo', 'trace'],
        help='Override pipeconfig.loglevel from the YAML (default: info).',
    )
    parser.add_argument(
        '--plotlevel',
        default=None,
        choices=['all', 'default', 'summary'],
        help='Override pipeconfig.plotlevel from the YAML (default: default).',
    )
    parser.add_argument(
        '--importonly',
        action='store_true',
        default=False,
        help='Stop execution after the importdata stage (PPR mode only).',
    )


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> dict:
    """Load a YAML file with yaml.safe_load."""
    import yaml
    with path.open(encoding='utf-8') as fh:
        return yaml.safe_load(fh) or {}


def _early_apply_prefect_env(config_yaml: Path) -> None:
    """Set Prefect env vars from the user YAML *before* any pipeline import.

    Prefect reads ``PREFECT_API_URL`` at Settings initialization time (i.e.
    when ``from prefect import flow`` first runs).  Setting ``os.environ``
    after that point has no effect.  We therefore parse only the tiny
    ``pipeconfig.prefect`` subtree with plain ``yaml.safe_load`` — no
    pipeline imports required — and propagate the values before anything
    else touches the Prefect module.
    """
    raw = _load_yaml(config_yaml)
    prefect_cfg = raw.get('pipeconfig', {}).get('prefect', {})

    api_url = prefect_cfg.get('api_url')
    if api_url and not os.environ.get('PREFECT_API_URL'):
        os.environ['PREFECT_API_URL'] = str(api_url)

    if prefect_cfg.get('enabled') and not os.environ.get('PIPELINE_USE_PREFECT'):
        os.environ['PIPELINE_USE_PREFECT'] = '1'


def _resolve_config(config_yaml: Path, loglevel_override: str | None, plotlevel_override: str | None) -> dict:
    """Load the user YAML and merge it into the pipeline built-in config.

    Returns the merged pipeconfig dict.
    """
    # Import pipeline.config *after* we have the file so we can pass it in.
    # The built-in cascade (pkg default → user cache → ./config.yaml) already
    # ran at import time; we apply the CLI YAML on top.
    from pipeline.config import config, nested_update

    user_data = _load_yaml(config_yaml)
    # Merge user YAML on top of the live config dict (in-place).
    nested_update(config, user_data)

    pipeconfig = config.get('pipeconfig', {})
    if loglevel_override:
        pipeconfig['loglevel'] = loglevel_override
    if plotlevel_override:
        pipeconfig['plotlevel'] = plotlevel_override

    return pipeconfig


# ---------------------------------------------------------------------------
# `run` subcommand
# ---------------------------------------------------------------------------

def _setup_rawdata_symlink(ppr_file: str | None, rawdata_override: str | None = None) -> None:
    """Create a ``rawdata`` symlink in the CWD.

    Resolution order:
    1. ``pipeconfig.rawdata`` from the config YAML (explicit override).
    2. ``../rawdata`` relative to CWD (sibling directory convention).
    3. The directory that contains the PPR file (fallback for PPR-based runs).

    The symlink is silently skipped when no candidate exists.
    """
    link = Path.cwd() / 'rawdata'
    if link.exists() or link.is_symlink():
        return  # already present

    if rawdata_override:
        target = Path(rawdata_override).resolve()
        if not target.exists():
            print(f'warning: pipeconfig.rawdata does not exist: {target}', file=sys.stderr)
            return
    else:
        sibling = (Path.cwd() / '../rawdata').resolve()
        if sibling.exists():
            target = sibling
        elif ppr_file:
            target = Path(ppr_file).resolve().parent
            if not target.exists():
                return
        else:
            return

    try:
        link.symlink_to(target)
        print(f'rawdata -> {target}')
    except OSError as exc:
        print(f'warning: could not create rawdata symlink: {exc}', file=sys.stderr)


def cmd_run(args: argparse.Namespace) -> int:
    """Execute the pipeline locally (blocking)."""
    config_path = Path(args.config_yaml).resolve()
    if not config_path.exists():
        print(f'error: config YAML not found: {config_path}', file=sys.stderr)
        return 1

    # Must happen before any pipeline import so Prefect reads the correct
    # PREFECT_API_URL at its Settings initialization time.
    _early_apply_prefect_env(config_path)

    pipeconfig = _resolve_config(config_path, args.loglevel, args.plotlevel)

    ppr_file: str | None = pipeconfig.get('ppr')
    vis = pipeconfig.get('vis')
    rawdata: str | None = pipeconfig.get('rawdata') or None
    procedure: str = pipeconfig.get('procedure') or 'procedure_hifa_calimage.xml'
    loglevel: str = pipeconfig.get('loglevel') or 'info'
    plotlevel: str = pipeconfig.get('plotlevel') or 'default'

    _setup_rawdata_symlink(ppr_file, rawdata_override=rawdata)

    if ppr_file:
        ppr_path = Path(ppr_file).resolve()
        if not ppr_path.exists():
            print(f'error: PPR file not found: {ppr_path}', file=sys.stderr)
            return 1
        from pipeline.infrastructure.executeppr import executeppr
        executeppr(
            str(ppr_path),
            importonly=args.importonly,
            loglevel=loglevel,
            plotlevel=plotlevel,
        )
    elif vis:
        vis_list = [vis] if isinstance(vis, str) else list(vis)
        from pipeline.recipereducer import reduce
        reduce(
            vis=vis_list,
            procedure=procedure,
            loglevel=loglevel,
            plotlevel=plotlevel,
        )
    else:
        print(
            'error: neither pipeconfig.ppr nor pipeconfig.vis is set in the config YAML.',
            file=sys.stderr,
        )
        return 1

    return 0


# ---------------------------------------------------------------------------
# `submit` subcommand
# ---------------------------------------------------------------------------


def _build_sbatch_script(config_path: Path, slurm: dict, args: argparse.Namespace) -> str:
    stem = config_path.stem
    job_name = slurm.get('name') or f'pipeline-{stem}'
    cores = slurm.get('cores', 1)
    memory = slurm.get('memory', '20gb')
    walltime = slurm.get('walltime', '1-0:0:0')
    queue = slurm.get('queue')

    # sys.executable is the Python interpreter on the *submitting* host.  If the
    # compute node activates a different environment, update this path accordingly
    # (e.g. hard-code the pixi/conda env Python or add an activation line above).
    run_cmd_parts = [sys.executable, '-m', 'pipeline', 'run', str(config_path)]
    if args.loglevel:
        run_cmd_parts += ['--loglevel', args.loglevel]
    if args.plotlevel:
        run_cmd_parts += ['--plotlevel', args.plotlevel]
    if args.importonly:
        run_cmd_parts.append('--importonly')

    lines = [
        '#!/bin/bash',
        f'#SBATCH --job-name={job_name}',
        f'#SBATCH --ntasks={cores}',
        f'#SBATCH --mem={memory}',
        f'#SBATCH --time={walltime}',
        f'#SBATCH --output=pipeline_{stem}_%j.log',
    ]
    if queue:
        lines.append(f'#SBATCH --partition={queue}')
    lines += [
        '',
        'cd "$SLURM_SUBMIT_DIR"',
        '',
        ' '.join(run_cmd_parts),
        '',
    ]
    return '\n'.join(lines)


def cmd_submit(args: argparse.Namespace) -> int:
    """Generate an sbatch script and optionally submit it."""
    config_path = Path(args.config_yaml).resolve()
    if not config_path.exists():
        print(f'error: config YAML not found: {config_path}', file=sys.stderr)
        return 1

    # Read SLURM options directly from the raw YAML — no pipeline import,
    # so Dask autostart is never triggered for `submit`.
    raw = _load_yaml(config_path)
    slurm = raw.get('pipeconfig', {}).get('dask', {}).get('jobqueue', {}).get('slurm', {})

    script_content = _build_sbatch_script(config_path, slurm, args)
    script_path = Path.cwd() / f'pipeline_{config_path.stem}.sbatch'
    script_path.write_text(script_content, encoding='utf-8')

    if args.dry_run:
        print(f'# sbatch script written to: {script_path}')
        print()
        print(script_content)
        return 0

    result = subprocess.run(['sbatch', str(script_path)], capture_output=True, text=True)
    if result.returncode != 0:
        print(f'error: sbatch failed:\n{result.stderr}', file=sys.stderr)
        return result.returncode

    print(result.stdout.strip())   # e.g. "Submitted batch job 12345"
    print(f'sbatch script: {script_path}')
    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='pipeline',
        description=textwrap.dedent("""\
            ALMA/VLA Pipeline command-line interface.

            The CONFIG_YAML argument uses the same format as config.yaml
            (pipeconfig / casaconfig sections).  Set pipeconfig.ppr to run via
            a Pipeline Processing Request, or set pipeconfig.vis (and optionally
            pipeconfig.procedure) to run via recipereducer.

            Subcommands:
              run     Execute a pipeline config YAML locally (blocking).
              submit  Submit a pipeline config YAML as a SLURM batch job.
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest='subcommand', metavar='SUBCOMMAND')
    subparsers.required = True

    # -- run --
    run_parser = subparsers.add_parser(
        'run',
        help='Execute a pipeline config YAML locally (blocking).',
        description='Run the pipeline in the current process. Dispatches via '
                    'pipeconfig.ppr (executeppr) or pipeconfig.vis (recipereducer).',
    )
    _add_common_args(run_parser)

    # -- submit --
    submit_parser = subparsers.add_parser(
        'submit',
        help='Submit a pipeline config YAML as a SLURM batch job (non-blocking).',
        description='Generate an sbatch script using pipeconfig.dask.jobqueue.slurm '
                    'settings and optionally submit it via sbatch.',
    )
    _add_common_args(submit_parser)
    submit_parser.add_argument(
        '--dry-run',
        action='store_true',
        default=False,
        help='Write the sbatch script and print it without calling sbatch.',
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.subcommand == 'run':
        sys.exit(cmd_run(args))
    elif args.subcommand == 'submit':
        sys.exit(cmd_submit(args))


if __name__ == '__main__':
    main()
