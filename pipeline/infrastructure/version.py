"""Provides utilities for determining software version information based on Git repository metadata.

This module inspects the Git history, including tags, commits, and the current branch state,
to generate version strings. Key functionalities include:

- `get_version`: Retrieves version information based on the last reachable release and branch tags,
  and indicates if the repository state is "dirty". Provides backward compatibility with
  an older versioning script.
- `get_version_string_from_git`: Generates a PEP 440-compliant version string suitable for
  Python packaging, incorporating release tags, commit counts, commit hashes, branch names,
  and dirty status into a public+local label format (e.g., '2024.1.0.5+PIPE-123-10-gabcdef-dirty').

The module can also be run as a script to print the version string directly, supporting both
the legacy format and the full PEP 440 format.

Functions:
    get_version: Gets version tuple (branch_tag, release_tag, [dirty]) from Git.
    get_version_string_from_git: Generates a PEP 440-compliant version string from Git.
"""

import argparse
import re
import shutil
import subprocess
import textwrap

__all__ = ['get_version_string_from_git', 'get_version']


def get_version(cwd: str | None = None) -> tuple[str, ...]:
    r"""Gets version information from Git repository history.

    Inspects the state of the current Git repository tree/branch to determine version
    information. Functionally equivalent to the old Perl script "version", and called mainly
    from setup.py.

    Version tags are identified using specific patterns:
    - Release tags: matching "\d+.\d+.\d+.\d+"
    - Branch tags: matching "PIPE-<number>-x"

    Args:
        cwd: Optional path to Git repository. Defaults to None, which uses the current
            working directory.

    Returns:
        tuple[str, ...]: A tuple containing version information:
            - Empty tuple () if Git history or Git command is not found
            - 2 or 3-element tuple otherwise containing:
                - First element: Last reachable branch tag (possibly empty string)
                - Second element: Last reachable release tag
                - Optional third element: "dirty" suffix if conditions are met

    Examples:
        >>> get_version()
        ('2024.0.0.3', '2024.0.0.3')

        >>> get_version('/path/to/dirty/repo')
        ('', '2024.0.0.3', 'dirty')

    Notes:
        The "dirty" state is defined as any of the following conditions:
        - The latest reachable branch tag is empty
        - The latest tag is not the latest commit
        - The repository has uncommitted changes

        The current working directory or `cwd` must be within a Git repository.

        The function retrieves the latest reachable branch tag and repository "dirty" state.
        However, these values are mainly used by the Bamboo build plan for tarball naming, and
        are not incorporated into the Pipeline build version string.
    """
    gitbin = shutil.which('git')
    if not gitbin:
        return ()  # Git command not found

    def run_git_command(args: list[str]) -> str | None:
        """Run git command and return output as string, or None on error."""
        try:
            return subprocess.check_output([gitbin, *args], stderr=subprocess.DEVNULL, cwd=cwd).decode().strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    # Get current branch
    gitbranch = run_git_command(['rev-parse', '--abbrev-ref', 'HEAD'])
    if not gitbranch:
        return ()  # Not in a git repository or invalid path

    # Get branch hashes
    branch_hashes_str = run_git_command([
        'log',
        '--since',
        '2019-10-01',
        '--simplify-by-decoration',
        '--pretty=%H',
        gitbranch,
    ])
    if not branch_hashes_str:
        return ()

    branch_hashes = branch_hashes_str.splitlines()

    # Get all references and tags
    refstags_str = run_git_command(['show-ref', '--tags', '-d'])
    if not refstags_str:
        return ()

    refstags = refstags_str.splitlines()

    # Get last release and branch tags
    last_release_tag = _get_last_release_tag(gitbranch, branch_hashes, refstags)
    if gitbranch in ['main', 'master'] or 'release/' in gitbranch:
        last_branch_tag = last_release_tag
    else:
        last_branch_tag = _get_last_branch_tag(gitbranch, branch_hashes, refstags)

    output = (last_branch_tag, last_release_tag)

    # Check for dirty state
    is_dirty = False

    # Check for uncommitted changes
    dirty_workspace = subprocess.call([gitbin, 'diff', '--quiet'], cwd=cwd, stderr=subprocess.DEVNULL) != 0

    if last_branch_tag == '' or dirty_workspace:
        is_dirty = True
    else:
        # Check if the latest tag is not the latest commit
        headcommit = run_git_command(['rev-parse', 'HEAD'])
        tagcommit = run_git_command(['rev-list', '-n', '1', last_branch_tag])
        if not headcommit or not tagcommit or tagcommit != headcommit:
            is_dirty = True

    if is_dirty:
        output += ('dirty',)

    return output


def _get_last_tag(gitbranch: str, branchpattern: str, delim: str, hashes: list[str], refstags: list[str]) -> str:
    r"""Gets the most recent tag for the specified git branch matching the given pattern.

    Searches through git commit hashes and reference tags to find the most recent
    version tag that matches the specified branch pattern and is associated with
    the given git branch.

    Args:
        gitbranch: The name of the git branch to search tags for.
        branchpattern: Regular expression pattern to match against tag names.
        delim: Regular expression delimiter to split version strings for comparison.
        hashes: List of git commit hashes to search for tags.
        refstags: List of git reference tags in the format "{hash} refs/tags/{tag}".

    Returns:
        The most recent version tag matching the criteria, or an empty string if none found.
        "Most recent" is determined by sorting the version components numerically.

    Example:
        >>> _get_last_tag(
        ...     'feature/new-feature', r'^v\d+\.\d+\.\d+$', r'\.', ['abc123', 'def456'], ['abc123 refs/tags/v1.2.3', 'def456 refs/tags/v1.2.4^{}']
        ... )
        'v1.2.4'
    """
    # Compile regular expressions once for better performance
    tag_pattern = re.compile(branchpattern)
    delimiter = re.compile(delim)

    # Extract release ID from branch name if it's a release branch
    release_id = gitbranch.split('/')[-1] if 'release/' in gitbranch else ''

    # Dictionary to store version tuples mapped to their tag strings
    versions = {}

    # Process hash and tag reference pairs
    for git_hash in hashes:
        for ref_line in refstags:
            # Skip if the hash doesn't match the beginning of the line
            if not ref_line.startswith(git_hash):
                continue

            # Skip if this is a release branch and the release ID isn't in the tag
            if release_id and release_id not in ref_line:
                continue

            # Extract tag name from reference line
            tag = ref_line.replace(f'{git_hash} refs/tags/', '').replace('^{}', '')

            # Check if tag matches the specified pattern
            if tag_pattern.match(tag):
                # Convert version components to numbers and store as tuple for comparison
                try:
                    version_tuple = tuple(_to_number(x) for x in delimiter.split(tag) if x)
                    versions[version_tuple] = tag
                except (ValueError, TypeError):
                    # Skip tags that can't be properly converted to version numbers
                    continue

    # Return the tag with the highest version number, or empty string if none found
    return versions[max(versions)] if versions else ''


def _get_last_branch_tag(gitbranch: str, hashes: list[str], refstags: list[str]) -> str:
    """Gets the most recent PIPE tag for the specified git branch.

    Searches for the most recent tag following either the 'PIPE-<number>-<number>' pattern
    for branches that start with 'PIPE-' or '<branch_name>-<number>' for other branches.

    Args:
        gitbranch: Name of the git branch to find tags for.
        hashes: List of git commit hashes to search through.
        refstags: List of git reference tags in the format "{hash} refs/tags/{tag}".

    Returns:
        The most recent branch tag matching the pattern, or an empty string if none found.
        For PIPE branches, returns tags like 'PIPE-123-45'.
        For other branches, returns tags like '{branch_name}-123'.

    Examples:
        >>> _get_last_branch_tag('PIPE-456', ['abc123', 'def456'], ['abc123 refs/tags/PIPE-456-1', 'def456 refs/tags/PIPE-456-2'])
        'PIPE-456-2'

        >>> _get_last_branch_tag('feature-branch', ['abc123'], ['abc123 refs/tags/feature-branch-42'])
        'feature-branch-42'
    """
    # Check if the branch follows the PIPE pattern
    pipe_match = re.match(r'(PIPE-\d+)', gitbranch)

    if pipe_match:
        # For PIPE branches, we're looking for tags like "PIPE-123-45"
        base_pattern = pipe_match.group(1)
        branch_pattern = f'{re.escape(base_pattern)}-\\d+'
    else:
        # For other branches, look for tags like "branch-name-123"
        # Escape the branch name to handle special regex characters in branch names
        branch_pattern = f'{re.escape(gitbranch)}-\\d+'

    # Find the latest tag matching the pattern
    return _get_last_tag(gitbranch, branch_pattern, '-', hashes, refstags)


def _get_last_release_tag(gitbranch: str, hashes: list[str], refstags: list[str]) -> str:
    r"""Gets the most recent semantic version release tag from the git repository.

    Searches through the git history to find the most recent release tag that follows
    the semantic versioning pattern <major>.<minor>.<patch>.<build> (e.g., 2024.1.0.5).
    This is typically used for official releases.

    Args:
        gitbranch: Current git branch name. Used for context when searching tags.
        hashes: List of git commit hashes to consider when looking for tags.
        refstags: List of git references and tags in the format "{hash} refs/tags/{tag}".

    Returns:
        The most recent release tag following the pattern <major>.<minor>.<patch>.<build>,
        or an empty string if no matching tag is found.

    Examples:
        >>> _get_last_release_tag('main', ['abc123', 'def456'], ['abc123 refs/tags/2024.0.0.1', 'def456 refs/tags/2024.0.1.0'])
        '2024.0.1.0'

    Notes:
        - Version components are compared numerically, not lexicographically
        - Tags must strictly match the pattern ^\d+\.\d+\.\d+\.\d+$
        - Uses _get_last_tag internally to perform the actual search
    """
    # Search for semantic version tags with the pattern: <major>.<minor>.<patch>.<build>
    # The pattern requires exactly 4 numeric components separated by periods
    version_pattern = r'^\d+\.\d+\.\d+\.\d+$'
    version_delimiter = r'\.'

    return _get_last_tag(gitbranch, version_pattern, version_delimiter, hashes, refstags)


def _to_number(s: str) -> int:
    """Converts a string to an integer for version component comparison.

    Used primarily for converting version components to integers for proper
    numerical sorting of version tags. Handles empty strings and non-numeric
    strings gracefully by returning 0.

    Args:
        s: String to convert to an integer. Typically a version component
           like "2024" or "1" from a version string like "2024.1.0.5".

    Returns:
        The string converted to an integer, or 0 if conversion fails due to
        the string being empty or containing non-numeric characters.

    Examples:
        >>> _to_number('42')
        42
        >>> _to_number('abc')
        0
        >>> _to_number('')
        0
    """
    if not s:
        return 0

    try:
        return int(s)
    except ValueError:
        return 0


def get_version_string_from_git(cwd: str | None = None, verbose: bool = False) -> str:
    """Generate a PEP 440-compliant version string from Git metadata.

    The version string is formatted as 'public_label+local_label':
    - `public_label` is the latest release tag on the main or release branches.
    - `local_label` includes additional context such as the branch name, commit count since the last tag,
      abbreviated commit hash, and a 'dirty' flag if the working directory is modified.

    If the working directory is not a Git repository or Git is not available, 'unknown' is returned.

    Args:
        cwd: Directory to execute Git commands in. Defaults to the current working directory.
        verbose: If True, prints debug information to stdout.

    Returns:
        A version string based on the Git state.

    Examples:
        $ python version.py --help
        $ python version.py -f
        Output: 2023.0.0.32+srdp.2023.1b1-48-g198ca2972-dirty-PIPE-1447-implement-self-calibration-task-hif_selfcal
    """
    gitbin = shutil.which('git')
    if not gitbin:
        return 'unknown'

    try:
        # Silently test if CWD is inside a Git repo; if not, a CalledProcessError Exception
        # will be triggered due to a non-zero subprocess exit status.
        subprocess.check_output([gitbin, 'rev-parse'], cwd=cwd, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        return 'unknown'

    # retrieve the info about the current branch
    try:
        git_branch = (
            subprocess.check_output([gitbin, 'symbolic-ref', '--short', 'HEAD'], cwd=cwd, stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )
    except subprocess.CalledProcessError:
        # https://stackoverflow.com/a/52222248
        # A detached HEAD pointing at a specific tag/commit instead of a branch top will cause a
        # non-zero exit status; in that case, we set git_branch to None.
        git_branch = 'detached'

    # try to get tag information, but we ignore the nontraditional 'dirty' check from get_version()
    tag_tuple = get_version(cwd=cwd)
    if verbose:
        print('# Output from get_version() (backward-compatible with pre-PIPE-1939 Perl script):')
        print(tag_tuple, '\n')
    if len(tag_tuple) > 1:
        last_release_tag = tag_tuple[1]
    else:
        return 'unknown'

    # Retrieve info about current commit.
    #
    # The git-describe call output format, e.g. 2024.0.0.22-27-gc9ac2824d
    # which consists of three elements jointed by '-':
    #       * most recent lightweight tag;
    #       * number of comments since that tag
    #       * commit hash abbreviation with a 'g' prefix
    # note:
    #   '--tags': search lightweight (non-annotated) tags rather than the default annotated tags
    #   '--dirty': this flag optionally adds the '-dirty' string if the repo state is dirty
    try:
        describe_cmd = [gitbin, 'describe', '--always', '--tags', '--long', '--dirty']
        describe_output = subprocess.check_output(describe_cmd, cwd=cwd, stderr=subprocess.DEVNULL).decode().strip()
    except subprocess.CalledProcessError:
        return last_release_tag

    if verbose:
        print(f'# Output from {" ".join(describe_cmd)}:')
        print(describe_output, '\n')

    dirty = describe_output.endswith('-dirty')
    if dirty:
        describe_output = describe_output[:-6]

    try:
        recent_tag, num_commit, hash_abbr = describe_output.rsplit('-', 2)
    except ValueError:
        return last_release_tag

    # In the Pipeline development, only main branch tags are guaranteed to meet PEP440, so we use that for the public label.
    public_label = last_release_tag
    local_parts = []

    is_dev_branch = git_branch != 'main' and not git_branch.startswith('release/')

    if recent_tag != last_release_tag:
        local_parts.append(recent_tag)
    if num_commit != '0':
        local_parts.append(num_commit)
    if dirty or num_commit != '0' or is_dev_branch or git_branch == 'detached':
        local_parts.append(hash_abbr)
    if dirty:
        local_parts.append('dirty')
    if is_dev_branch:
        local_parts.append(git_branch)

    # PIPE-2068: Consolidate into single version string.
    # Only ASCII numbers, letters, '.', '-', and '_' are allowed in the local version label
    local_label = re.sub(r'[^\w.\-_]+', '.', '-'.join(local_parts))
    return f'{public_label}+{local_label}' if local_label else public_label


if __name__ == '__main__':
    DESC = """
    This script derives a PEP 440-compatible version string from the Git repository state.

    When executed inside a Git repository, it prints the resulting version string. By default, for backward 
    compatibility with the pre-PIPE-1913 Perl script, it outputs a space-separated version string consisting 
    of two or three components. This default format is *not* PEP 440-compatible and is only intended for use 
    with legacy CI/CD systems that depend on the old output style.

    Use the --full-string flag to generate the version string used in Pipeline development and installation. 
    This full version is PEP 440-compatible and can serve as a lightweight replacement for `setuptools-scm` in 
    standalone environments outside the NRAO/ALMA/NAOJ Pipeline infrastructure.

    Examples:

        $ python version.py  # note the leading space
        $  2025.0.0.41 dirty

        $ python pipeline/infrastructure/version.py --full-string  # used by the Pipeline build system
        $ 2025.0.0.41+151-g156bc01d1-dirty-update-docs-build-and-packaging-setup

        $ python -m setuptools_scm  # comparable third-party output
        $ 2025.0.0.42.dev151+g156bc01d1.d20250425

    For historical reference, a pre-PIPE-1669 version string appeared as:
        2025.0.0.41+2025.0.0.41-151-g156bc01d1-dirty-update-docs-build-and-packaging-setup
    """

    parser = argparse.ArgumentParser(description=textwrap.dedent(DESC), formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument(
        '-f',
        '--full-string',
        dest='full_string',
        action='store_true',
        help='Generate the full PEP 440-compliant version string used by Pipeline builds.',
    )
    parser.add_argument(
        '-v', '--verbose', dest='verbose', action='store_true', help='Print detailed debug information.'
    )
    args = parser.parse_args()

    if args.full_string:
        print(get_version_string_from_git(verbose=args.verbose))
    else:
        # Default: output a space-separated string for compatibility with legacy CI/CD tooling.
        tag_tuple = get_version()
        if len(tag_tuple) > 1:
            print(' '.join(tag_tuple))
        else:
            print('unknown')
