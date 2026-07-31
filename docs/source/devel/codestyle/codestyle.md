# Code Style and Docstring Guide

This page documents the code style and docstring conventions used in the Pipeline codebase.

> **Note**: For historical reasons, these rules are **not retroactively enforced** across the entire codebase. They serve as recommendations and guidelines — please follow them when writing new code or modifying existing code.

> **GitHub Copilot**: The repository includes a `.github/copilot-instructions.md` file that encodes these same conventions as custom instructions for GitHub Copilot. When using Copilot inside this repository, it will automatically apply the style rules described on this page (type annotation syntax, docstring format, logging style, etc.) to any generated or refactored code.

## References

- [PEP 257 — Docstring Conventions](https://www.python.org/dev/peps/pep-0257/)
- [PEP 484 — Type Hints](https://www.python.org/dev/peps/pep-0484/)
- [PEP 604 — Union types with `|`](https://peps.python.org/pep-0604/)
- [PEP 585 — Built-in generics](https://peps.python.org/pep-0585/)
- [PEP 695 — Type Parameter Syntax](https://peps.python.org/pep-0695/)
- [Google Python Style Guide — Comments and Docstrings (§3.8)](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings)
- [Python `typing` module](https://docs.python.org/3/library/typing.html)

---

## Formatting Rules

These settings are enforced by [`ruff`](https://docs.astral.sh/ruff/) (configured in `pyproject.toml`):

```{list-table}
:header-rows: 1
:widths: 40 60

* - Setting
  - Value
* - Line length
  - 120 characters
* - Indentation
  - 4 spaces
* - String quotes
  - Single quotes (`` ' ``) preferred; double quotes only if the string contains a single quote
* - Docstring code block line length
  - 140 characters
```

---

## Type Annotations

The codebase targets **Python 3.12+**. Use modern type syntax throughout:

```{list-table}
:header-rows: 1
:widths: 45 55

* - Avoid
  - Use instead
* - `typing.List[str]`
  - `list[str]`
* - `typing.Dict[str, int]`
  - `dict[str, int]`
* - `typing.Optional[str]`
  - `` str | None ``
* - `typing.Union[str, int]`
  - `` str | int ``
* - `TypeAlias` / `Vector = list[float]`
  - `type Vector = list[float]` (PEP 695)
* - `TypeVar`-based generics
  - `def func[T](x: T) -> T` (PEP 695)
```

**All function arguments and return values must have type annotations.**

---

## Logging

Use lazy `%`-style formatting — never f-strings — so that the string is only evaluated if the message is actually emitted:

```python
# Bad
logger.info(f'Processing {len(data)} items')

# Good
logger.info('Processing %s items', len(data))
```

---

## Docstrings

### Format

Use **Google-style** docstrings ([PEP 257](https://www.python.org/dev/peps/pep-0257/) compatible), as parsed by the [Napoleon](https://www.sphinx-doc.org/en/master/usage/extensions/napoleon.html) Sphinx extension.

### Type information

Do **not** repeat type information in `Args` or `Returns` descriptions — it is already captured in the function signature annotations:

```python
# Bad (redundant types in docstring)
def fetch_data(ids: list[int | str]) -> dict:
    """Fetch data.

    Args:
        ids (list[int | str]): List of IDs.

    Returns:
        dict: The result.
    """

# Good
def fetch_data(ids: list[int | str]) -> dict:
    """Fetch data.

    Args:
        ids: List of IDs.

    Returns:
        The result.
    """
```

### Referring to code symbols

Use single backticks for references to functions, classes, methods, and modules in the description body. Sphinx/Napoleon renders these as cross-references:

```python
"""Process data using advanced algorithms.

This function calls `numpy.mean` and `scipy.optimize.minimize`
internally. It is similar to `pandas.DataFrame.apply` but
optimized for numerical arrays.

See Also:
    `calculate_stats`: Related function for statistical analysis.
    `preprocess_data`: Use this to prepare data before calling this function.
"""
```

### Referring to values and literals

Use **double backticks** (RST inline code) for literal values, option strings, and filenames:

```python
"""Set the ``hm_phaseup`` parameter to ``'snr'`` or ``'manual'``."""
```

Use *italics* for file paths or variable names mentioned in a narrative context:

```python
"""The *hm_phaseup* parameter controls the phase-up heuristics."""
```

Reserve **bold** for warnings or strong emphasis only:

```python
"""Changing this parameter is **not recommended** for most users."""
```

### Parameters with options and defaults

Document options and defaults as sub-items under the parameter description. Use double backticks for each option value:

```python
def run(parallel: str | bool | None = None):
    """Run the task.

    Args:
        parallel: Process multiple MeasurementSets in parallel using the
            casampi parallelization framework.

            Options: ``'automatic'``, ``'true'``, ``'false'``, ``True``, ``False``

            Default: ``None`` (equivalent to ``False``)
    """
```

### Math

For inline math use `:math:`:

```python
"""The condition is :math:`A = \\pi r^2`."""
```

For display (block) math use the `.. math::` directive:

```python
"""
Check whether the S/N condition is satisfied.

The condition is:

.. math::

    \\frac{\\text{Peak S/N}}{\\text{dividing\\_factor}} \\times \\mathrm{RMS} < 5.0
"""
```

### Examples section

`Examples` is a first-class Google-style section. Use it for doctestable code:

```python
def add(a: int, b: int) -> int:
    """Add two integers.

    Args:
        a: The first integer.
        b: The second integer.

    Returns:
        The sum of the two integers.

    Examples:
        >>> add(2, 3)
        5
        >>> add(-1, 1)
        0
    """
    return a + b
```

### Complete example

```python
type Vector = list[float]


def fetch_data(ids: list[int | str]) -> dict:
    """Fetch data from the flux service.

    Args:
        ids: List of source IDs to query.

    Returns:
        Mapping of ID to flux measurement result.
    """
    logger.info('Fetching %s items', len(ids))
    return {}


def first[T](items: list[T]) -> T:
    """Return the first element of a list.

    Args:
        items: Non-empty list of items.

    Returns:
        The first element.
    """
    return items[0]
```
