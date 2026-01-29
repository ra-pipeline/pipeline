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
On macOS, this is typically `/Applications/CASA.app/Contents/MacOS`; on Linux, it is the `bin/` directory inside the unpacked CASA tarball, e.g. `casa-6.5.3-28-py3.8/bin`. `PYTHONNOUSERSITE=1` is used to prevent the `pip` command from checking dependencies from the user's site-packages directory. This is necessary to isolate the user's site-packages directory from your CASA development environment, which is generally confined to the unpacked CASA tarball directory. You may create a series of alias shortcuts to avoid accidentally using the wrong Python environment and tools:

```console
alias casa_pip='PYTHONNOUSERSITE=1 ${casa_bin}/pip3 --disable-pip-version-check'
alias casa_python='PYTHONNOUSERSITE=1 ${casa_bin}/python3'
```

The `pip` command above should install the dependencies in the CASA site-packages directory, which can be verified with this:

```python
CASA <1>: import astropy
CASA <2>: astropy.__version__
Out[2]: '5.2.1'
CASA <3>: astropy.__path__
Out[3]: ['/opt/casa_dist/casa-6.5.3-28-py3.8/lib/py/lib/python3.8/site-packages/astropy']
```

## Standard install

The Pipeline can be built and installed like any standard Python packages, with

```console
casa_pip install .
```

If Pipeline is already installed, this command will upgrade the
package with the new installation.

You can also build a local wheel for easy distribution: `casa_pip wheel --no-deps .`
For a custom installation with optional dependencies (e.g. building docs, running pytest plugins, or performance profiling), one can also try

```console
casa_pip install .[dev]
```

or

```console
casa_pip install .[docs]
```

## Developer install

As a developer, you will quickly grow weary of creating an egg every time you
wish to exercise new code. The pipeline supports developer installations. In
this mode, a pseudo installation is made which adds your source directory to
the CASA site-packages. Hence the working version you are editing will become
the pipeline version available to CASA.

```console
casa_pip install --editable .
```

To uninstall the developer installation, execute

```console
casa_pip uninstall pipeline
```

## Pairing CASA and Pipeline at runtime

To pair and use a working copy of Pipeline with the local CASA installation temporarily without
touching your CASA copy, you can add the Pipeline source code path to the CASA/Python `sys.path`
at runtime. This can be conveniently achieved by adding the example code block below to your
CASA [`rcdir`](https://casadocs.readthedocs.io/en/latest/api/configuration.html) (default to `~/.casa`)
`startup.py`:

```python
import sys, os
pipe_path=os.environ.get('PIPE_PATH', None)
if isinstance(pipe_path,str):
    pipe_abspath=os.path.abspath(os.path.expanduser(pipe_path))
    if os.path.isdir(pipe_abspath) or os.path.islink(pipe_abspath):
        print("\nAdding the Pipeline package from: {} to the Python interpreter sys.path\n".format(pipe_abspath))
        sys.path.insert(0, pipe_abspath)
        import pipeline
        import pipeline.infrastructure.executeppr as eppr  
        pipeline.initcli() 
```

Here `PIPE_PATH` is a shell environment variable that points at your Pipeline code path, e.g., `export PIPE_PATH=/path/to/workspace/pipeline_branches/main`.

Note that this use case will only work if the CASA installation has all dependency libraries required by the Pipeline package. For a pristine "vanilla" CASA build without Pipeline pre-installed, this can be done with:

```console
casa_pip install --upgrade-strategy=only-if-needed -r requirements.txt
```

## Pipeline versioning

The Pipeline versioning following the principle convention outlined in [PEP440](https://peps.python.org/pep-0440/): public_label[+local_label]
The public label is the latest main branch tag that is reachable from the Git repo HEAD: in our current tagging scheme, the lightweight tag value always meets the [PEP440](https://peps.python.org/pep-0440/) requirements.
On the other hand, the "local_label" string is joined by several mandate or optical string elements with '-'. The format is inspired by the output of `git describe --long --tags --dirty --always` and various schemes used by [`setuptools-scm`](https://github.com/pypa/setuptools_scm), but gets further expanded with additional branching information:

* the latest branch tag that is reachable from the HEAD, if it is identical to b, it will be skipped
* the number of additional commits from the latest branch tag to the current HEAD
* abbreviated commit name (always with a 'g' prefix); this is skipped if the following conditions are all met: the repo state is clean; no additional commits from the recent branch tag to the HEAD; the branch is a "release" branches, or unknown (e.g. a HEAD detached state)
* the 'dirty' string : only included if the repo is in a "dirty" state. note that a detached HEAD is not considered "dirty" here.
* the branch name; however, if the HEAD is a release branch (`release/*` or `main`), it will be skipped.
