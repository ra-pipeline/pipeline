# Heuristics Development and Integration in the Pipeline

The process and stage of heuristics development and its pipeline implementation can vary significantly, ranging from direct drop-ins, light adaptations, refactored codebase heavily leverage on the pipeline infrastructure, to, complete rewrites to become "pipeline-native".

While leveraging existing pipeline infrastructure is always encouraged from start, heuristics development has traditionally occurred within standalone CASA environments, and its pipeline implementation could begin with heuristic prototyping at varying degrees of code qualities in structures, codestyles, in-line documentation, etc.

However, one historical lesson we have learned so far is that a clean-cut scientist-to-developer handover situation for complex heuristics often leads to longer adaptation periods, duplicated efforts, lack of detailed all-in-one technical and design documentation, and communication gaps for a sharedn understanding of the latest state in continuous heuristics development and its pipeline maintenance.

To streamline this process, we strongly encourage heuristics development to leverage Pipeline infrastructure early on:

- Unified Development Environment: During the heuristics development and adaptation period, heuristics contributors and Pipeline developers should use the same codebase (e.g., a temporary Pipeline repository branch), workspace (e.g., open-bitbucket.nrao), and CASA version.

- Collaborative Tools: Use draft pull requests and open Jira tickets for technical discussions and design decisions.

- Shared Documentation: Document the development process on a shared version-controlled platform (e.g., markdown/RST, Jupyter notebooks, inside the Pipeline repository, GoogleDocs, Overleaf) to ensure transparency and ease of access.

## Accessing Lightly-Adapted Prototype Modules in the Pipeline Codebase

For self-contained prototype modules with generic Python/CASA dependencies, you can easily access these modules and functions after drop-in. Follow the steps below to access them under the pipeline namespace:

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
    vis: str, spw: List[int], create_cal_table: bool,
    threshold: Union[NoneType, float], excludechan: Dict,
    atm_auto_exclude: bool, bwthreshspw: Dict, caltable: str
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

get_flagged_solns_per_spw(spwlist, gaintable)

```python
get_flagged_solns_per_spw(spwlist,
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

During the translation/adaptation development period, both developers and prototype contributors can still access, refactor, and experiment from the same ticket codebase. This allows for co-development and discussion of technical matters using the Bitbucket draft PR interface.

## Checklist for Adaptation Process

- Compatibility of Dependency Libraries: Ensure compatibility with different versions of dependencies, such as Astropy and Numpy, considering potential API changes.
- Code Style: Adhere to the established code style guidelines to maintain consistency across the codebase.
- Unspecified Implicit Dependencies: Identify and document any implicit dependencies, for example, functions from `analysis_utils`.
- Avoid Duplications: Utilize existing helper functions within the Pipeline infrastructure to prevent redundant code.

## Uses of `pipeline.extern`

Rules of thumb for the `pipeline.extern` namespace:

- `pipeline.extern` in the `main` and `release` branches should mostly host dropped-in modules/classes with no dependencies on the pipeline modules, classes, or functions, e.g. no `from pipeline.abc import xyz` statements. These dropped-in modules can typically function outside of the Pipeline codebase and are likely being used or considered as standalone tools. Currently, `almarenorm.py`, `almarenorm_2023.py`, `XmlObjectifier.py`, and `findContinuum.py` meet this criterion.

_However_, in practice, for codes in the adaptation-in-progress period, which is still largely in the original form, keeping the code is also acceptable. That way, we have some small conveniences:

- Easier to access/navigate/parse for original contributors as we can easily parse the self-contained code in a simple one-directory structure: this could be helpful when they’re still tinkering with the code during the early heuristics design transferring phase.
- Most modules there aren’t auto-imported (not in `__int__.py`): so it has the advantage that you could debug things in a semi-isolated environment, e.g. crashing only happens when you explicitly import that module: if you are in iPython/CASA interactive session, you can enable `autoreload` magic command `%autoreload2` quickly revise/reload the in-development heuristics module being worked on.

For in-progress dev branches or temporary demo/testing branches, we don't need to obey the above consideration for proper uses of `pipeline.extern`: `pipeline.extern` could be considered as an easy staging area before developers make a more decision on how to dissolve/adapt prototyping code blocks into the pipeline code structures.
