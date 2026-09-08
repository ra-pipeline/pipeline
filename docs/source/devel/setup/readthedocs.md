# Building & Publishing Documentation

This page describes how Pipeline documentation is built locally and automatically published to [ReadTheDocs][rtd]. The pipeline documentation is organized into three main groups: **User Reference** (guides, task manual, releases), **Developer Notes** (internal documentation like this page), and **Code Examples** (practical use cases).

[rtd]: https://about.readthedocs.com

## Getting Started: Building Docs Locally

Use the Pixi `docs` environment to build documentation locally. For detailed task descriptions and options, see the [Pixi Workflow guide](pixi_tasks.md#documentation-building).

```console
# Full HTML build (runs all notebooks)
pixi run -e docs build-docs

# Fast HTML build (skips notebook re-execution)
pixi run -e docs build-docs-fast

# PDF build
pixi run -e docs build-pdfs
```

HTML output is written to `docs/_build/html/`. Open `docs/_build/html/index.html` in a browser to preview.

### Building the Internal Variant

Pipeline documentation includes an "internal" variant with developer-only notes and sections. To build the internal variant locally, prepend the `BUILD_INTERNAL_DOCS=1` environment variable:

```console
# Build internal variant (overwrites default _build/html directory)
BUILD_INTERNAL_DOCS=1 pixi run -e docs build-docs-fast

# Alternatively, build into a separate directory
BUILD_INTERNAL_DOCS=1 pixi run -e docs make -C docs html_fast BUILDDIR=_build_internal
```

## Publishing to ReadTheDocs

[ReadTheDocs][rtd] automatically builds and hosts documentation from the repository. The `.readthedocs.yaml` configuration defines the build steps:

1. Check out the repository branch
2. Install LaTeX dependencies (via `apt`)
3. Install [Pixi](https://pixi.sh) and set up the `docs` environment
4. Build HTML and PDF documentation using Sphinx via Pixi tasks

[ReadTheDocs][rtd] then ingests the artifacts and hosts them on the platform.

### Automatic Builds via Webhooks

Webhooks are configured between the `Open-Bitbucket@NRAO` instance and [ReadTheDocs][rtd] to trigger builds automatically on push events, with flexible control over conditions.

### Internal Variant on ReadTheDocs

The custom `.readthedocs.yaml` configuration executes a double-build: first the public site, then the internal build placed in a hidden `/internal/` subfolder (e.g., `https://<project-url>/en/latest/internal/`).

## Design Choices

### API Documentation

For API documentation, we support two Sphinx approaches:

- **Namespace-based**: `sphinx.ext.autodoc` with `autosummary`
- **Module-based**: `automodapi` extension

Both are customized using Jinja + RST templates and local Python code for careful namespace management and cross-module imports.

### Notebooks and MyST-NB

[MyST-NB][myst-nb] is used over nbsphinx for broader feature support, active maintenance, and flexibility with both `.ipynb` notebooks and MyST-enhanced Markdown files.

[myst-nb]: https://myst-nb.readthedocs.io/en/latest/
