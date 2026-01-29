# Prevent Accidental Commits to the `main` Branch in Your Local Repo

To prevent any accidental commits to the "main" branch in a local clone, you can optionally set up a "pre-commit" hook. This hook is a small piece of code that runs automatically prior to every commit attempt.

The pre-commit hook described below will check if you are trying to commit directly to the "main" branch. If it detects such an attempt, it will reject the commit and issue a warning message.

## Manual Installation of a Git Hook

Here's how to install the pre-commit hook:

1. **Navigate to your local repository:**

    ```bash
    cd pipeline.git
    ```

    (Replace `pipeline.git` with the actual name of your local pipeline repository directory if it's different).

2. **Create the pre-commit hook file:**

    ```bash
    touch .git/hooks/pre-commit
    ```

3. **Edit the pre-commit hook file:**
    Open the newly created `.git/hooks/pre-commit` file in your preferred text editor and add the following content:

    ```sh
    #!/bin/sh
    branch="$(git rev-parse --abbrev-ref HEAD)"
    if [ "$branch" = "main" ]; then
      echo "You cannot commit directly to the main branch"
      exit 1
    fi
    ```

4. **Make the file executable:**

   ```bash
   chmod +x .git/hooks/pre-commit
   ```

## Using the [`pre-commit`](https://pre-commit.com) Package

[`pre-commit`](https://pre-commit.com) is a Python package that provides a framework for managing Git hooks.
Instead of writing and installing each hook manually, you define them in a configuration file (`.pre-commit-config.yaml`) and [`pre-commit`](https://pre-commit.com) will manage that for you when you run `pre-commit install`.
Then you just need to ensure that you have the correct configuration file (version tracked in the Pipeline repositatory), and that `pre-commit` is available in your environment.

The pipeline repository contains a default configuration at: `.pre-commit-config.yaml`
