---
name: docs-build
description: Sphinx documentation build commands and diagram conventions for the Science Data Processing Pipeline. Use when editing docs/ or adding diagrams to documentation.
version: 1.0.0
tags:
  - documentation
  - sphinx
  - diagrams
---

# Documentation Build

## When to Use

Editing anything under `docs/`, adding architecture diagrams, or updating references.

## Commands

```bash
pixi run -e docs build-docs        # Full clean Sphinx build
pixi run -e docs build-docs-fast  # Incremental (reuses doctrees and autosummary stubs)
pixi run -e docs build-pdfs       # Task Reference Manual & User Guide (LaTeX)
pixi run -e docs update-references# Refresh BibTeX from NASA/ADS public library
```

## Diagrams

- Use Mermaid (fenced ` ```mermaid ` blocks or standalone `.mmd` files) for flowcharts, graphs, architecture overviews, and task execution flows.
- Mermaid renders natively via `sphinxcontrib-mermaid` and on GitHub/Bitbucket; no external diagram tools required.

## Verify

- After any docs edit, run `pixi run -e docs build-docs-fast` and confirm it completes without new warnings before presenting changes.
