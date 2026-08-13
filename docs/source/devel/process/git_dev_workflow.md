# Git Development Workflow

We use the standard **feature branch workflow** — no commits are made directly to the `main` branch. The typical steps are described below.

## 1. Get a local copy of the repository

```bash
git clone https://open-bitbucket.nrao.edu/scm/pipe/pipeline.git
```

## 2. Create a new branch for your work

**Option A — via Jira/Bitbucket (recommended):**

Use the "Create branch" link on the Jira ticket. After the branch is created in Bitbucket, fetch it and check it out locally:

```bash
git fetch --all
git checkout <branchname>
```

**Option B — locally:**

```bash
git checkout -b <branchname>
```

The branch name should be prefixed with the relevant Jira ticket ID, e.g. `PIPE-XXX-your-description`.

> **Note**: The ticket tarball packaging function on Jira requires the branch name to begin with exactly `PIPE-`. Variations such as `bugfix/PIPE-` will not work.

## 3. Check out an existing ticket branch

```bash
git fetch --all
git branch -a | grep <ticket-number>   # find the branch name (or look on the ticket)
git checkout <branch-name>
```

## 4. (PLWG) Use with CASA

CASA must have Pipeline bundled, or the required pip packages installed. Ensure the following environment variables are set:

- `desired casa/bin` first in `$PATH`
- `SCIPIPE_HEURISTICS=/lustre/naasc/sciops/comm/rindebet/pipeline/branches/${PIPE_BRANCH}`
- `SCIPIPE_SCRIPTDIR=${SCIPIPE_HEURISTICS}/pipeline/recipes`
- `SCIPIPE_ROOTDIR=/lustre/naasc/sciops/comm/$USER/pipeline/root`
- `SCIPIPE_LOGDIR=/lustre/naasc/sciops/comm/$USER/pipeline/logs`
- `FLUX_SERVICE_URL="https://almascience.org/sc/flux"`

Add the following to `~/.casa/startup.py`:

```python
if "SCIPIPE_HEURISTICS" in os.environ:
    sys.path.insert(0, os.path.expandvars("$SCIPIPE_HEURISTICS"))
    import pipeline
    pipeline.initcli()
    import pipeline.infrastructure.executeppr as eppr
```

Then run CASA normally — the `--pipeline` flag is not required.

## 5. Make changes and commit

```bash
git add <file>          # or: git add -p  (interactive, recommended for reviewing hunks)
git commit -m "Commit message"
```

## 6. Push your branch to Bitbucket

```bash
git push origin <branchname>
```

## 7. Open a Pull Request

Create a Pull Request on Bitbucket to merge your branch into `main`. Any team member can review and approve, including yourself.

## 8. Code Review and Merge

Once the PR is open, request a review from a team member. After approval:

- The person who opened the PR should typically be the one to perform the merge.
- Enable the **delete branch on merge** option to keep the repository clean. All commits are preserved in `main`.

## 9. Update your local repository after merge

```bash
git checkout main
git pull
git branch -d <branchname>   # optional: delete the branch locally
```

## Tip: Prevent accidental commits to `main`

The repository ships with a `.pre-commit-config.yaml` that configures several hooks, including:

- **`no-commit-to-branch`** — blocks direct commits to `main` or any `release/*` branch.
- **`ruff`** — runs the linter and formatter on all Python files.

### Option A — Use the `pre-commit` package (recommended)

[`pre-commit`](https://pre-commit.com) is a Python package that provides a framework for managing Git hooks. Instead of writing and installing each hook manually, you define them in a configuration file (`.pre-commit-config.yaml`) and `pre-commit` manages that for you.

The pipeline repository already contains a default configuration at `.pre-commit-config.yaml` (version-tracked). You only need to ensure `pre-commit` is available in your environment and then install the hooks once per clone:

```bash
pip install pre-commit      # or: conda install -c conda-forge pre-commit
pre-commit install
```

All hooks will then run automatically on every `git commit`.

### Option B — Manual hook (legacy)

If you prefer not to use the `pre-commit` package, you can install a minimal hook manually:

1. Go to your local clone:

   ```bash
   cd pipeline.git
   ```

   (Replace `pipeline.git` with the actual name of your local clone directory if it differs.)

2. Create the hook file:

   ```bash
   touch .git/hooks/pre-commit
   ```

3. Open `.git/hooks/pre-commit` in an editor and add the following content:

   ```sh
   #!/bin/sh
   branch="$(git rev-parse --abbrev-ref HEAD)"
   if [ "$branch" = "main" ]; then
     echo "You cannot commit directly to the main branch"
     exit 1
   fi
   ```

4. Make it executable:

   ```bash
   chmod +x .git/hooks/pre-commit
   ```
