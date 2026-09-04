# Heuristics Development and Integration in the Pipeline

The path from heuristics development to pipeline integration can take many forms — from a direct drop-in, through light adaptation or refactoring against pipeline infrastructure, to a developer-lead full rewrite as "pipeline-native" code.

Heuristics development has traditionally occurred in standalone CASA environments, with varying degrees of code quality in structure, style, and documentation. While leveraging existing pipeline infrastructure from the outset is always encouraged, prototype code often begins as an experimental script tested against a limited subset of pipeline operation parameter space, and is refined iteratively from there.

A recurring lesson is that a sharp scientist-to-developer handover for complex heuristics tends to cause longer adaptation periods, duplicated effort, gaps in technical and design documentation, and a loss of shared understanding of the current state of both the heuristics and the pipeline implementation.

To streamline this process, we strongly encourage heuristics contributors and pipeline developers to collaborate early, using shared tooling:

- **Unified development environment**: Both parties should work from the same codebase (e.g., a shared pipeline repository branch), the same workspace (e.g., `open-bitbucket.nrao.edu`), and the same CASA version.
- **Collaborative tools**: Use draft pull requests and open Jira tickets for technical discussions and design decisions.
- **Shared documentation**: Document the development process on a version-controlled platform (e.g., Markdown/RST, Jupyter notebooks in the pipeline repository, Google Docs, or Overleaf) to ensure transparency and ease of access.

## Accessing Lightly-Adapted Prototype Modules in the Pipeline Codebase

For self-contained prototype modules with generic Python/CASA dependencies, you can access them under the pipeline namespace by inserting the local branch clone into the system path.

1. Insert the pipeline branch local clone into the system path:

```console
sys.path.insert(0, os.path.abspath(os.path.expanduser('~/abc/pipeline-branch-local-clone')))
```

2. Access the prototype modules and functions in CASA:

```python
CASA <1>: from pipeline.extern.almarenorm import alma_renorm
CASA <2>: help(alma_renorm)
```

Help on function `alma_renorm` in module `pipeline.extern.almarenorm`

```python
alma_renorm(
    vis: str, spw: list[int], create_cal_table: bool,
    threshold: NoneType | float, excludechan: dict,
    atm_auto_exclude: bool, bwthreshspw: dict, caltable: str
) -> tuple

Interface function for ALMA Pipeline: this runs the ALMA renormalization
heuristic for input vis, and returns statistics and metadata required by
the Pipeline renormalization task.

Args:
    vis: Path to the measurement set to renormalize.
    spw: Spectral Window IDs to process.
    create_cal_table: Save renorm corrections to a calibration table.
    threshold: The threshold above which the scaling must exceed for the
              renormalization correction to be applied. If set to None, then use
              a pre-defined threshold appropriate for the ALMA Band.
    excludechan: Dictionary with keys set to SpW IDs (as string), and
                 values set to channels to exclude for that SpW.
    correct_atm: Get the transmission profiles for the SPW bandpass (or phase) and
                 target(s). The BP (or phase) and target(s) autocorr are compared
                 in establishing the scaling in cases spectra where transmission
                 is low.
```

Help on function `get_flagged_solns_per_spw` in module `pipeline.hif.heuristics.auto_selfcal.selfcal_helpers`

```python
get_flagged_solns_per_spw(spwlist, gaintable, extendpol=False)

Calculate the number of flagged and unflagged solutions per spectral window (spw).

This function examines a gain table and calculates the number of flagged and unflagged
solutions for each spectral window (spw) provided in the spwlist. It also calculates
the fraction of flagged solutions.

Args:
    spwlist (list): List of spectral window IDs to examine.
    gaintable (str): Path to the gain table directory.

Returns:
    tuple: A tuple containing three elements:
        - nflags (list): Number of flagged solutions per spw.
        - nunflagged (list): Number of unflagged solutions per spw.
        - fracflagged (numpy.ndarray): Fraction of flagged solutions per spw.

Raises:
    FileNotFoundError: If the specified gain table directory does not exist.
```

During the translation and adaptation period, both developers and prototype contributors can access, refactor, and experiment from the same ticket branch, enabling co-development and technical discussion via Bitbucket draft PRs.

## Checklist for Adaptation

- **Dependency compatibility**: Verify compatibility with the pipeline's pinned versions of libraries such as `NumPy` and `Astropy`, as well as the targeted CASA version, accounting for potential API changes.
- **Code style**: Follow the project's {doc}`code style guidelines <../codestyle/index>` to maintain consistency across the codebase.
- **Implicit dependencies**: Identify and document any unlisted dependencies, such as functions from `analysis_utils`. Where possible, eliminate such dependencies to avoid hidden coupling and keep the code self-contained.
- **Avoid duplication**: Use existing helper functions in the pipeline infrastructure rather than reimplementing equivalent functionality.

## Uses of `pipeline.extern`

Guidelines for the `pipeline.extern` namespace:

- In `main` and `release` branches, ideally, `pipeline.extern` should contain only self-contained, dropped-in modules or classes that have no imports from within the pipeline (i.e., no `from pipeline.abc import xyz` statements) and can function as standalone tools outside the pipeline codebase. **A dual-use capability — supporting both standalone use outside the CASA-Pipeline setup and use as a pipeline heuristics module — is a prerequisite for long-term residency in `pipeline.extern`.** If a module does not serve both roles, `pipeline.extern` is not its appropriate long-term namespace. Current examples meeting this criterion: `almarenorm.py`, `almarenorm_2023.py`, `XmlObjectifier.py`, and `findContinuum.py`.

- During the adaptation-in-progress period, code that is still largely in its original form may be kept in `pipeline.extern` **for the short term (typically one development cycle)**. This has practical benefits:
  - Original contributors can navigate the semi-self-contained codebase in a simple flat structure, which is useful while heuristics design is still being transferred.
  - Most modules in `pipeline.extern` are not auto-imported (they are not listed in `__init__.py`), so they can be debugged in a semi-isolated environment — a crash only occurs when the module is explicitly imported. In an iPython or CASA interactive session, `%autoreload 2` can be used to reload the module quickly during active development.
  - **Once the porting phase is complete, the code should migrate to the appropriate pipeline namespace (e.g., `pipeline/h*/heuristics/`) or another suitable location.**

- In development or temporary demo/testing branches, the above constraints do not apply. `pipeline.extern` can serve as a convenient staging area while developers decide how to dissolve or integrate prototype code blocks into the pipeline codebase.
