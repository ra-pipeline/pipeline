# Documentation Infrastructure

This page describes the documentation setup that enables automatic generation of Pipeline documentation from the codebase.

## General Context

[rtd]: https://about.readthedocs.com

Our documentation is organised into three main groups:

- **User Reference**: guides and instructions for end-users, task reference manual, and past releases
- **Developer Notes**: internal documentation aimed at developers, such as the page you are currently viewing
- **Code Examples**: practical examples and use cases showcasing pipeline functionality

## Technical Setup

The [ReadTheDocs][rtd] autobuild process runs on an `Ubuntu 24.04` container, with custom build steps defined in the `.readthedocs.yaml` file. The build sequence is:

1. Check out the repository branch
2. Install LaTeX dependencies (via `apt`)
3. Install [Pixi](https://pixi.sh) and set up the `docs` environment
4. Build HTML and PDF documentation using Sphinx via Pixi tasks

Finally, [ReadTheDocs][rtd] ingests the generated artifacts and hosts them on the platform.

### Automation and Webhooks

Webhooks are configured between the `Open-Bitbucket@NRAO` instance and [ReadTheDocs][rtd]. This allows builds to be triggered automatically on webhook events, with flexible control over the trigger conditions.

### Sphinx Configuration and Extensions

For API documentation, we use Sphinx with two potential approaches:

1. **Namespace-based**: using `sphinx.ext.autodoc` with `autosummary`
2. **Module-based**: using the `automodapi` extension

Both approaches are customised using Jinja + RST templates, directives, and local Python code blocks, with careful management of namespaces, cross-module imports, and ongoing improvements to docstrings.

[myst-nb]: https://myst-nb.readthedocs.io/en/latest/

For notebooks, we use [MyST-NB][myst-nb] over nbsphinx, due to its broader feature support and more actively maintained documentation. It supports both `.ipynb` notebooks and MyST-enhanced Markdown files, offering flexibility and easier long-term maintenance.

## Building the Docs Locally

Use the `docs` Pixi environment to build locally. From the repository root:

```console
# Full HTML build (runs all notebooks)
pixi run -e docs build-docs

# Fast HTML build (skips notebook re-execution)
pixi run -e docs build-docs-fast

# PDF build
pixi run -e docs build-pdfs
```

The HTML output is written to `docs/_build/html/`. Open `docs/_build/html/index.html` in a browser to preview the result.

### Building the Internal Variant

The pipeline documentation supports an "internal" variant that includes developer-only notes and sections (such as this one). By default, the public build excludes these files. To build and preview the internal variant locally, prepend your build command with the `BUILD_INTERNAL_DOCS=1` environment variable. 

```console
# Build the internal variant (overwrites the default _build/html directory)
BUILD_INTERNAL_DOCS=1 pixi run -e docs build-docs-fast

# Alternatively, build into a separate directory to preserve your public build cache
BUILD_INTERNAL_DOCS=1 pixi run -e docs make -C docs html_fast BUILDDIR=_build_internal
```

When building on Read the Docs, the custom `.readthedocs.yaml` configuration executes a double-build. It first generates the public site, then automatically runs the internal build and places the output in a hidden `/internal/` subfolder (e.g., `https://<project-url>/en/latest/internal/`).
