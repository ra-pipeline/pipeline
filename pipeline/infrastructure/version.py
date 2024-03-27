import re
import subprocess

# This script has to be run within the Git repository.
# It will inspect the state of the current tree/branch in the workspace.
# Functionally equivalent to the perl script "version", and called only from setup.py

# Version type is used to select the appropriate grep pattern.
# The idea is to look for either the latest master/release type tag "\d+.\d+.\d+.\d+"
# or PIPE-<number>-x tags. Both are required to construct a meaningful number for
# the pipeline wheels.


def get_version(cwd=None):
    """
    Return: a tuple containing last branch tag (possibly empty),
            last release tag, and possibly a "dirty" string
    """

    def tonumber(value):
        try:
            return int(value)
        except ValueError:
            return 0

    def get_last_tag(gitbranch, branchpattern, delim):
        branchpattern = re.compile(branchpattern)
        delim = re.compile(delim)
        releaseid = gitbranch.split('/')[-1] if 'release/' in gitbranch else ''
        versions = {}
        for githash in hashes:
            for line in refstags:
                # if 'release/' is not in gitbranch, the second condition is always true
                if line.startswith(githash) and releaseid in line:
                    tag = line.replace(githash+' refs/tags/', '').replace('^{}', '')
                    if branchpattern.match(tag):
                        # split the version string into a tuple by the given delimiter,
                        # then convert each element of the tuple from string to int
                        # in order to sort the versions correctly.
                        # "versions" is a dict in which keys are the parsed tuples of ints,
                        # and values are the original version strings
                        versions[tuple(tonumber(x) for x in delim.split(tag))] = tag
        # sort the dict items by the first element (tuples of ints)
        # and return the second element (the corresponding version string)
        # of the highest value (i.e. most recent version)
        return sorted(versions.items())[-1][1] if versions else ''

    def get_last_branch_tag(gitbranch):
        match = re.match(r'(PIPE-\d+)', gitbranch)
        if match:
            branchpattern = match.group(1) + r'-\d+'
        else:
            branchpattern = gitbranch + r'-\d+'
        return get_last_tag(gitbranch, branchpattern, '-')

    def get_last_release_tag(gitbranch):
        return get_last_tag(gitbranch, r'^\d+\.\d+\.\d+\.\d+$', r'\.')

    gitbranch = subprocess.check_output(
        ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
        stderr=subprocess.DEVNULL, cwd=cwd).decode().strip()

    hashes = subprocess.check_output(
        ['git', 'log', '--since', '2019-10-01', '--simplify-by-decoration', "--pretty=%H", gitbranch],
        stderr=subprocess.DEVNULL, cwd=cwd).decode().splitlines()

    refstags = subprocess.check_output(
        ['git', 'show-ref', '--tags', '-d'],
        stderr=subprocess.DEVNULL, cwd=cwd).decode().splitlines()

    last_release_tag = get_last_release_tag(gitbranch)
    if gitbranch in ['main', 'master'] or 'release/' in gitbranch:
        last_branch_tag = last_release_tag
    else:
        last_branch_tag = get_last_branch_tag(gitbranch)

    output = (last_branch_tag, last_release_tag)
    dirty_workspace = subprocess.call(['git', 'diff', '--quiet'], cwd=cwd)

    if last_branch_tag == '' or dirty_workspace:
        # No tag at all for branch
        output += ('dirty',)
    else:
        # Check if the latest tag is the latest commit
        headcommit = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'],
            stderr=subprocess.DEVNULL, cwd=cwd).decode().strip()
        tagcommit = subprocess.check_output(
            ['git', 'rev-list', '-n', '1', last_branch_tag],
            stderr=subprocess.DEVNULL, cwd=cwd).decode().strip()
        if tagcommit != headcommit:
            output += ('dirty',)

    return output


if __name__ == '__main__':
    print(' '.join(get_version()))
