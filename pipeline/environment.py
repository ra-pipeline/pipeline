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

import pkg_resources

from .infrastructure import mpihelpers
from .infrastructure.mpihelpers import MPIEnvironment
from .infrastructure import utils
from .infrastructure import casa_tools

__all__ = ['casa_version', 'casa_version_string', 'compare_casa_version', 'cpu_type', 'hostname', 'host_distribution', 'logical_cpu_cores',
           'memory_size', 'pipeline_revision', 'role', 'cluster_details']


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
def _pipeline_revision():

    def str_encode(s):
        return bytes(s,sys.getdefaultencoding())
    def str_decode(bs):
        return bs.decode(sys.getdefaultencoding(),"strict")
    def pipe_decode(output):
        if isinstance(output,bytes) or isinstance(output,bytearray):
            return str_decode(output)
        elif isinstance(output,tuple):
            return (str_decode(output[0]),str_decode(output[1]))
        else:
            return ("","")
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

    if git_branch != None and (git_branch == "main" or git_branch.startswith("release/")):
        proc = subprocess.Popen( [ pl_path + "/infrastructure/version" ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=pl_path )
        out,err = pipe_decode(proc.communicate( ))
        #print(out)
        releasetag = out.split(" ")[1].strip()
        dirty=""
        version = releasetag
        if (len(out.split(" ")) == 3):
            #print("Latest commit doesn't have a tag. Adding -dirty flag to version string.")
            dirty="+" + out.split(" ")[2].strip() # "+" denotes local version identifier as described in PEP440
            version = version + dirty
        return version
    else: 
        # Consolidate into single version string.
        if commit_hash is None:
            # If no Git commit info could be found, then attempt to load version
            # from the _version module that is created when pipeline package is
            # built.
            try:
                from pipeline._version import version
            except ModuleNotFoundError:
                version = "unknown"
        elif git_branch is None:
            # If info on Git commit is available, but no info on Git branch, then
            # this checkout may have a detached HEAD pointing at a specific tag, so
            # just report the Git commit/tag info.
            version = commit_hash
        else:
            # If both Git commit and branch info are available, then use both.
            version = "{}-{}".format(commit_hash, git_branch)

        return version


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


casa_version = casa_tools.utils.version()
casa_version_string = casa_tools.utils.version_string()
compare_casa_version = casa_tools.utils.compare_version
cpu_type = _cpu_type()
hostname = _hostname()
host_distribution = _host_distribution()
iers_info = utils.IERSInfo()
logical_cpu_cores = _logical_cpu_cores()
memory_size = _memory_size()
role = _role()
pipeline_revision = _pipeline_revision()
ulimit = _ulimit()

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
