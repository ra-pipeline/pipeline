# Building the pipeline

## Prerequisites

It is recommended to put the CASA `bin` directory first on your path for the
duration of the installation procedure.

### Downloading and Installing CASA

If you don't already have CASA installed, you can find recent builds at [CASA pre-releases](https://casa.nrao.edu/download/distro/casa/releaseprep/). Sort by "Last Modified" to find the most recent version.

After downloading a CASA build, follow the instructions on the [CASA Installation Guide](https://casadocs.readthedocs.io/en/stable/notebooks/usingcasa.html#Full-Installation-of-CASA-5-and-6) to install CASA.

### Dependency Requirements

Following the change from [PIPE-1699](https://open-jira.nrao.edu/browse/PIPE-1699), Pipeline now specifies the required standard Python dependencies in a [requirements.txt](../requirements.txt) file, and recommends using `pip` to install them directly from the Python Package Index ([PyPI](https://pypi.org/)).
The [`pipeline/extern`](../pipeline/extern) directory now only contains the non-standard Python packages/modules contributed by the developers and heuristics development team.

Note that this file is currently *not* used by [`setup.py`](../setup.py) to auto-install dependencies, and only serves as a reference for development and packaging purposes.
In addition, the list only includes dependencies that are *not* bundled in the monolith CASA release designated for the next Pipeline release, and their version specifications are continuously examined against potential compatibility issues with other Python packages already shipped in CASA.
The developer team will maintain the file to reflect the current state of the dependency requirements across the development cycle.

To use this file manually, you can type the following command:

```console
PYTHONNOUSERSITE=1 ${casa_bin}/pip3 install --disable-pip-version-check \
    --upgrade-strategy=only-if-needed -r requirements.txt
```

Note that here `casa_bin` is the path to the CASA `bin` directory.
On macOS, this is typically `/Applications/CASA.app/Contents/MacOS`; on Linux, it is the `bin/` directory inside the unpacked CASA tarball, e.g. `casa-6.5.3-28-py3.8/bin`. `PYTHONNOUSERSITE=1` is used to prevent the `pip` command from checking dependencies from the user's site-packages directory. This is necessary to isolate the user's site-packages directory from your CASA development environment, which is generally confined to the unpacked CASA tarball directory.

The `pip` command above should install the dependencies in the CASA site-packages directory, which can be verified with this:

```python
CASA <1>: import astropy
CASA <2>: astropy.__version__
Out[2]: '5.2.1'
CASA <3>: astropy.__path__
Out[3]: ['/opt/casa_dist/casa-6.5.3-28-py3.8/lib/py/lib/python3.8/site-packages/astropy']
```

## Standard install

The pipeline can be built and installed like any standard Python module, with

```console
python3 setup.py install
```

If a pipeline egg is already installed, this command will upgrade the
pipeline with the new installation.

## Temporary install

To build a pipeline .egg file without installing the egg and hence overwriting
the CASA default pipeline installation, execute

```console
python setup.py bdist_egg
```

The resulting egg file can be found in the dist directory and added to the
CASA sys.path in your CASA prelude, e.g.,

```python
import sys
sys.path.insert(0, '/path/to/workspace/dist/Pipeline.egg')
```

### Switching between pipeline versions

Developers often have multiple workspaces, each workspace containing a
different version of the pipeline. Below is an example prelude.py which
switches between workspaces based on the launch arguments given to CASA, e.g.,
`casa --trunk --egg` makes the most recent pipeline egg from the *trunk*
workspace available. Edit the workspaces dictionary definition to match your
environment.

```python
#
#  CASA prelude to switch between development environments and eggs
#
# casa --trunk         : puts the 'trunk' workspace directory first on the CASA
#                        path
# casa --trunk --egg   : put the most recent egg from the trunk workspace first
#                        on the CASA path
import os.path
import sys

# edit workspaces to match your environment. The dictionary keys become the
# recognised CASA command line arguments.
workspaces = {
    'trunk': '~/alma/pipeline/svn/pristine/pipeline',
    'sessions': '~/alma/pipeline/svn/pristine/pipeline-feature-sessions',
}

def find_most_recent_egg(directory):
    # list all the egg files in the directory..
    files = [f for f in os.listdir(directory) if f.endswith('.egg')]

    # .. and from these matches, create a dict mapping files to their
    # modification timestamps, ..
    name_n_timestamp = dict([(f, os.stat(os.path.join(directory,f)).st_mtime) for f in files])

    # .. then return the file with the most recent timestamp
    return max(name_n_timestamp, key=name_n_timestamp.get)


def get_egg(path):
    dist_dir = os.path.join(path, 'dist')
    try:
        egg = find_most_recent_egg(dist_dir)
    except OSError:
        msg = 'Error: no pipeline egg found in {!s}\n'.format(dist_dir)
        sys.stderr.writelines(msg)
        return None
    else:
        return os.path.join(dist_dir, egg)


for k, workspace_path in workspaces.items():
    full_path = os.path.expanduser(workspace_path)
    if '--' + k in sys.argv:
        if '--egg' in sys.argv:
            entry_to_add = get_egg(full_path)
            entry_type = 'egg'
        else:
            entry_to_add = full_path
            entry_type = 'directory'
        if entry_to_add:
            msg = 'Adding {!s} to CASA PYTHONPATH: {!s}\n'.format(entry_type, entry_to_add)
            sys.stdout.writelines(msg)
            sys.path.insert(0, entry_to_add)

```

## Developer install

As a developer, you will quickly grow weary of creating an egg every time you
wish to exercise new code. The pipeline supports developer installations. In
this mode, a pseudo installation is made which adds your source directory to
the CASA site-packages. Hence the working version you are editing will become
the pipeline version available to CASA.

```console
python3 setup.py develop
```

or

```console
pip3 install --editable .
```

To uninstall the developer installation, execute

```console
python3 setup.py develop -u
```

### Optional: removing legacy pipeline installation from CASA

To prevent any possible conflict between legacy pipeline installation and new
pipeline code, the legacy pipeline installation should be removed from CASA.
Execute:

```console
casa-config --sh-exec rm '$PYTHONHOME/pipeline'
```
