Pipeline with Conda
===================


.. warning::

 Running and developing the pipeline from a Conda environment is not officially supported or validated for observatory operation, and the information provided here is for demonstration purposes only.

.. contents:: Table of Contents
   :local:
   :depth: 2


Setup - step-by-step
--------------------


.. _Miniforge: https://github.com/conda-forge/miniforge
.. _Micromamba: https://micromamba.readthedocs.io/en/latest/
.. _miniforge3: https://github.com/conda-forge/miniforge/releases
.. _conda-forge: https://conda-forge.org
.. _CASA6: https://casadocs.readthedocs.io/en/stable/
.. _Pipeline: https://open-bitbucket.nrao.edu/projects/PIPE
.. _casashell: https://casadocs.readthedocs.io/en/stable/api/casashell.html
.. _casatasks: https://casadocs.readthedocs.io/en/stable/api/casatasks.html
.. _casatools: https://casadocs.readthedocs.io/en/stable/api/casatools.html
.. _casampi: https://casadocs.readthedocs.io/en/stable/notebooks/parallel-processing.html#Advanced:-Interface-Framework
.. _environment.yml: https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline/browse/environment.yml
.. _requirements.txt: https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline/browse/requirements.txt
.. _pyproject.toml: https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline/browse/pyproject.toml


- Install `Miniforge`_ or `Micromamba`_: below we use `miniforge3`_ installer as examples, which only includes the `conda-forge`_ channel by default.

  .. code-block:: bash

    #!/bin/bash

    # 1. Detect OS and Architecture
    OS=$(uname -s | sed 's/Darwin/MacOSX/')
    ARCH=$(uname -m)

    # 2. Construct the download URL
    URL="https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-${OS}-${ARCH}.sh"

    # 3. Download the installer
    echo "Downloading Miniforge for ${OS}-${ARCH}..."
    curl -L "$URL" -o miniforge.sh

    # 4. Run the installer (adjust the installation path as needed)
    echo "Installing to /opt/miniforge3..."
    bash miniforge.sh -b -f -p /opt/miniforge3

    # 5. Update and Cleanup
    conda update --all
    conda clean -a -y
    rm miniforge.sh
    echo "Installation complete."

- Reproduce a Python environment with modular `CASA6`_ components and the dependency libraries required by them and Pipeline, e.g., `openmpi <https://www.open-mpi.org>`_.

  - Fetch source code:

    .. code-block:: bash

      git clone https://open-bitbucket.nrao.edu/scm/pipe/pipeline.git
      cd pipeline
  
  - Recreate the Conda environment with all `CASA6`_ components for `Pipeline`_ execution and development:

    .. code-block:: bash

      PIP_VERBOSE=3 conda env update --name pipeline --file=environment.yml -vv
      
    or just simply run:

    .. code-block:: bash

      conda env update

    This will create or update a Conda environment named 'pipeline'.  

    .. note::
      
        Occasionally, you might also update, clean up, or remove a pre-existing environment:

        .. code-block:: bash

          conda env update --name pipeline --file=environment.yml # Update an existing environment
          conda env update --name pipeline --file=environment.yml --prune # Remove packages not in the environment file
          conda env remove --name pipeline # Remove the entire environment

- Activate the environment and verify the `CASA6`_ software stack installation:

  .. code-block:: bash

    conda activate pipeline
    # Create the default CASA data directory if it doesn't exist (can be customized later)
    mkdir -p ~/.casa/data
    # Verify casatools installation/functionality; CASA data could be fetched from internet if not present locally by casaconfig
    # Also see: https://casadocs.readthedocs.io/en/stable/api/casaconfig.html
    python -c "import casatools; print('casatools version:', casatools.version_string())"

- Install `Pipeline`_:

  .. code-block:: bash

    pip install .

  To install `Pipeline`_ along with optional dependencies for developmental and experimental purposes in editable mode, try:

  .. code-block:: bash

    pip install -e .[dev,docs]

  Our `ReadtheDocs` setup of `Pipeline`_ uses this approach for documentation builds (see `.readthedocs.yaml <https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline/browse/.readthedocs.yaml>`_)

  .. note::

    `environment.yml`_, `pyproject.toml`_, and `requirements.txt`_
    
    - The scope of `environment.yml`_ (Conda environment definition) is to create a monolithic-`CASA6`_-like self-contained Python environment with all `CASA6`_ components and dependencies required by `Pipeline`_ installed.
    - `pyproject.toml`_ handles `Pipeline`_ packaging and build system requirements.
    - A separate `requirements.txt`_ (which is referenced in both `environment.yml`_ and `pyproject.toml`_) handles `Pipeline`_ core/functional dependencies. The separation is intentional for balancing different needs / use cases, e.g. monolithic and modular `CASA6`_ builds, developer/testing installation setups, etc.

Run `Pipeline`_
---------------

Typical use patterns of `Pipeline`_ include running within a headless environment, or on a workstation interactively, either in CASA serial or parallel mode:

For an interactive use case, one could simply run this to start a `casashell`_ session:

.. code-block:: bash

  conda activate pipeline
  python -m casashell

For headless sessions to execute automated `Pipeline`_ data processing:

.. code-block:: bash

  conda activate pipeline
  xvfb-run -a python -m casashell --nologger --log2term --agg -c run_pipeline.py


Here ``run_pipeline.py`` is a Python script. Example content could be:

.. code-block:: python

  import pipeline.recipereducer, os
  pipeline.recipereducer.reduce(vis=['../rawdata/uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.ms'],
                                procedure='procedure_hifa_calimage.xml', loglevel='debug')

or alternatively:

.. code-block:: python

  import pipeline
  pipeline.initcli()

  context = h_init()
  context.set_state('ProjectStructure', 'recipe_name', 'hifa_calimage')
  try:
      hifa_importdata(vis=['uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.ms'], session=['default'], dbservice=True)
      hifa_flagdata()
      hifa_fluxcalflag()
      hif_rawflagchans()
      hif_refant()
      h_tsyscal()
      hifa_tsysflag()
      hifa_tsysflagcontamination()
      hifa_antpos()
      hifa_wvrgcalflag()
      hif_lowgainflag()
      hif_setmodels()
      hifa_bandpassflag()
      hifa_bandpass()
      hifa_spwphaseup()
      hifa_gfluxscaleflag()
      hifa_gfluxscale()
      hifa_timegaincal()
      hifa_renorm(createcaltable=True, atm_auto_exclude=True)
      hifa_targetflag()
      hif_applycal()
      hif_makeimlist(intent='PHASE,BANDPASS,AMPLITUDE')
      hif_makeimages()
      hif_makeimlist(intent='CHECK', per_eb=True)
      hif_makeimages()
      hifa_imageprecheck()
      hif_checkproductsize(maxcubesize=40.0, maxcubelimit=60.0, maxproductsize=500.0)
  finally:
      h_save()



Below are some examples of more detailed managed ways to run the `Pipeline`_.

Serial
^^^^^^

- A plain Python session without invoking `casashell`_:

  .. code-block:: bash

    PYTHONNOUSERSITE=1 OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 xvfb-run -a python ../scripts/run_pipeline.py

  Here we isolate the user site-packages by setting the ``PYTHONNOUSERSITE`` environment variable to ``1`` to avoid potential package conflicts.
  We also set ``OMP_NUM_THREADS`` and ``OPENBLAS_NUM_THREADS`` to control the number of threads used by OpenMP/OpenBlas-enabled libraries 
  (e.g., ``numpy``, ``scipy``, ``casatools``, etc.) during the Pipeline processing.

- A session via `casashell`_, with `CASA6`_ logging and plotting enabled:

  .. code-block:: bash

    PYTHONNOUSERSITE=1 OMP_NUM_THREADS=4 OPENBLAS_NUM_THREADS=4 xvfb-run -a \
        python -m casashell --nologger --log2term --agg -c ../scripts/run_pipeline.py

Parallel
^^^^^^^^

- A standard Python session with `casashell`_ invoked:

  .. code-block:: bash

    PYTHONNOUSERSITE=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
        mpirun --mca btl_vader_single_copy_mechanism none -x OMP_NUM_THREADS -x OPENBLAS_NUM_THREADS -x PRTE_MCA_quiet -np 4 \
        python -c "import casampi.private.start_mpi; exec(open('run_pipeline.py').read())"  

  .. admonition:: `casampi.private.start_mpi`

    As discussed/examined in `CAS-14037 <https://open-jira.nrao.edu/browse/CAS-14037>`_, `casashell`_ include some configuration-dependent 
    (modular vs. monolithic) environment initialization to help `casampi`_ set up the client and server roles for different openmpi processes 
    while avoid circular imports during the `casampi` process initialization. Without `casashell` involvement, you need to execute `casampi.private.start_mpi`
    outside the scope of `casatasks`_ (`casashell`_ implicitly import `casatasks` in monolithic casa distributions). As a workaround, include the
    following boilerplate command at the beginning of your workflow script.

      .. code-block:: python

        try:
            import casampi.private.start_mpi  # assign the client and server roles
            import casatasks                  # ensure the time-based logfile name
        except (ImportError, RuntimeError) as error:
            pass

    Alternatively, as the above example shows, prepend them into a one-liner command with the ``-c`` option of the ``python`` executable.
    If you run a parallel CASA session without going through `casashell`_ (e.g., ```mpirun -n 4 python run_script.py```), place the code snippet above at the beginning of your Python script before any `casatasks`_ import actions to avoid deadlocks.

    The consequence of not doing so is that all openmpi processes will be initialized in the same way and instructed to execute the content of your script concurrently, without the expected ``1 x mpiclient + (nproc-1) x mpiserver`` configuration.


- A session via `casashell`_, with `CASA6`_ logging and plotting enabled:

  .. code-block:: bash

    PYTHONNOUSERSITE=1 OMP_NUM_THREADS=1 xvfb-run -a \
    mpirun -display-allocation -display-map -oversubscribe --mca btl_vader_single_copy_mechanism none -x OMP_NUM_THREADS -n 4 \
            python -c "import casampi.private.start_mpi; import casashell.__main__" --nologger --log2term --agg -c ../scripts/run_pipeline.py

  If you run a parallel CASA session with `casashell`_, you need to add the code snippet inside ``~/.casa/config.py``. Failure to do so will result in a deadlock the first time `casatasks` is imported. Note that we use ``python -c "import casampi.private.start_mpi; import casashell.__main__"`` instead of ``python -m casashell`` so that `start_mpi` runs before `casatasks`_ is imported. 
  the first time `casatasks`_ is imported in a MPI server process, it will attempt to start a new MPI environment, leading to a deadlock situation.


.. admonition:: Running a parallel CASA session from macOS

  - A parallel Pipeline data processing session might hang on macOS at the completion of the job due to lingering `casaplotms.app` sub-processes. 
    This behavior appears to be different from Linux, potentially caused by the fact that each ``casaplotms`` process spawned from a MPIserver process runs as a macOS "app".
    Although this doesn’t affect the data processing, to ensure a clean exit, one might need to use the following snippet at the end of your Python job script:

    .. code-block:: python

      def close_plotms_on_mpiservers():
          try:
              from casampi.MPIEnvironment import MPIEnvironment
              from casampi.MPICommandClient import MPICommandClient
              client = MPICommandClient()
              mpi_server_list = MPIEnvironment.mpi_server_rank_list()
              client.push_command_request('from casaplotms import plotmstool', block=True,
                                          target_server=mpi_server_list)
              rs_list = client.push_command_request('plotmstool.__proc!=None', block=True,
                                                    target_server=mpi_server_list)
              servers_with_active_plotms = [rs['server'] for rs in rs_list if rs['ret']]
              if servers_with_active_plotms:
                  print(f'servers with active plotms instances: {servers_with_active_plotms}')
                  client.push_command_request('plotmstool.__proc.kill()', block=True,
                                              target_server=servers_with_active_plotms)
          except Exception:
              pass
        
      close_plotms_on_mpiservers()
    
    In addition, ``xvfb-run`` is not available on macOS, even if xvfb/X11 is installed; therefore, you may not be able to use it for headless sessions.
    Additionally, to complete a Pipeline processing session requiring ``casaplotms``, one must log in remotely with GUI access. The ``casaplotms`` GUI will appear in the desktop environment but cannot be forwarded via X11.


Useful shorthand
----------------

Useful aliases/shortcuts to emulate monolithic CASA executables:

.. code-block:: bash

  conda activate pipeline

  export casa_omp_num_threads=4
  export casa_mpi_nproc=4
  export TMPDIR=/tmp    
  
  export casa6_opts_custom='--nologger --log2term --agg'
  export mpirun_custom='mpirun -display-allocation -display-map -oversubscribe --mca btl_vader_single_copy_mechanism none --mca btl ^openib -x OMP_NUM_THREADS -x PYTHONNOUSERSITE'
  export xvfb_run_auto='xvfb-run -a' # Debian, Ubuntu, RedHat8, etc.

  alias casa6='PYTHONNOUSERSITE=1 OMP_NUM_THREADS=${casa_omp_num_threads} python -m casashell'
  alias casa6mpi='PYTHONNOUSERSITE=1 OMP_NUM_THREADS=1 ${mpirun_custom} -n ${casa_mpi_nproc} python -c "import casampi.private.start_mpi; import casashell.__main__"'

  # For Linux only, not applicable on macOS
  alias casa6_xvfb='PYTHONNOUSERSITE=1 OMP_NUM_THREADS=${casa_omp_num_threads} ${xvfb_run_auto} python -m casashell'
  alias casa6mpi_xvfb='PYTHONNOUSERSITE=1 OMP_NUM_THREADS=1 ${xvfb_run_auto} ${mpirun_custom} -n ${casa_mpi_nproc} python -c "import casampi.private.start_mpi; import casashell.__main__"'

For executing a headless parallel Pipeline processing session on Linux, one could try:

.. code-block:: bash
  
  casa6mpi_xvfb ${casa6_opts_custom} -c ../scripts/run_pltest.py

If you prefer running with an 8-core mpicasa session (1 client + 7 servers), you could do:

.. code-block:: bash
  
  casa_mpi_nproc=8 casa6mpi_xvfb ${casa6_opts_custom} -c ../scripts/run_pltest.py