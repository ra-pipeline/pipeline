# Pipeline Versioning

## Version Number Format

Pipeline version numbers follow the format `YEAR.MAJOR.MINOR.MICRO`, where:

- **YEAR**: Calendar year of the release cycle (e.g., 2025, 2026)
- **MAJOR**: Major release number within the year
- **MINOR**: Minor feature releases
- **MICRO**: Merges of features, bug fixes, and hotfixes

## PEP 440 Compliance and Git-based Version String

Pipeline follows the [PEP 440](https://peps.python.org/pep-0440/) versioning convention, producing a version string of the form `public_label[+local_label]`.

The **public label** is the latest main-branch tag reachable from the Git repo HEAD. In the current tagging scheme, this lightweight tag value always satisfies [PEP 440](https://peps.python.org/pep-0440/) requirements.

The **local label**, when present, is composed of several mandatory or optional elements joined by `-`. Its format is inspired by `git describe --long --tags --dirty --always` and schemes used by [`setuptools-scm`](https://github.com/pypa/setuptools_scm), extended with additional branching information:

- The latest branch tag reachable from HEAD (omitted if identical to the public label)
- The number of additional commits from the latest branch tag to HEAD
- The abbreviated commit hash (with a `g` prefix); omitted when all of the following hold: the repo is clean, there are no additional commits since the latest branch tag, and the branch is a release branch or in a detached HEAD state
- The string `dirty`, included only when the repo has uncommitted changes (a detached HEAD is not considered dirty)
- The branch name; omitted when HEAD is on a release branch (`release/*`) or `main`

To inspect the full version string from a pipeline git checkout, run:

```console
python pipeline/infrastructure/version.py --full-string
```

Example output on a dirty development branch:

```
2026.1.1.31+63-g7e7f7dfcb8-dirty-docs.PIPE-2738-migrate-cli-documentation
```

Here `2026.1.1.31` is the public label (latest main-branch tag), and `63-g7e7f7dfcb8-dirty-docs.PIPE-2738-migrate-cli-documentation` is the local label encoding 63 commits ahead, the abbreviated commit hash, the dirty state, and the current branch name.
