"""
environment.py defines functions and variables related to the execution environment.
"""
import multiprocessing
import os
import platform
import re
import resource
import subprocess
import sys

from importlib.metadata import version, PackageNotFoundError
from importlib.util import find_spec
import pkg_resources

import casatasks

from .infrastructure import mpihelpers
from .infrastructure.mpihelpers import MPIEnvironment
from .infrastructure import utils
from .infrastructure import casa_tools
from .infrastructure.version import get_version

__all__ = ['casa_version', 'casa_version_string', 'compare_casa_version', 'cpu_type', 'hostname', 'host_distribution',
           'logical_cpu_cores', 'memory_size', 'pipeline_revision', 'role', 'cluster_details', 'dependency_details']


def _cpu_type():
    """
    Get a user-friendly string description of the host CPU.

    :return: CPU description
    """
    system = platform.system()
    if system == 'Linux':
        all_info = subprocess.check_output('cat /proc/cpuinfo', shell=True).strip().decode(sys.stdout.encoding)
        model_names = {line for line in all_info.split('\n') if line.startswith('model name')}
        if len(model_names) != 1:
            return 'N/A'
        # get the text after the colon
        token = ''.join(model_names.pop().split(':')[1:])
        # replace any multispaces with one space
        return re.sub(r'\s+', ' ', token.strip())
    elif system == 'Darwin':
        return subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string']).strip().decode(sys.stdout.encoding)
    else:
        raise NotImplemented('Could not get CPU type for system {!s}'.format(system))


def _logical_cpu_cores():
    """
    Get the number of logical (not physical) CPU cores in this machine.

    :return: number of cores
    """
    return multiprocessing.cpu_count()


def _host_distribution():
    """
    Get a description of the host operating system.

    :return: host OS description
    """
    system = platform.system()
    if system == 'Linux':
        return _linux_os_release()
    elif system == 'Darwin':
        return 'MacOS {!s}'.format(platform.mac_ver()[0])
    else:
        raise NotImplemented('Could not get host OS for system {!s}'.format(system))


def _linux_os_release():
    """Get the Linux distribution name.

    Note: verified on CentOS/RHEL/Ubuntu/Fedora
    """
    try:
        os_release = {}
        with open('/etc/os-release') as f:
            for line in f:
                line_split = line.split('=')
                if len(line_split) == 2:
                    os_release[line_split[0].upper()] = line_split[1].strip().strip('"')
        linux_dist = '{NAME} {VERSION}'.format(**os_release)
    except Exception as e:
        linux_dist = 'Linux (unknown distribution)'

    return linux_dist


def _hostname():
    """
    Get the FQDN for this machine.

    :return: FQDN of this machine
    """
    return platform.node()


def _memory_size():
    """
    Get the amount of memory on this machine.

    :return: memory size, in bytes
    :rtype: int
    """
    try:
        return os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
    except ValueError:
        # SC_PHYS_PAGES doesn't always exist on OS X
        system = platform.system()
        if system == 'Darwin':
            return int(subprocess.check_output(['sysctl', '-n', 'hw.memsize']).strip())
        else:
            raise NotImplemented('Could not determine memory size for system {!s}'.format(system))


# Determine pipeline version from Git or package.
def _pipeline_revision() -> str:
    """
    Get a string describing the pipeline revision and branch of the executing
    pipeline distribution if executing from a Git repo; as a fall-back,
    attempt to get version from built package.
    :return: string describing pipeline version.
    """
    pl_path = pkg_resources.resource_filename(__name__, '')

    # Retrieve info about current commit.
    try:
        # Silently test if this is a Git repo.
        subprocess.check_output(['git', 'rev-parse'], cwd=pl_path, stderr=subprocess.DEVNULL)
        # Continue with fetching commit and branch info.
        commit_hash = subprocess.check_output(['git', 'describe', '--always', '--tags', '--long', '--dirty'],
                                              cwd=pl_path, stderr=subprocess.DEVNULL).decode().strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        # FileNotFoundError: expected if git is not present in PATH.
        # subprocess.CalledProcessError: expected if one of the git commands
        # throws an error.
        commit_hash = None

    # Retrieve info about current branch.
    git_branch = None
    try:
        git_branch = subprocess.check_output(['git', 'symbolic-ref', '--short', 'HEAD'], cwd=pl_path,
                                             stderr=subprocess.DEVNULL).decode().strip()

    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    # Try to get the version
    ver = None
    try:
        ver = get_version(pl_path)
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

    if git_branch is not None and ver is not None and (git_branch == "main" or git_branch.startswith("release/")):
        # Output of the version.py script is a string with two or three space-separated elements:
        # last branch tag (possibly empty), last release tag, and possibly a "dirty" suffix.
        releasetag = ver[1]
        if len(ver) >= 3:
            dirty = ver[2]
            return releasetag + '+' + dirty  # "+" denotes local version identifier as described in PEP440
        else:
            return releasetag
    else:
        # Consolidate into single version string.
        if commit_hash is None:
            commit_hash = "unknown_hash"
            # If no Git commit info could be found, then attempt to load version
            # from the _version module that is created when pipeline package is
            # built.
            try:
                from pipeline._version import version
                ver = version
            except ModuleNotFoundError:
                ver = "0.0.dev0"

        if git_branch is None:
            git_branch = "unknown_branch"

        # this isn't available here
        if ver is None or len(ver) < 2:
            # Invalid version number:
            ver = "0.0.dev0"
        else:
            ver = ver[1]

        # Only ASCII numbers, letters, '.', '-', and '_' are allowed in the local version label (anything after the +)
        commit_hash = re.sub(r'[^\w_\-\.]+', '.', commit_hash)
        git_branch = re.sub(r'[^\w_\-\.]+', '.', git_branch)

        # Consolidate into single version string.
        version_str = "{}+{}-{}".format(ver, commit_hash, git_branch)

        return version_str


def _ulimit():
    """
    Get the ulimit setting.

    The 'too many open files' error during imaging is often due to an
    incorrect ulimit. The ulimit value is recorded per host to assist in
    diagnosing these errors.

    See: PIPE-350; PIPE-338

    :return: ulimit as string
    """
    # get soft limit on number of open files
    soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)

    return '{}'.format(soft_limit)


def _role():
    if not MPIEnvironment.is_mpi_enabled:
        return 'Non-MPI Host'

    if MPIEnvironment.is_mpi_client:
        return 'MPI Client'
    else:
        return 'MPI Server'


def _cluster_details():
    env_details = [node_details]
    if mpihelpers.is_mpi_ready():
        mpi_results = mpihelpers.mpiclient.push_command_request('pipeline.environment.node_details', block=True,
                                                                target_server=mpihelpers.mpi_server_list)
        for r in mpi_results:
            env_details.append(r['ret'])

    return env_details


casa_version = casatasks.version()
casa_version_string = casatasks.version_string()
compare_casa_version = casa_tools.utils.compare_version


def _get_dependency_details(package_list=None):
    """Get dependency package version/path.

    See https://docs.python.org/3.8/library/importlib.metadata.html#metadata
    """
    if package_list is None:
        package_list = ['numpy', 'scipy', 'matplotlib', 'astropy', 'bdsf',
                        'casatools', 'casatasks', 'almatasks', 'casadata',
                        'casampi', 'casaplotms']

    package_details = dict.fromkeys(package_list)
    for package in package_list:
        try:
            package_version = version(package)
            module_spec = find_spec(package)
            if module_spec is not None:
                package_details[package] = {'version': package_version, 'path': os.path.dirname(module_spec.origin)}
        except PackageNotFoundError:
            pass
    return package_details


cpu_type = _cpu_type()
hostname = _hostname()
host_distribution = _host_distribution()
iers_info = utils.IERSInfo()
logical_cpu_cores = _logical_cpu_cores()
memory_size = _memory_size()
role = _role()
pipeline_revision = _pipeline_revision()
ulimit = _ulimit()
dependency_details = _get_dependency_details()

node_details = {
    'cpu': cpu_type,
    'hostname': hostname,
    'os': host_distribution,
    'num_cores': logical_cpu_cores,
    'ram': memory_size,
    'role': role,
    'ulimit': ulimit
}
cluster_details = _cluster_details()
