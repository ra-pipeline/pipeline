.. _testing:

===============
Testing Guide
===============

The pipeline uses a comprehensive testing strategy that includes automated regression tests, 
component tests, and unit tests. Each type of test serves a specific purpose in ensuring 
code quality and preventing regressions.

Documentation Contents
======================

.. toctree::
   :maxdepth: 2

   automated_testing
   unit_testing

Test Types Overview
===================

Automated Tests (Regression & Component)
----------------------------------------

These tests validate pipeline behavior using real or realistic datasets and compare results 
against known expected values. They catch regressions in pipeline processing and ensure 
end-to-end functionality.

* **Location**: ``tests/`` directory
* **Characteristics**: Slower, data-dependent, comprehensive
* **Purpose**: Validate complete workflows and prevent regressions

See: :ref:`automated_testing`

Unit Tests
----------

Small, focused tests that validate individual functions and classes in isolation. They 
execute quickly without requiring large datasets or full pipeline execution.

* **Location**: Throughout ``pipeline/`` codebase
* **Characteristics**: Fast, isolated, focused
* **Purpose**: Validate individual components and enable safe refactoring

See: :ref:`unit_testing`

Quick Start
===========

Running All Tests
-----------------

Run fast automated tests (regression + component, excluding slow)::

    pytest tests/

Run all tests including slow regression tests::

    pytest --longtests tests/

Run unit tests only::

    pytest pipeline/

Run everything::

    pytest --longtests

Common Workflows
----------------

**During Development** - Run relevant unit tests frequently::

    pytest pipeline/infrastructure/utils/math_test.py -v

**Before Committing** - Run related automated tests::

    pytest tests/component/ -v

**Pre-Release Validation** - Run full test suite::

    pytest --longtests --junitxml=results.xml

Test Organization
=================

.. code-block:: text

    repository/
    ├── tests/                          # Automated tests (centralized)
    │   ├── component/                  # Component tests
    │   ├── regression/                 # Regression tests
    │   │   ├── fast/                   # Quick regression tests
    │   │   └── slow/                   # Longer regression tests
    │   ├── testing_utils.py            # PipelineTester framework
    │   └── test_pipeline_testing_framework.py
    │
    └── pipeline/                       # Unit tests (distributed)
        ├── infrastructure/
        │   ├── module.py
        │   └── module_test.py          # Unit tests for module.py
        ├── hifa/
        │   └── tasks/
        │       └── task/
        │           ├── task.py
        │           └── task_test.py
        └── ...

Related Documentation
=====================

* :doc:`../develdocmd/pipeline_tests` - Additional testing information
* :doc:`../develdocmd/DataType_Testing` - DataType-specific tests

