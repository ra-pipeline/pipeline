# calibpipe

`calibPipeIF.py` drives a single CASA + ALMA-pipeline run; `runbatch.py`
submits a file of MOUS UIDs as slurm jobs, each calling `calibPipeIF.py`.

Both scripts are location-agnostic: no personal filesystem paths are
hardcoded in this repo. Everything that varies per person or per site (which
CASA build, which pipeline branch checkout, where your obscal/analysis-scripts
directories are) lives in a TOML config file that sits right next to
`calibPipeIF.py`, wherever you've put it — and is gitignored (`config*.toml`)
so it never gets committed.

## Setup

These scripts normally live inside a pipeline branch checkout's own
`scripts/` directory (e.g. `<pipeline-checkout>/scripts/calibPipeIF.py`), so
that by default the checkout they're running from *is* the heuristics used
(`SCIPIPE_HEURISTICS` falls back to one level up — `../` — when
`[paths].heuristics_root` isn't set; see `envconfig.build_environment`). But
nothing about the config resolution is specific to that layout: copy
`calibPipeIF.py`/`runbatch.py`/`envconfig.py` to any directory and
`config.toml` in that same directory is what gets picked up.

1. This repo's contents live at `<pipeline-checkout>/scripts/` (or wherever
   you've placed them).
2. Copy `config.example.toml` to `config.toml` in that same directory.
3. Edit it: add an `[envs.<name>]` table per CASA build you use. Leave
   `[paths].heuristics_root` unset unless you want `--env` to switch between
   *other* branch checkouts elsewhere on disk instead of using this one.

```
~/pipeline/main/               <- one pipeline branch checkout (its own git repo)
├── scripts/                    <- this repo's contents live here
│   ├── calibPipeIF.py
│   ├── runbatch.py
│   ├── envconfig.py
│   ├── config.toml             <- your personal config, gitignored
│   └── config-testing.toml     <- as many other configs as you want
└── pipeline/                   <- the checkout's own heuristics package
```

You can keep any number of personal config files here (`config-testing.toml`,
`config-2026val.toml`, ...) and pick one at runtime with `--config=<path>`.

Config file resolution order: `--config=<path>` flag, then
`$CALIBPIPE_CONFIG`, then `config.toml` in the same directory as
`calibPipeIF.py`. `--env=<name>` picks an `[envs.<name>]` table within
whichever config file was resolved, defaulting to that file's `default_env`.

Adding a new CASA build or pipeline branch is just adding a new
`[envs.foo]` table to your TOML file — no script forking needed.

## Usage

```
calibPipeIF.py --mous=uid://A001/X.../X... --env=main --recipe=calimage
calibPipeIF.py --mous=... --config=config-testing.toml --env=pl2025
calibPipeIF.py --mous=... --env=main --print-env   # just show the resolved environment
```

```
runbatch.py pipefile.txt --env=main -c 8 -m 248
```

`pipefile.txt` has one `<mous_uid> [recipe]` per line; `#`-prefixed lines
are comments.

By default a run is quiet (only the return code is checked); pass
`--verbose` to log the subprocess's output line-by-line to the calibPipeIF
log file.

### Interactive shell use

`calibpipe_env.sh` sets up an interactive shell to call
`pipelineMakeRequest`/`casa` directly instead of going through
`calibPipeIF.py`. `source` it (works from bash or zsh) and it sets the
CASA/pipeline environment variables directly in your current shell:

```
source calibpipe_env.sh --env=main
pipelineMakeRequest ...
casa ...
```

It takes the same `--config=`/`--env=`/`--subdir=` flags as
`calibPipeIF.py`. Running it directly (instead of sourcing it) just prints a
reminder, since it has nothing to modify in that case.

The actual TOML parsing and environment construction (a pure-bash port of
`envconfig.py`'s resolution logic, kept in sync with it by hand) lives in
`calibpipe_env_resolve.sh` next to it -- `calibpipe_env.sh` is a thin,
POSIX-portable dispatcher that always runs that script under an explicit
`bash` subprocess (regardless of which shell you sourced it from) and
`eval`s its output, because bash and zsh disagree on array indexing and a
few other things a naively-sourced bash script would get wrong under zsh.
Call `calibpipe_env_resolve.sh` directly (`bash calibpipe_env_resolve.sh
--env=main`) for scripting, or with `--print-env` to dump plain `KEY=value`
lines for inspection or diffing against `calibPipeIF.py --env=<name>
--print-env`.

`--semipass=<EB_uid>`/`--onlysemipass=<EB_uid>` process specific EBs
(comma-delimited `uid://...` list) by running `analysisUtils.asdmExport`
(when not using `--flag`) and patching the generated PPR via
`analyzemscal.modifyPPR`. This is the one feature that needs `calibPipeIF.py`
itself to run under a python with `casatools` available (unlike everything
else in this script, which only needs plain Python 3) — `[paths].aUdir` (or
`--aUdir=`) must point somewhere both `analysisUtils` and `analyzemscal` can
be imported from.

## What moved where

- `env_core2.sh`'s logic (CASA_PATH/SCIPIPE_*/PATH construction) is now
  `envconfig.build_environment()` — pure Python, no shell sourcing.
- Personal `pipeline_env_<name>.sh` files are now `[envs.<name>]` tables in
  your TOML config.
- Site-wide constants (JAVA_HOME, PMR/ACS paths, flux service URLs) have
  built-in defaults in `envconfig.py`; override them via an optional
  `[site]` table if your site differs.
- `SCIPIPE_HEURISTICS` defaults to `../` (the checkout this `scripts/`
  directory lives in) when `[paths].heuristics_root` isn't set — the
  common case, since these scripts ship inside a pipeline branch checkout.

Not ported: the interactive-shell `PS1` prompt decoration from
`env_core2.sh` (irrelevant to a batch driver), and `new_pmr.sh` (unseen
during this rewrite — if you relied on it, extend
`envconfig.build_environment`).

## Testing

```
python3 -m unittest discover -s tests -v
```

`tests/test_runbatch.py` never calls the real `sbatch`/`hostname`; it patches
`subprocess.run` to capture what *would* have been submitted and checks it
against `tests/reference/sbatch_commands.txt` — that file is the actual spec
these tests check against (the exact sbatch command line and the sbatch
script content, one block per scenario), so review/diff it directly rather
than the test code when checking correctness. Two things that would
otherwise be nondeterministic (the temp sbatch script's random path,
`calibPipeIF.py`'s absolute location) are normalized to `<SBATCH_SCRIPT>`/
`<CALIBPIPEIF>`/`<CONFIG>` placeholders before comparison, so the reference
file works regardless of where this checkout lives.

`tests/test_calibPipeIF.py` never calls the real `pipelineMakeRequest` or
`casa`; it fakes both out and records the ordered sequence of
pipelineMakeRequest/copy/casa calls calibPipeIF.py makes against a fake
pipeline-output directory tree built under a temp dir, checking it against
`tests/reference/calibpipeif_calls.txt` — again the actual spec, review/diff
it directly. The `shutil.copy`/`shutil.copytree` calls that copy old
`--flag` products into the new run's working dir are still allowed to run
for real — they're harmless against the throwaway fixture tree — but are
also recorded into the same sequence.
