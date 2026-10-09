---
name: python-code-standards
description: Python typing, docstring, and logging style rules for the Science Data Processing Pipeline. Use when writing or editing Python code in this repository.
version: 1.0.0
tags:
  - python
  - code-style
  - typing
---

# Python Code Standards

## When to Use

Writing or editing Python modules under `pipeline/` or `tests/`.

## Annotations

- Put `from __future__ import annotations` at the top of every module.
- Target Python 3.12+. Use built-in generics (`list[str]`, `dict[str, Any]`, `set[int]`, `tuple[str, ...]`), never `typing.List` or `typing.Dict`.
- Use pipe unions (`str | None`, `int | float`), never `typing.Optional` or `typing.Union`.
- Type aliases use the PEP 695 `type` statement:

  ```python
  type SpectralWindowId = int
  ```

- Generic functions use PEP 695 syntax:

  ```python
  def first[T](items: list[T]) -> T: ...
  ```

- Type-hint all function arguments, return types, and class attributes.

## Docstrings

- Google style (PEP 257), configured via `[tool.ruff.lint.pydocstyle]`.
- Do not repeat type information in `Args:` or `Returns:` sections; the signature carries the types. Avoid docstring drift.

## Logging

- Use lazy formatting, not eager f-strings:

  ```python
  logger.info('Processing MS: %s (spw=%d)', vis, spw)
  ```

## Formatting & Lint

- Ruff is the single authority; all rules live in `pyproject.toml` (`[tool.ruff]`). Do not configure editor formatters independently.
- Run `pixi run ruff format <path>` and `pixi run ruff check <path>` on every touched file.
