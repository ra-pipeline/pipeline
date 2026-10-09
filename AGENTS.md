# AGENTS.md: Science Data Processing Pipeline

> Operational directives, architectural invariants, modern Python coding standards, and development guidelines for AI coding assistants and human contributors working on the **Science Data Processing Pipeline**.

## Project Layout

The **Science Pipeline** is an automated data reduction, calibration, and imaging framework for astronomical radio interferometry and single-dish observations (ALMA, VLA, and Nobeyama).
- Operates within CASA (Common Astronomy Software Applications).
- Implements specialized heuristics, calibration engines, imaging algorithms, QA score generation, and interactive HTML WebLog reporting.

```
pipeline/                 # Core Python package
├── infrastructure/       # Execution engine: Context, Task, JobRequest, Callibrary, MPI, Logging, renderer/
├── domain/               # Domain entities: MeasurementSet, SpectralWindow, Field, Antenna, CalTable
├── h/                    # Base heuristic tasks, common utilities, and generic templates
├── hif/                  # General interferometric base (imaging, self-calibration, continuum subtraction)
├── hifa/                 # ALMA specific tasks (extends hif)
├── hifv/                 # VLA specific tasks (extends hif)
├── hsd/                  # General Single-Dish base heuristics and tasks
├── hsdn/                 # Nobeyama specific (extends hsd)
├── extern/               # External and vendored utilities (e.g. sd_applycal_qa)
├── qa/                   # QA score calculators (scorecalculator.py, bpcal.py)
└── recipes/              # Standard operational reduction recipes (XML & Python)
```

Note the naming grammar: h = base, hif* = interferometry (hifa ALMA, hifv VLA), hsd* = single dish (hsdn Nobeyama).

Root level: `docs/` (Sphinx), `tests/` (regression and component tests; unit tests are colocated inside `pipeline/`), `scripts/` (build utilities).

## Architecture Invariants

- All data reduction steps follow the Task pattern: `Inputs` (`pipeline.infrastructure.vdp.StandardInputs`), `Task` (`pipeline.infrastructure.basetask.StandardTaskTemplate`), `Results` (`Results.accept(context)`), `Heuristic` (`pipeline.infrastructure.api.Heuristic`). See [`docs/source/devel/reference/task_types.md`](docs/source/devel/reference/task_types.md) and [`docs/source/devel/reference/context_domain_objects.md`](docs/source/devel/reference/context_domain_objects.md).
- Wrap every CASA task/tool execution in `pipeline.infrastructure.jobrequest.JobRequest` (logging, timing, dry-run, MPI dispatch).
- Raw visibility data is immutable. Register caltables via `context.callibrary`. See [`docs/source/devel/reference/callibrary.md`](docs/source/devel/reference/callibrary.md).
- Parallel-aware tasks must work both serially and under MPI via `pipeline.infrastructure.mpihelpers`. See [`docs/source/devel/reference/parallelization.md`](docs/source/devel/reference/parallelization.md).
- Every scientific task produces one or more `QAScore` objects (`pipeline.infrastructure.pipelineqa.QAScore`) via `pipeline.qa.scorecalculator` or task-specific QA handlers. Scores range 0.0–1.0; warning threshold 0.66, error threshold 0.33 (`pipeline.infrastructure.renderer.rendererutils`). See [`docs/source/devel/reference/QA_scores.md`](docs/source/devel/reference/QA_scores.md).
- Fail with actionable errors (`PipelineException`), not raw stack traces.
- When creating utility modules that serve multiple instruments (ALMA, VLA, etc.) use generic names: `observatory`, `antenna_array`, `location`. Avoid instrument-specific terms in function names. Examples: `get_observatory_location()` not `get_alma_location()`; `observatory_coords.py` not `alma_coords.py`.

## Testing

- Unit tests are colocated with source: `pipeline/infrastructure/utils/utils.py` → `pipeline/infrastructure/utils/utils_test.py`.
- Regression and component tests live in `tests/`.
- All unit tests run offline. Mock `casatools`, `casatasks`, and `casaplotms` with `unittest.mock`. Use `tmp_path` fixtures for MeasurementSets, CalTables, and WebLog scratch data.

| Marker | Description |
|--------|-------------|
| `unit` | Unit tests (colocated) |
| `component` | Component tests (single task) |
| `regression` | End-to-end pipeline tests |
| `fast` | Fast regression tests |
| `slow` | Slow regression tests (requires `--longtests`) |

Full marker list: `pyproject.toml` (`[tool.pytest.ini_options]`).

## Repository Gotchas

- CASA writes `casa-YYYYMMDD-HHMMSS.log` files at runtime. Never commit them.
- Preserve CalTable schemas, task parameter defaults, and WebLog metadata so historical datasets stay reproducible.

## Safety (Data & Archives)

- Fixtures, docs, and examples use synthetic dataset identifiers only (`uid___A002_X000000_X000.ms`, `test_small.ms`).
- Never put proprietary PI data, unreleased targets, or real source coordinates in code, tests, or docs.
- Never write to production archives or external servers during development or testing.

## Git & Review

*Full workflow: [`docs/source/devel/process/git_dev_workflow.md`](docs/source/devel/process/git_dev_workflow.md)*

- Never run `git add`, `git commit`, or `git push` autonomously. Leave changes in the working directory for human review.
- Never run destructive operations (`rm -rf`, `git reset --hard`, history rewrites, `git push --force`) without explicit human instruction.
- Before presenting changes: format and lint touched files, run the unit tests, and rebuild the docs if documentation was touched.

## Common Commands

Tasks are declared in `pyproject.toml` (`[tool.pixi.tasks]`); full list via `pixi task list`. Details: [`docs/source/devel/setup/pixi_tasks.md`](docs/source/devel/setup/pixi_tasks.md). Examples:

```bash
pixi install                       # Installs locked dependencies and editable pipeline
pixi run ruff format <path>        # Format
pixi run ruff check <path>         # Lint (add --fix for safe fixes)
pixi run test-unit                 # Unit tests
pixi run test-regression           # Fast regression suite
pixi run test-pltest1              # Single small ALMA-IF regression test
pixi run casa                      # Interactive CASA shell
pixi run casampi                   # CASA with MPI (CASA_NPROCS ranks, default 4)
pixi run update-data               # Update CASA runtime data (IERS, geodetic)
pixi run -e docs build-docs-fast   # Incremental Sphinx build
```

## Prose

- Keep in-code prose short. Always prefer readable code over comments. In-line comments should never be longer than 2 lines, anything longer should go in a separate documentation page. Never comment long provenance and reasoning, only explain iff code is not self-explanatory. Provenance and why can go in git commit messages and tickets.
- Avoid obvious AI language tells in comments, commit messages, and PR text: em-dashes, "not just X but Y" constructions, filler openers ("It's worth noting that", "In conclusion", "Let's dive in"), and buzzwords ("delve", "leverage", "robust", "seamless", "comprehensive").

## Optional Style Guides (`.skills/`)

Long-form style rules live in `.skills/` (one directory per skill, `SKILL.md` with frontmatter). They are not loaded automatically, so read the relevant file before writing code:

- `.skills/python-code-standards/SKILL.md`: typing, docstrings, logging style
- `.skills/commit-style/SKILL.md`: commit message format
- `.skills/docs-build/SKILL.md`: documentation builds and diagrams
