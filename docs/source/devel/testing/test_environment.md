# Test environment setup

## `casa-data` and `pipeline-testdata`

With an identical software stack, numerical test results can still differ due to runtime
session environment (serial vs. mpicasa), OS libraries, OpenMP threading, and the version
of [`casa-data`](https://casadocs.readthedocs.io/en/latest/notebooks/external-data.html)
managed by [`casaconfig`](https://casadocs.readthedocs.io/en/latest/api/casaconfig.html).

Two typical use cases for developers and testers:

- **Case 1 — daily development**: use the latest `casa-data`, auto-updated by `casaconfig`.
- **Case 2 — benchmarking / reproducing reported issues**: pin to a specific `casa-data`
  version checked out from the
  [`casa-data` Git repo](https://open-bitbucket.nrao.edu/projects/CASA/repos/casa-data/browse).
  Set the `CASADATA` environment variable to override the discovery list.

The following snippet for `~/.casa/config.py` handles both cases. Adjust
`measurespath_checklist` and `datapath_list` for your local filesystem layout:

```python
###################################################################################################
# User customization section
###################################################################################################

# 'casa-data' path discovery list in precedence order: first hit will be picked up by casaconfig.
# note: if the environment variable `CASADATA` is set, the value will be prepended to the
# discovery list.
measurespath_checklist = [
    '~/Workspace/nvme/nrao/casa_dist/casarundata',  # maintained by casaconfig
    '~/Workspace/nvme/nrao/casa_dist/casa-data',    # git-lfs clone
    '~/Workspace/local/nrao/casa_dist/casarundata', # maintained by casaconfig
    '~/Workspace/local/nrao/casa_dist/casa-data',   # git-lfs clone
]

# all user data paths to be appended
datapath_list = ['~/Workspace/zfs/nrao/tests/pipeline-testdata']

# note: if measurespath is not maintained by casaconfig (i.e. from git clone), auto_update
# will not take effect.
measures_auto_update = True
data_auto_update = True

###################################################################################################
# Assign rundata/measurespath/datapath for casa6
###################################################################################################

if 'CASADATA' in os.environ:
    measurespath_checklist = [os.environ.get('CASADATA')]
else:
    measurespath_checklist = [
        os.path.abspath(os.path.expanduser(path))
        for path in measurespath_checklist if isinstance(path, str)
    ]
datapath_list = [
    os.path.abspath(os.path.expanduser(path))
    for path in datapath_list if isinstance(path, str)
]

measurespath = None
datapath = []
for path in measurespath_checklist:
    if os.path.isdir(os.path.join(path, 'geodetic')):
        rundata = measurespath = path
        datapath = [measurespath]
        break

try:
    import casaconfig
except ImportError:
    if measurespath is None:
        print(
            '!!! The value of rundata is not set and casatools can not find the expected data in datapath !!!'
        )
        print('!!! CASA6 can not continue. !!!')
        os._exit(os.EX_CONFIG)

datapath += [os.path.expanduser(path) for path in datapath_list if os.path.isdir(path)]

###################################################################################################
```

`casaconfig` (introduced in CASA 6.6.4) and the
[`casa-data` Git repository](https://open-bitbucket.nrao.edu/projects/CASA/repos/casa-data/browse)
are equivalent approaches for managing runtime data. When `casaconfig` detects a Git-managed
directory, `measures_auto_update` and `data_auto_update` take no action — `casaconfig` only
manages directories it initialized itself.

For testing cases that require a specific `casa-data` version: since `casaconfig` does not
support rollback, use the Git repo approach. Note that versions of certain data (e.g. geodetic
measures) in a Git checkout may occasionally lag behind those fetched by `casaconfig`'s
auto-update mechanism from external providers (e.g. the ASTRO FTP server).

## Preventing in-place measures update collisions (node-local staging, PIPE-2882)

When running batch regression suites or automated overnight testing on shared cluster infrastructure (e.g. Slurm or HTCondor), pointing directly to live shared measures repositories (such as `/home/casa/data/distro`) risks test failures if daily maintenance cron jobs update measures tables in-place while tests are active ({jira}`PIPE-2882`).

To completely isolate test runs from shared NFS updates:
- Set the environment variable `PIPELINE_STAGE_LOCAL_MEASURES=true` before running pytest or regression suites.
- The pipeline will automatically stage dynamic measures tables (`geodetic/`, ~9.5 MB) and link `ephemerides/` into node-local scratch storage (`$SLURM_TMPDIR`, `$_CONDOR_SCRATCH_DIR`, or `/tmp`), redirecting C++ casacore lookups and cleaning up on process exit.

For full architectural details, multi-process concurrency handling, and configuration options, see {doc}`Node-Local Measures Staging (PIPE-2882) <../reference/measures_staging>`.
