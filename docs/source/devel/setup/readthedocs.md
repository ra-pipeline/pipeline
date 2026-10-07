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

### PDF (LaTeX) Prerequisites

Building PDF documentation locally (`pixi run -e docs build-pdfs`) requires system LaTeX packages:

- **Ubuntu/Debian:** Install [TeX Live](https://www.tug.org/texlive/) packages:

  ```console
  sudo apt-get install -y latexmk texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended
  ```

- **macOS:** Install [MacTeX](https://www.tug.org/mactex/) via Homebrew:

  ```console
  brew install --cask mactex-no-gui
  ```

The documentation includes an internal variant containing developer notes and architecture docs. To build it locally, set `BUILD_INTERNAL_DOCS=1`:

```console
# Build internal variant into default _build/html
BUILD_INTERNAL_DOCS=1 pixi run -e docs build-docs-fast

# Or build into a separate directory
BUILD_INTERNAL_DOCS=1 pixi run -e docs make -C docs html_fast BUILDDIR=_build_internal
```

## Publishing to ReadTheDocs

[ReadTheDocs][rtd] hosts documentation from the repository via Bitbucket push webhooks. Builds follow `.readthedocs.yaml`:

1. Check out repository branch
2. Install system packages (`texlive`, `imagemagick`, `poppler-utils`)
3. Install [Pixi](https://pixi.sh) and the `docs` environment
4. Run Sphinx builds via Pixi tasks for HTML and PDF, including a second pass with `BUILD_INTERNAL_DOCS=1` for the `/internal/` subsite

Hosted docs: [pipe-docs.readthedocs.io](https://pipe-docs.readthedocs.io/)

- **Build history**: <https://app.readthedocs.org/projects/pipe-docs/builds/>
- **Version settings**: <https://app.readthedocs.org/projects/pipe-docs/versions/>

### Branching Strategy & Version Mapping

Documentation source files live alongside the code in `pipeline/docs/`, so heuristic updates and documentation changes are reviewed and merged in the same pull request.

Our ReadTheDocs setup generally maps repository branches and tags to versions in the bottom-right version picker following the conventions outlined below.

| Git Ref | RTD Version | Description | Flyout Visibility |
| :--- | :--- | :--- | :--- |
| `main` | `latest` | Active development (unreleased changes) | Visible |
| Release tag / branch | `stable` | Current operational release (default landing page) | Visible (Default) |
| `release/YYYY.M.m` (in-flight RC) | `vYYYY.M.m-rc` | Release candidate awaiting sign-off | Hidden / RC |
| `release/YYYY.M.m` | `vYYYY.M.m` | Finalized release (e.g., `v2026.2.1`) | Visible |
| `docs/YYYY.M.m` | `vYYYY.M.m` | Post-release documentation maintenance (e.g., `v2026.2.0`) for adding latest information like [known issues](../../users_guide/known_issues.md) | Visible |
| `PIPE-XXXX-*` | `pipe-xxxx-*` | Feature and bugfix ticket branches | Hidden |

> **Release candidates awaiting sign-off**:
> While a release branch (e.g., `release/2026.2.1`) is still undergoing review, customize its slug to `v2026.2.1-rc` under Read the Docs **Versions** admin settings (or keep it **Hidden**) so external visitors only see `stable` and `latest` until final sign-off.

### Viewing Branch Builds on Read the Docs

Branch builds can be viewed directly by slug:

- **Public docs**: `https://pipe-docs.readthedocs.io/en/<version-slug>/`
- **Internal docs**: `https://pipe-docs.readthedocs.io/en/<version-slug>/internal/`

Read the Docs lowercases branch names and converts slashes/underscores to hyphens (e.g., `PIPE-3268-use-pyasdm-for-metadata-parsing-in-pipeline` becomes `pipe-3268-use-pyasdm-for-metadata-parsing-in-pipeline`). Development branches are marked **Hidden** in the project dashboard so they can be viewed for review without cluttering the public version picker.

### Documentation Contribution Workflow

1. **Branch**: Create `PIPE-XXXX-description` from `main` (for next cycle) or from the target `release/*` branch (for backports).
2. **Build locally**:

   ```console
   pixi run -e docs build-docs-fast
   BUILD_INTERNAL_DOCS=1 pixi run -e docs build-docs-fast
   ```

3. **Push & preview**: Push to Bitbucket, check the build in the [Read the Docs dashboard](https://app.readthedocs.org/projects/pipe-docs/builds/), and confirm the output at `https://pipe-docs.readthedocs.io/en/<branch-slug>/`.
4. **Open PR**: Add the RTD preview link to the Bitbucket PR description for reviewers.

## Design Choices

### API Documentation

For API documentation, we support two Sphinx approaches:

- **Namespace-based**: `sphinx.ext.autodoc` with `autosummary`
- **Module-based**: `automodapi` extension

Both are customized using Jinja + RST templates and local Python code for careful namespace management and cross-module imports.

### Notebooks and MyST-NB

[MyST-NB][myst-nb] is used over nbsphinx for broader feature support, active maintenance, and flexibility with both `.ipynb` notebooks and MyST-enhanced Markdown files.

[myst-nb]: https://myst-nb.readthedocs.io/en/latest/
