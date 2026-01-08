Dependencies of ``Pipeline``
============================


Runtime
--------

.. _Pipeline: https://open-bitbucket.nrao.edu/projects/PIPE
.. _casaconfig: https://github.com/casangi/casaconfig
.. _pipeline-testdata: https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline-testdata/browse
.. _casatasks.wvrgcal: https://casadocs.readthedocs.io/en/stable/api/tt/casatasks.calibration.wvrgcal.html#casatasks.calibration.wvrgcal


A CASA6-equivalent Python environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. note:: 

    `Pipeline`_ is a Python-based package with CASA6 components and other general-purpose Python libraries as dependencies. As with any python package, it's only compatible and supported with certain Python and 3rd-party libraries versions. In reality, each release is only tested and validated against an ALMA-cycle-specific monolithic CASA6 release (a self-contained Python environment with a built-in portable Python interpreter and associated libraries in other languages). CASA6 distribution itself has limited platform support (see the `CASA6 compatibility matrix <https://casadocs.readthedocs.io/en/stable/notebooks/introduction.html#Compatibility>`_).; users are encouraged to check the OS/libraries compatibility and requirements for running CASA6.

For transparency and encouraging the use and development of ``Pipeline`` in a standard Python environment (e.g. conda), we break down the essential components for a CASA6-equivalent environment as below. In reality, all of them are included in Pipeline-dedicated CASA releases with built-in portable Python interpreter. 




- python3
- ipython
- pip
- numpy
- scipy
- matplotlib
- casatools
- casatasks
- casaplotms
- casampi

.. note::
    
    ``casadata`` and ``almatasks`` are no longer required for ``CASA6>=6.6.1`` due to the introduction of casaconfig and refactor and migration of the `casatasks.wvrgcal`_ task. `casaconfig` is implicitly required by ``casatasks``

Other Pipeline Dependencies
^^^^^^^^^^^^^^^^^^^^^^^^^^^
Here we list other dependency libraries required by Pipeline but not offered in the CASA6 monolithic environment
:

 - Python packages/libraries (also see ``requirements.txt`` in the source code repository)

 - cachetools
 - mako
 - pypubsub
 - intervaltree
 - logutils
 - ps_mem
 - astropy
 - bdsf (for VLASS source detection & mask creation)

 - \*unix-cmd tools

 - ImageMagick
 - the "convert" cmd:
 - Linux only for generating thumbnails; macOS uses "sips" which comes with OS.
 - Also used by ImageMagickWriter from matplotlib.animation in hsd/tasks/common/rasterutil.py (only for developers)
 - the "montage" cmd: required from hifa_renorm
 - poppler-utils
 - the "pdfunite" cmd: required from hifa_renorm
 - Git: for obtaining the Pipeline revision description string.
 - Xvfb/xvfb-run: xvfb from OS is required for the casampi module, which is mandatory for running 
 - uncompress: used by tec_maps.py in CASA for VLA pipeline task hifv_priorcals


Development Tools
-----------------


Packaging
^^^^^^^^^

 - ``wheel``: for installing older Python packages
 - ``csscompressor``: minify CSS during installation

Testing
^^^^^^^

 - ``pytest``
 - ``pytest-cov``



Development tools
^^^^^^^^^^^^^^^^^

 - ``pydocstyle``
 - ``pycodestyle``
 - ``memory_profiler``
 - ``line_pofiler``

Documentation
^^^^^^^^^^^^^

 - ``sphinx``


Version Controls
^^^^^^^^^^

 - ``Git LFS``: for managing the `pipeline-testdata`_ repo

