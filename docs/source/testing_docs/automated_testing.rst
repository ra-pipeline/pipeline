.. _automated_testing:

==================================
Automated Testing Guide
==================================

.. |ptester| replace:: ``PipelineTester``
.. |testdata_repo| replace:: `pipeline-testdata <https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline-testdata/browse>`_
.. |testdata_repo_readme| replace:: `README <https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline-testdata/browse/readme.md>`_
.. |regression_py| replace:: ``infrastructure/renderer/regression.py``
.. |recipereducer| replace:: ``recipereducer.py``
.. |component_test| replace:: ``tests/component/component_test.py``

Overview
========

There is a great need within our development process to have easy to create, regular, 
automatic regression and component tests of partial or full pipeline recipes. This guide 
describes how to create new automated tests using the |ptester| framework. These 
tests run on 'main' each evening (Charlottesville time) if a change is made to either 
pipeline or CASA code. Because we want the tests to run within a daily build process, they 
should not run for more than a few hours total.

Test Types
==========

The pipeline testing framework supports two distinct test modes:

Regression Tests
----------------

Regression tests validate complete pipeline recipes or PPR (Pipeline Processing Request) 
executions. These tests ensure that the full end-to-end pipeline processing produces 
expected results and catches regressions in pipeline behavior.

* Located in ``tests/regression/`` directory
* Organized into ``fast/`` and ``slow/`` subdirectories
* Run complete recipes using either PPR files or recipe XML files
* Compare comprehensive output metrics against versioned expected results

Component Tests
---------------

Component tests validate individual pipeline tasks or small sequences of tasks in isolation. 
These tests focus on specific functionality and are typically faster than full regression 
tests.

* Located in ``tests/component/`` directory
* Execute specific tasks with controlled inputs
* Test edge cases and specific functionality
* Can validate task behavior without running the entire pipeline

Example component test structure::

    tasks = [
        ('hifa_importdata', {'vis': 'path/to/data.ms'}),
        ('hif_selfcal', {}),
        ('hif_selfcal', {'restore_only': True}),
    ]

    pt = PipelineTester(
        visname=['data.ms'],
        mode='component',
        tasks=tasks,
        output_dir='test_output',
        expectedoutput_dir='pl-componenttest/test_name',
    )

    pt.run()

Test Organization
=================

The test suite is organized hierarchically:

* ``tests/`` - Root test directory

  * ``component/`` - Component tests

    * ``component_test.py`` - Component test definitions

  * ``regression/`` - Regression tests

    * ``fast/`` - Quick regression tests (typically < 30 minutes)

      * ``alma_if_fast_test.py`` - ALMA interferometry fast tests
      * ``alma_sd_fast_test.py`` - ALMA single-dish fast tests
      * ``vla_fast_test.py`` - VLA fast tests
      * ``vlass_fast_test.py`` - VLASS fast tests
      * ``nobeyama_sd_fast_test.py`` - Nobeyama single-dish fast tests

    * ``slow/`` - Longer regression tests (typically > 30 minutes)

      * ``alma_if_slow_test.py`` - ALMA interferometry slow tests
      * ``alma_sd_slow_test.py`` - ALMA single-dish slow tests
      * ``vla_slow_test.py`` - VLA slow tests
      * ``vlass_slow_test.py`` - VLASS slow tests

  * ``testing_utils.py`` - Core |ptester| framework
  * ``test_pipeline_testing_framework.py`` - Unit tests for the framework itself

Pytest Markers
==============

Tests are automatically marked based on their location and can also have manual markers. 
Key markers include:

* ``regression`` - Regression tests (auto-applied to tests in ``regression/``)
* ``component`` - Component tests (auto-applied to tests in ``component/``)
* ``fast`` - Fast-running tests (auto-applied to tests in ``fast/`` subdirectories)
* ``slow`` - Slow-running tests (auto-applied to tests in ``slow/`` subdirectories, requires ``--longtests`` flag)
* ``seven`` - 7m array tests
* ``twelve`` - 12m array tests
* ``importdata`` - Tests involving data import
* ``selfcal`` - Tests involving self-calibration
* ``makeimages`` - Tests involving imaging

To run tests with specific markers::

    pytest -m "fast and alma"
    pytest -m "regression and not slow"
    pytest -m "component and selfcal"

Inputs
======

To write a Pipeline regression test requires the following inputs to be available in the 
|testdata_repo| repository. *Before adding new data to the repository, please review the |testdata_repo_readme|.*

Required inputs:

* Input SDM(s) or MS(s)
* Expected test output
* PPR (optional)

These inputs should be stored in a dataset-specific directory in the ``pl-regressiontest/`` 
subdirectory of the |testdata_repo| git repo. Each of these files can have any name, 
but in the interest of clarity you should name using the following convention for expected 
results::

    pl-regressiontest/
    `-- <dataset basename>
        | -- <dataset basename>.<release version>.results.txt

For example::

    pl-regressiontest/
    `-- uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small
        |-- PPR.xml
        |-- uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.casa-6.1.1-15-pipeline-2020.1.0.40.casa.log
        |-- uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.casa-6.1.1-15-pipeline-2020.1.0.40.results.txt
        `-- uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.casa-6.1.3-2-pipeline-2021.1.1.6.results.txt

Input SDM/MS
------------

Whenever possible, we should use the smallest, fastest running test datasets we can find. 
The first place to look is in the |testdata_repo| repository to see if it is already 
available. The next place to look would be our list of Small verification test datasets.

If the desired test dataset is already stored elsewhere in the repository, there is no need 
to add another. For example::

    pl-unittest/
    |-- uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.ms

To add a new dataset, add a directory and data to ``pl-regressiontest/`` or ``pl-componenttest/`` 
in the testdata repository, using the instructions in the repository |testdata_repo_readme|.

Expected Output
---------------

Expected output should follow the format generated by 
``infrastructure/renderer/regression.py``, with the addition of ``:::`` and an optional 
relative tolerance value at the end of the line. For example::

    s15.hifa_gfluxscaleflag.uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.num_rows_flagged.after=268048:::
    s16.hifa_gfluxscale.uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.field_0.spw_0.I=2.2542400978094923:::1e-6

If no tolerance is supplied, the test output will be compared with expected output using a 
default tolerance set in the |ptester|.run() method; currently ``1e-7``.

PPR (Optional)
--------------

If a PPR is supplied, the test framework will use ``executeppr`` for ALMA or 
``executevlappr`` for VLA. If no PPR is supplied, the tests will use |recipereducer| 
and a given recipe. The test runner will create and clean up the necessary directory 
structures to run the test.

Adding a New Regression Test
=============================

Regression tests use the |ptester| framework with ``mode='regression'`` (the 
default). To create a new test, add the required data to the data repository and add a new 
function to the appropriate file in ``tests/regression/fast/`` or ``tests/regression/slow/``.

Basic Structure
---------------

Example regression test using a PPR::

    @pytest.mark.seven
    def test_uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small__PPR__regression():
        """Run ALMA cal+image regression on a small test dataset with a PPR file.

        PPR:                        pl-regressiontest/uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small/PPR.xml
        Dataset:                    uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.ms
        """
        ref_directory = 'pl-regressiontest/uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small'

        pt = PipelineTester(
            visname=['uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.ms'],
            ppr=f'{ref_directory}/PPR.xml',
            input_dir='pl-unittest',
            expectedoutput_dir=ref_directory,
        )

        pt.run()

Example regression test using a recipe::

    def test_dataset__recipe_name__regression():
        """Run test with recipe XML file.

        Recipe name:                procedure_hifa_image
        Dataset:                    uid___A002_Xef72bb_X9d29
        """
        ref_directory = 'pl-regressiontest/uid___A002_Xef72bb_X9d29'

        pt = PipelineTester(
            visname=['uid___A002_Xef72bb_X9d29'],
            recipe='procedure_hifa_image.xml',
            input_dir=ref_directory,
            expectedoutput_dir=ref_directory,
        )

        pt.run()

Adding a New Component Test
===========================

Component tests use the |ptester| framework with ``mode='component'`` and require 
a list of tasks to execute. Add new component tests to |component_test|.

Basic Structure
---------------

Example component test::

    @pytest.mark.importdata
    @pytest.mark.selfcal
    def test_dataset__task_sequence__component():
        """Run test of specific task sequence.

        Dataset(s):                 dataset_name.ms
        Task(s):                    hifa_importdata, hif_selfcal
        """
        data_dir = 'pl-unittest'
        visname = 'dataset_name.ms'
        tasks = [
            ('hifa_importdata', {'vis': casa_tools.utils.resolve(os.path.join(data_dir, visname)),
                                 'datacolumns': {'data': 'regcal_contline'}}),
            ('hif_selfcal', {}),
            ('hif_selfcal', {'restore_only': True}),
        ]

        pt = PipelineTester(
            visname=[visname],
            mode='component',
            tasks=tasks,
            output_dir='test_output_dir',
            expectedoutput_dir='pl-componenttest/test_name',
        )

        pt.run()

The ``tasks`` parameter is a list of tuples where each tuple contains:

1. The task name as a string (e.g., ``'hifa_importdata'``)
2. A dictionary of task parameters (can be empty: ``{}``)

Versioned Results Files
=======================

The |ptester| framework automatically selects the most appropriate expected results 
file based on the current CASA and Pipeline versions. This allows tests to maintain multiple 
versions of expected results as software evolves.

File Naming Convention
----------------------

Results files should follow this naming pattern::

    <dataset_name>.casa-<CASA_version>-pipeline-<Pipeline_version>.results.txt

Examples::

    uid___A002_Xc46ab2_X15ae.casa-6.5.1-15-pipeline-2023.1.0.8.results.txt
    uid___A002_Xc46ab2_X15ae.casa-6.6.0-21-pipeline-2024.1.0.12.results.txt

Version Selection Logic
-----------------------

When ``expectedoutput_dir`` is specified instead of ``expectedoutput_file``, the framework:

1. Scans the directory for all ``*.results.txt`` files
2. Parses CASA and Pipeline versions from filenames
3. Filters out files with versions exceeding the current running versions
4. Selects the file with versions closest to (but not exceeding) the current versions

This automatic selection ensures tests use the most relevant expected results without manual 
intervention when CASA or Pipeline versions change.

Adding New Values to Compare
=============================

To add new regression values to check, one needs to add to or modify a class in |regression_py|. 
For example, ``class FluxcalflagRegressionExtractor()``.

Running Tests Manually
======================

Setup
-----

To run these tests locally, you need to:

1. Check out the | repository
2. Configure CASA to find your test data by modifying ``~/.casa/config.py``::

    datapath = ['/path/to/pipeline-testdata']

3. Optionally, for larger test datasets, use the ``--data-directory`` option to specify an 
   alternate location

Running All Tests
-----------------

Run all fast tests (skips slow tests by default)::

    pytest tests/

Run all tests including slow tests::

    pytest --longtests tests/

Running Specific Test Categories
---------------------------------

Run only component tests::

    pytest tests/component/

Run only fast regression tests::

    pytest tests/regression/fast/

Run only ALMA interferometry tests::

    pytest tests/regression/fast/alma_if_fast_test.py

Running with Pytest Markers
---------------------------

Run only fast tests (auto-marked)::

    pytest -m fast

Run regression tests but skip slow ones::

    pytest -m "regression and not slow"

Run component tests with selfcal::

    pytest -m "component and selfcal"

Running Individual Tests
------------------------

Run a specific test by name::

    pytest tests/regression/fast/alma_if_fast_test.py::test_uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small__PPR__regression

Or using the shorter form::

    pytest -k "test_uid___A002_Xc46ab2_X15ae"

Useful Command-Line Options
---------------------------

* ``-v`` or ``-vv`` - Verbose output (use ``-vv`` for extra detail)
* ``--longtests`` - Include slow tests (required for tests marked as ``slow``)
* ``--compare-only`` - Skip pipeline execution, only compare against existing results
* ``--remove-workdir`` - Clean up working directories after tests complete
* ``--nologfile`` - Suppress CASA log file creation (keeps local repo clean)
* ``--junitxml=results.xml`` - Generate JUnit XML report
* ``-n <num>`` - Run tests in parallel using pytest-xdist (e.g., ``-n 4``)

Example with multiple options::

    pytest -vv --longtests --nologfile --junitxml=results.xml tests/regression/fast/

Compare-Only Mode
-----------------

If you have already run tests and want to re-evaluate results without re-running the 
pipeline::

    pytest --compare-only tests/regression/fast/

This is useful for:

* Tweaking comparison tolerances
* Updating expected results files
* Debugging test comparison logic

Test Results
============

Build success and failure is reported in Bamboo, and by email notification, but failure 
will not prevent a pre-release tarball from being published for download.

A successful test will show a passing status in Bamboo, while a failed test will include 
details about how your values differed from expected.

.. note::
   Originally created by Joseph Masters, last updated by Shawn Booth on Jan 27, 2026.
