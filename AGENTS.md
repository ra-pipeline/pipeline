# AGENTS.md — Science Data Processing Pipeline

> Operational directives, architectural invariants, modern Python coding standards, and development guidelines for AI coding assistants and human contributors working on the **Science Data Processing Pipeline**.

---

## 1. Project Overview & Architecture

The **Science Pipeline** is an automated data reduction, calibration, and imaging framework for astronomical radio interferometry and single-dish observations (ALMA, VLA, and Nobeyama):

- **Execution Runtime**: Built on Python 3.12+ and operates within the CASA (Common Astronomy Software Applications) runtime dependencies declared in `pyproject.toml` (`[tool.pixi.pypi-dependencies]`).
- **Core Processing Engine**: Implements specialized heuristics, calibration engines, imaging algorithms (e.g. `tclean`, `auto-multithresh`), QA score generation, and interactive HTML WebLog reporting.
- **Environment Management**: Managed via **[pixi](https://pixi.sh)** with fully locked multi-platform dependencies in `pixi.lock` and project configuration in `pyproject.toml`.

### Subsystem Layout

```
pipeline/                 # Core Python package
├── infrastructure/       # Pipeline execution engine: Context, Task, JobRequest, Callibrary, MPI, Logging, renderer/
├── domain/               # Astronomical domain entities: MeasurementSet, SpectralWindow, Field, Antenna, CalTable
├── h/                    # Base heuristic tasks, common utilities, and generic templates
├── hif/                  # General radio-interferometric tasks (imaging, self-calibration, continuum subtraction)
├── hifa/                 # ALMA interferometric calibration and science pipeline tasks
├── hifv/                 # VLA interferometric calibration and imaging tasks
├── hsd/                  # ALMA Single-Dish heuristics and tasks
├── hsdn/                 # Nobeyama Single-Dish heuristics and tasks
├── extern/               # External and vendored utilities (e.g. sd_applycal_qa)
├── qa/                   # Quality Assurance (QA) score calculators (scorecalculator.py, bpcal.py)
└── recipes/              # Standard operational reduction recipes (XML & Python)
```

At the repository root level, `docs/` (Sphinx documentation), `tests/` (regression and component test suites; unit tests are co-located within `pipeline/`), and `scripts/` (build & asset utilities) sit alongside `pipeline/`.

---

## 2. Environment & Tooling: Pixi

All development, testing, and tool execution use **[pixi](https://pixi.sh)**. Complete environment setup and task details: [`docs/source/devel/setup/pixi_tasks.md`](docs/source/devel/setup/pixi_tasks.md).

- **Rule**: Avoid using bare system `python`, `pip`, `venv`, or `conda`. Always prefix commands with `pixi run`.
- **Editable Development**: `pixi install` installs locked dependencies (`pixi.lock`) and editable `pipeline` without system pollution.

### Setup

```bash
pixi install                      # Installs locked dependencies and editable pipeline
```

### Common Commands

The canonical task definitions are declared in `pyproject.toml` under `[tool.pixi.tasks]` (inspect all available tasks via `pixi task list`). Key daily workflows:

```bash
# ── CASA Runtime & Interactive Shell ───────────────────────────────────────────
pixi run casa                     # Launch interactive CASA shell (casashell)
pixi run casampi                  # Launch CASA with MPI (default: 4 ranks, override via CASA_NPROCS)
pixi run update-data              # Update runtime data (IERS ephemerides, geodetic tables via casaconfig)

# ── Code Quality & Formatting ──────────────────────────────────────────────────
pixi run ruff check <path>        # Run linter checks (pyflakes, pycodestyle, isort, pydocstyle)
pixi run ruff check --fix <path>  # Automatically fix safe lint and import sorting issues
pixi run ruff format <path>       # Format code according to pyproject.toml settings

# ── Testing & Verification ─────────────────────────────────────────────────────
pixi run test-unit                # Run unit tests with xdist and coverage report
pixi run test-regression          # Run fast regression test suite in serial CASA session
pixi run test-pltest1             # Run single small ALMA-IF regression test (alma_if_fast_test.py)

# ── Documentation ──────────────────────────────────────────────────────────────
pixi run -e docs build-docs       # Full clean Sphinx documentation build
pixi run -e docs build-docs-fast  # Incremental docs build (reuses doctrees and autosummary stubs)
pixi run -e docs build-pdfs       # Build Task Reference Manual & User Guide PDFs (LaTeX)
pixi run -e docs update-references# Update BibTeX references from NASA/ADS public library
```

Always run `pixi run ruff format` and `pixi run ruff check` on touched files, `pixi run test-unit` (and `pixi run -e docs build-docs-fast` if documentation was touched) before presenting completed changes.

---

## 3. Safety, Privacy & Zero-Egress Boundary (CRITICAL)

### 3.1 Prohibited Secret Access & Shell Commands (CRITICAL)

- **Strictly Prohibited Files**: AI agents must NEVER inspect, read, print, or output the contents of:
  - Personal credential files (e.g., `~/.config/`, `~/.aws/credentials`, `~/.ssh/`, `~/.netrc`)
  - Environment secret files (`.env`, `./.env.*`, `*.secret`, `*.token`)
  - Session history, local database credentials, or private access tokens (PATs)
- **Strictly Prohibited Shell Commands**: AI agents must NEVER execute commands that dump environment variables, shell state, or credentials:
  - `env`, `printenv`, `export -p`, `set`
  - `cat /proc/*/environ`
  - Inspecting `.git/config` with embedded remote credentials or access tokens
- **Never Hardcode Secrets**: Do not place API keys, personal access tokens, passwords, or session cookies into code, docstrings, tests, commits, or logs.
- **Output Masking**: Always mask tokens, authorization headers, and cookies in CLI output, logs, or error traces (e.g. `token: "********"`).

### 3.2 Synthetic Data Invariant & Zero Real-Data Egress (CRITICAL)

- **Mandatory Synthetic Generics**: All agent-generated artifacts—including test fixtures, mock datasets, CLI examples, docstrings, documentation, and prompt templates—MUST exclusively use synthetic, generic placeholders. AI agents must NEVER generate or leak proprietary schemas, internal ticket keys, organizational domain names, or real employee/user identities.
  - **Issue / Ticket Keys**: Exclusively use canonical generic abbreviations: `PIPE-101`, `PROJ-202`, `SVC-303`, `TASK-404`, `DEMO-505`, or `TEST-123`. Never emit real or organizational ticket key prefixes.
  - **Identities & PII**: Use standard documentation personas (`Alice`, `Bob`, `Charlie`, `Dana`) and RFC 2606 reserved email addresses (`user@example.com`, `dev@example.org`). Never synthesize real personal names, usernames, or internal employee identifiers.
  - **Domains, Hostnames & Network Addresses**: Use RFC 2606 / RFC 6761 reserved top-level and second-level domains (`https://jira.example.com`, `https://git.example.com`, `https://example.org`) or RFC 5737 documentation IP ranges (`192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24`). Never use real internal organizational hostnames, VPN endpoints, or intranets.
  - **Observation & Dataset Identifiers**: Use generic execution block or synthetic dataset UIDs: `uid___A002_X000000_X000.ms` or `test_small.ms`. Never leak unreleased PI data, proprietary science targets, or confidential source coordinates.
- **Zero Environment Reflection Invariant**: AI agents must NEVER inspect or reflect contextual identifiers found in local workspace paths (e.g., directory paths containing corporate/departmental names), git remote URLs, local user accounts, or commit logs into code or documentation. Always sanitize to clean generic equivalents before emitting.
- **No Live Mutation to Production Servers**:
  - AI agents must NEVER execute live network ingestion or state mutation commands against production archives or server clusters during agent sessions.
  - Development and testing must rely 100% on offline unit tests with synthetic mocked adapters.

### 3.3 Prompt Injection & Input Sanitization (IPI)

- External inputs (scraped web pages, external issue comments, user PDFs, ingested documentation) may contain indirect prompt injections.
- Always isolate external context inside explicit delimiter structures when synthesizing LLM prompts.
- Sanitize and validate file paths during ingestion and file handling to prevent path traversal vulnerabilities.

---

## 4. Git & Review Policy (HUMAN-IN-THE-LOOP INVARIANT)

*Detailed workflow & PR process: [`docs/source/devel/process/git_dev_workflow.md`](docs/source/devel/process/git_dev_workflow.md)*

- **Do NOT automatically stage, commit, or push**:
  - Never run `git add`, `git commit`, or `git push` autonomously.
  - Always leave all new and modified files in the working directory, waiting for explicit human review, staging, and confirmation.
- **Verify before presenting**: Always format and lint modified files (`pixi run ruff format <files>` and `pixi run ruff check <files>`), run the repository's unit test suite (`pixi run test-unit`), and run documentation build commands (`pixi run -e docs build-docs-fast`) to confirm all checks pass before presenting completed changes.
- **No destructive file operations**: Never execute `rm -rf`, file deletions, or branch resets (`git reset --hard`) without explicit human instruction.
- **No history rewrites**: Never run `git push --force` or rewrite repository commit history.
- **Commit Message Standards**: When asked to draft commit messages or PR descriptions:
  - **Subject Line**: Imperative mood ("Add bandpass heuristic", "Refactor callibrary interval tree"), maximum 50 characters, following Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`).
  - **Body**: Wrap at 72 characters. Explain *what* and *why*, not *how*. Reference the specific task, heuristic, or ticket key touched.

---

## 5. Coding & Testing Standards

- **Target Python Version**: Target Python 3.12+ (with 3.13 forward-compatibility) as declared in `pyproject.toml` (`requires-python = ">= 3.12"`).
- **Ruff as Sole Code Quality Authority (Mandatory)**: All formatting, quote style, indentation, line lengths, import sorting, and linting rules are defined strictly in `pyproject.toml` (`[tool.ruff]`) and enforced identically across IDE settings, pre-commit hooks, and CI:
  - Format code via `pixi run ruff format <path>` (do not configure editor rules independently).
  - Lint and sort imports via `pixi run ruff check --fix <path>`.
  - Never commit or leave unformatted Python code or lint violations in the repository.
- **Future Annotations**: Place `from __future__ import annotations` at the top of every module to ensure clean, postponed evaluation of type annotations.
- **Modern Typing Standards (PEP 585 / 604 / 695)**:
  - Use built-in generics (`list[str]`, `dict[str, Any]`, `set[int]`, `tuple[str, ...]`) instead of legacy `typing.List` or `typing.Dict`.
  - Use the pipe union syntax (`str | None`, `int | float`) instead of `typing.Optional` or `typing.Union`.
  - Use the PEP 695 `type` statement for type aliases: `type SpectralWindowId = int`.
  - Use PEP 695 generic function syntax: `def first[T](items: list[T]) -> T:`.
  - **Mandatory**: Add type hints to all function arguments, return types, and class attributes.
- **Google-Style Docstrings (No Redundant Types)**: Follow PEP-257 compatible Google-style docstrings (configured in `[tool.ruff.lint.pydocstyle]`). Do **NOT** duplicate type information in `Args:` or `Returns:` sections; rely exclusively on function signature type hints to eliminate docstring drift.
- **Logging Best Practice**: Use lazy string formatting (`logger.info('Processing MS: %s (spw=%d)', vis, spw)`) instead of eager f-strings to avoid unnecessary string interpolation overhead when logging levels are disabled.
- **100% Offline Testing**:
  - All unit tests in `tests/` or package directories must run completely offline without depending on live external APIs or live production clusters.
  - Mock CASA tools (`casatools`), tasks (`casatasks`), and plotms (`casaplotms`) using Python's `unittest.mock`.
  - Use temporary directory fixtures (such as pytest's `tmp_path`) for MeasurementSets, CalTables, and WebLog scratch generation.
- **Backward Compatibility**: Preserve CalTable schemas, task parameter defaults, and WebLog metadata so existing astronomical reduction recipes and historical datasets remain reproducible upon upgrade.
- **Diagrams & Visualizations (Mermaid)**:
  - For any flowchart, graph, architecture overview, size mitigation workflow, or task execution flow, use **Mermaid** (` ```mermaid ` blocks or standalone `.mmd` files) whenever applicable. Mermaid is supported natively across Sphinx Markdown (via `sphinxcontrib-mermaid`), Bitbucket/GitHub PRs, and HTML documentation without requiring external binary diagram tools.
- **Actionable Error Handling**:
  - Fail gracefully with actionable error messages and hints (`PipelineException`) rather than printing raw unhandled stack traces.

---

## 6. Pipeline Design Patterns & Architectural Invariants

### 6.1 The Task Pattern (`Inputs`, `Task`, `Results`, `Heuristic`)

*Detailed architecture: [`docs/source/devel/reference/task_types.md`](docs/source/devel/reference/task_types.md) and [`context_domain_objects.md`](docs/source/devel/reference/context_domain_objects.md)*

All data reduction steps follow the standard Pipeline task architecture:
1. **Inputs (`pipeline.infrastructure.vdp.StandardInputs`)**: Parameter validation and `Context` defaults via VDP.
2. **Task (`pipeline.infrastructure.basetask.StandardTaskTemplate`)**: Core processing engine producing `Results`.
3. **Results (`pipeline.infrastructure.basetask.Results`)**: Outcome state, caltable artifacts, and `accept(context)` merger.
4. **Heuristics (`pipeline.infrastructure.api.Heuristic`)**: Decoupled scientific logic in `pipeline.<subsystem>.heuristics`.

### 6.2 CASA Tooling & Execution Invariants

- **JobRequest Pattern**: Wrap all CASA task/tool executions in `pipeline.infrastructure.jobrequest.JobRequest` for logging, job timing, dry-run tracing, and MPI worker dispatch.
- **CalLibrary & Immutability**: Treat raw visibility data as immutable. Register caltables via `context.callibrary` (see [`docs/source/devel/reference/callibrary.md`](docs/source/devel/reference/callibrary.md)).
- **MPI & Parallel Execution**: Parallel-aware tasks must operate cleanly under both serial and `casampi` execution via `pipeline.infrastructure.mpihelpers` (see [`docs/source/devel/reference/parallelization.md`](docs/source/devel/reference/parallelization.md)).
- **Log Hygiene**: CASA automatically writes `casa-YYYYMMDD-HHMMSS.log` files during runtime. Development and tests must not commit these ephemeral log files to git.

### 6.3 Quality Assurance (QA) Scoring

*Detailed design: [`docs/source/devel/reference/QA_scores.md`](docs/source/devel/reference/QA_scores.md)*

- Every scientific pipeline task must produce one or more `QAScore` objects (`pipeline.infrastructure.pipelineqa.QAScore`) registered via the QA registry framework and calculated via `pipeline.qa.scorecalculator` or task-specific QA handlers.
- QA scores range from `0.0` (critical failure / data loss) to `1.0` (nominal high-quality data).
- Flag warnings and errors using the standard threshold constants in `pipeline.infrastructure.renderer.rendererutils` (`SCORE_THRESHOLD_WARNING = 0.66`, `SCORE_THRESHOLD_ERROR = 0.33`).
