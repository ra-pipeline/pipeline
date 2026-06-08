.. _unit_testing:

==================
Unit Testing Guide
==================

Overview
========

Unit tests are small, focused tests that validate individual functions, classes, or modules 
in isolation. These tests are scattered throughout the pipeline codebase, typically located 
near the code they test. Unit tests execute quickly and don't require external data files or 
full pipeline execution.

Purpose
=======

Unit tests serve several important purposes:

* Validate individual functions and methods work correctly
* Test edge cases and error handling
* Document expected behavior through test examples
* Enable safe refactoring by catching regressions
* Run quickly as part of development workflow

Unit Test Organization
======================

Unlike regression and component tests which are centralized in the ``tests/`` directory, unit 
tests are distributed throughout the codebase, typically co-located with the code they test.

Naming Convention
-----------------

Unit test files follow one of these naming patterns:

* ``<module_name>_test.py`` - Test file for ``<module_name>.py``
* ``test_<module_name>.py`` - Alternative pattern (less common in this codebase)

For example:

* ``contfilehandler_test.py`` - Tests for ``contfilehandler.py``
* ``utils_test.py`` - Tests for ``utils.py``
* ``daskhelpers_test.py`` - Tests for ``daskhelpers.py``

Common Locations
----------------

Unit tests can be found throughout the pipeline code:

* ``pipeline/infrastructure/`` - Infrastructure and utilities tests

  * ``contfilehandler_test.py`` - Continuum file handling
  * ``daskhelpers_test.py`` - Dask parallelization helpers
  * ``executeppr_test.py`` - PPR execution
  * ``utils_test.py`` - General utilities

* ``pipeline/infrastructure/utils/`` - Utility function tests

  * ``conversion_test.py`` - Unit conversions
  * ``imaging_test.py`` - Imaging utilities
  * ``math_test.py`` - Mathematical functions
  * ``sorting_test.py`` - Sorting algorithms
  * ``positioncorrection_test.py`` - Position corrections
  * ``casa_data_test.py`` - CASA data access
  * ``weblog_test.py`` - Weblog generation

* ``pipeline/infrastructure/displays/`` - Display and plotting tests

  * ``plotpointings_test.py`` - Pointing plots

* ``pipeline/hifa/tasks/`` - ALMA interferometry task tests

  * ``applycal/mswrapper_test.py`` - MS wrapper utilities
  * ``applycal/ampphase_vs_freq_qa_test.py`` - QA scoring
  * ``flagging/flagdeteralma_test.py`` - Flagging determinism
  * ``importdata/almaimportdata_test.py`` - Data import

* ``pipeline/hifv/`` - VLA task and heuristic tests

  * ``heuristics/standard_test.py`` - Standard heuristics
  * ``heuristics/uvrange_test.py`` - UV range calculations
  * ``tasks/testBPdcals/testBPdcals.py`` - Bandpass calibrator tests
  * ``tasks/fluxscale/testgainsdisplay.py`` - Gain display tests

* ``pipeline/hsd/`` - Single-dish tests

  * ``tasks/baseline/detection_test.py`` - Baseline detection
  * ``tasks/baseline/worker_test.py`` - Baseline fitting workers
  * ``tasks/atmcor/atmcor_test.py`` - Atmospheric correction
  * ``tasks/common/utils_test.py`` - SD utilities
  * ``tasks/common/observatory_policy_test.py`` - Observatory policies
  * ``tasks/common/direction_utils_test.py`` - Direction utilities
  * ``tasks/common/display_test.py`` - Display utilities
  * ``tasks/common/flagcmd_util_test.py`` - Flag command utilities
  * ``heuristics/grouping2_test.py`` - Data grouping
  * ``heuristics/pointing_outlier_test.py`` - Pointing outlier detection
  * ``heuristics/rasterscan_test.py`` - Raster scan patterns

* ``pipeline/h/`` - Common task and heuristic tests

  * ``heuristics/importdata_test.py`` - Import data heuristics
  * ``heuristics/linefinder_test.py`` - Line finding
  * ``tasks/common/atmutil_test.py`` - Atmospheric utilities

* ``pipeline/qa/`` - QA framework tests

  * ``scorecalculator_test.py`` - QA score calculations

* ``pipeline/recipes/`` - Recipe tests

  * ``recipe_converter_test.py`` - Recipe conversion
  * ``tests/test_hifv.py`` - VLA recipe tests
  * ``tests/test_hifv_contimage.py`` - VLA continuum imaging recipe
  * ``tests/test_hifv_calimage_cont.py`` - VLA calibration+imaging recipe

Writing Unit Tests
==================

Unit tests in the pipeline use pytest as the test framework.

Basic Structure
---------------

A typical unit test file:

.. code-block:: python

    import pytest
    from module_under_test import function_to_test

    def test_basic_functionality():
        '''Test that function works for normal inputs.'''
        result = function_to_test(input_value)
        assert result == expected_value

    def test_edge_case():
        '''Test boundary condition.'''
        result = function_to_test(edge_case_input)
        assert result == expected_edge_case_value

    def test_error_handling():
        '''Test that appropriate errors are raised.'''
        with pytest.raises(ValueError):
            function_to_test(invalid_input)

Using Parametrized Tests
-------------------------

For testing multiple cases, use ``pytest.mark.parametrize``:

.. code-block:: python

    import pytest

    test_cases = [
        ('input1', 'expected1'),
        ('input2', 'expected2'),
        ('input3', 'expected3'),
    ]

    @pytest.mark.parametrize('input_val, expected', test_cases)
    def test_multiple_cases(input_val, expected):
        '''Test function with multiple input/output pairs.'''
        result = function_to_test(input_val)
        assert result == expected

Using Mocks
-----------

For isolating code from dependencies, use ``unittest.mock``:

.. code-block:: python

    from unittest.mock import Mock, patch

    def test_with_mock():
        '''Test function with mocked dependency.'''
        mock_dependency = Mock()
        mock_dependency.method.return_value = 'mocked_value'
        
        result = function_using_dependency(mock_dependency)
        assert result == expected_result
        mock_dependency.method.assert_called_once()

    @patch('module.external_function')
    def test_with_patch(mock_function):
        '''Test with patched external function.'''
        mock_function.return_value = 'patched_value'
        
        result = function_calling_external()
        assert result == expected_result

Test Fixtures
-------------

Use fixtures for setup and teardown:

.. code-block:: python

    import pytest

    @pytest.fixture
    def sample_data():
        '''Provide sample data for tests.'''
        return {'key': 'value', 'number': 42}

    def test_using_fixture(sample_data):
        '''Test using fixture data.'''
        assert sample_data['number'] == 42

Running Unit Tests
==================

Running All Unit Tests
----------------------

Run all unit tests in the repository::

    pytest pipeline/

Run unit tests in a specific directory::

    pytest pipeline/infrastructure/

Run a specific test file::

    pytest pipeline/infrastructure/contfilehandler_test.py

Running Specific Tests
----------------------

Run a specific test function::

    pytest pipeline/infrastructure/contfilehandler_test.py::test_cont_ranges

Run tests matching a pattern::

    pytest -k "test_cont" pipeline/infrastructure/

Useful Options
--------------

* ``-v`` or ``-vv`` - Verbose output
* ``-x`` - Stop after first failure
* ``--tb=short`` - Shorter traceback format
* ``--tb=line`` - One-line traceback
* ``-l`` - Show local variables in tracebacks
* ``--pdb`` - Drop into debugger on failures
* ``--maxfail=N`` - Stop after N failures

Example::

    pytest -vv -x --tb=short pipeline/infrastructure/utils/

Excluding Unit Tests from Test Runs
====================================

To run only regression and component tests (excluding unit tests)::

    pytest tests/

To run unit tests only (excluding regression/component tests)::

    pytest pipeline/

To explicitly exclude unit tests when running from repository root::

    pytest tests/ --ignore=pipeline/

Best Practices
==============

Test Organization
-----------------

* Place test files in the same directory as the code they test
* Use descriptive test function names that describe what is being tested
* Group related tests in the same file
* Use test classes to group related test methods

Test Independence
-----------------

* Each test should be independent and not rely on other tests
* Use fixtures for shared setup, not global state
* Clean up any resources created during tests
* Don't assume test execution order

Test Coverage
-------------

* Test normal operation (happy path)
* Test edge cases and boundary conditions
* Test error conditions and exception handling
* Test with various input types when applicable

Documentation
-------------

* Use docstrings to describe what each test validates
* Include context about why edge cases are important
* Document any tricky setup or mock behavior

Performance
-----------

* Keep unit tests fast (milliseconds, not seconds)
* Mock external dependencies (files, network, CASA tools when possible)
* Use small, synthetic test data rather than large real datasets
* Reserve large data and slow operations for regression tests

Assertions
----------

* Use descriptive assertion messages when helpful
* Test one concept per test function
* Use appropriate pytest assertion helpers (``approx`` for floats, etc.)
* Prefer specific assertions over generic ones

Example of well-structured unit tests::

    import pytest
    from pipeline.infrastructure import contfilehandler

    class TestContFileHandler:
        '''Tests for ContFileHandler class.'''

        @pytest.fixture
        def handler(self):
            '''Create handler with test data file.'''
            return contfilehandler.ContFileHandler('test_cont.dat')

        def test_cont_ranges_basic(self, handler):
            '''Test that cont_ranges returns expected structure.'''
            ranges = handler.cont_ranges
            assert isinstance(ranges, dict)
            assert 'fields' in ranges

        def test_to_topo_conversion(self, handler):
            '''Test frequency conversion to TOPO frame.'''
            selection = '214.5~215.5GHz LSRK'
            result = handler.to_topo(selection, ['test.ms'], ['0'], 3, mock_run)
            
            assert result[0][0].endswith('TOPO')
            assert len(result[1]) > 0  # Channel ranges

        def test_invalid_file_raises_error(self):
            '''Test that missing file raises appropriate error.'''
            with pytest.raises(FileNotFoundError):
                contfilehandler.ContFileHandler('nonexistent.dat')

Continuous Integration
======================

Unit tests are typically run as part of the CI/CD pipeline:

* Executed on every commit to development branches
* Must pass before code can be merged
* Provide fast feedback to developers
* Complement slower regression and component tests

.. seealso::

   * :ref:`automated_testing` - Regression and component testing guide
   * `pytest documentation <https://docs.pytest.org/>`_ - Official pytest docs
