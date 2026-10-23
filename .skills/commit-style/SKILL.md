---
name: commit-style
description: Commit message conventions for the Science Data Processing Pipeline. Use when drafting commit messages or pull request descriptions.
version: 1.0.0
tags:
  - git
  - commits
  - conventions
---

# Commit & PR Style

## When to Use

Drafting a commit message or PR description for this repository (always after explicit human confirmation; never commit autonomously).

## Subject Line

- Imperative mood, max 50 characters.
- Conventional Commits prefix: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`.

## Body

- Wrap at 72 characters.
- Explain *what* and *why*, not *how*.
- Reference the specific task, heuristic, or ticket key touched.

## Examples

```
feat: Add bandpass heuristic
```

```
refactor: Simplify callibrary interval tree

Replace nested interval scans with a single sorted pass to
speed up calibration selection for multi-SPW datasets (PIPE-101).
```

## Pull Request Message

- Keep it short for quick human digestion.
- Short point-wise summaries of changes, grouped by category (e.g. Added feature, Bug fix, Optimization, Refactoring, Documentation).
- Refer to tickets for further context where design choices and approaches were discussed.
