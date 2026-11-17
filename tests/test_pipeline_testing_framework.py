"""
test_pipeline_testing_framework.py
============================

Unit tests for the PipelineTester framework logic.

Purpose
-------
Validate internal behaviors of the pipeline framework so that pipeline
tests can trust the scaffolding they run on.

Scope covered here
------------------
- Versioned-results file selection
  * `_pick_results_file(...)`: parses candidate filenames and chooses the best
    match for the **current** CASA/Pipeline versions.
  * `_results_file_heuristics(...)`: rejects candidates that exceed running
    versions, then prefers the closest not-greater versions.
- CLI options propagation
  * Ensures `--compare-only` and `--remove-workdir` options are read from
    pytest and applied to a `PipelineTester` instance.
- Filename regex correctness
  * Confirms patterns extract versions from names like:
    `...casa-<X.Y.Z[-build]>-pipeline-<YYYY.M.m.p>`
- Weblog rendering failure detection
  * `weblog_rendering_failures(...)`: reads timetracker database to identify
    stages where weblog rendering failed with 'abnormal exit' state.
  * Integration with `__do_sanity_checks()`: ensures tests fail when weblog
    rendering failures are detected.

Out of scope
------------
- Actual pipeline execution (PPR/reducer), CASA tools, filesystem side effects.
  Those are covered by component/regression suites.

Expected filename patterns
--------------------------
- CASA:     `casa-6.5.1-15`  (dash is allowed; internally compared as dots)
- Pipeline: `pipeline-2023.1.0.8`

How to run
----------
Directly call file:
    python3 -m pytest -vv <repo root>/tests/test_pipeline_testing_framework.py

Or as part of the unit suite:
    python3 -m pytest -vv -m 'not regression and not component' '<repo root>'

Notes for contributors
----------------------
- To add new selection cases, include representative filenames in the
  `reference_files` lists or expand `reference_dict` with parsed versions.
- Environment versions are pinned with `unittest.mock.patch`:
  * `pipeline.environment.casa_version_string`
  * `pipeline.environment.pipeline_revision`
  Keep new tests deterministic by patching these accordingly.
- If you change filename patterns or selection rules in
  `PipelineTester`, update tests here first to codify the intended behavior.
- To simulate weblog rendering failures in integration tests, set
  `SIMULATE_WEBLOG_FAILURE` to comma-separated stage numbers.
  A test-only wrapper installed from `conftest.py` raises from renderer
  `render()` for those stages. The `htmlrenderer` catches this and emits a
  `WebLogStageRenderingAbnormalExitEvent`, which the timetracker records with
  state='abnormal exit'. This is what the failure detection mechanism checks.
"""
from __future__ import annotations

import collections
import datetime
import os
import shelve
import tempfile
import unittest
from typing import TYPE_CHECKING
from unittest import mock

import packaging
import pytest

from pipeline.infrastructure.renderer import regression
from tests.testing_utils import PipelineTester

if TYPE_CHECKING:
    from pytest import Config, FixtureRequest


# ExecutionState namedtuple matching the one in timetracker module
ExecutionState = collections.namedtuple('ExecutionState', ['stage', 'start', 'end', 'state'])


@pytest.fixture(autouse=True)
def _isolate_testcase_tmpdir(request: FixtureRequest, pytestconfig: Config):
    inst = getattr(request, "instance", None)
    if isinstance(inst, unittest.TestCase):
        inst.compare_only = pytestconfig.getoption("--compare-only", False)
        inst.remove_workdir = pytestconfig.getoption("--remove-workdir", False)
        inst._tmpdir = tempfile.mkdtemp(prefix="pltest_")
        inst.pipeline = PipelineTester(
            visname=["test_results"],
            recipe="test_procedure.xml",
            output_dir=inst._tmpdir,
        )


class TestPipelineTester(unittest.TestCase):

    @mock.patch("pipeline.environment.casa_version_string", "6.5.1.15")
    @mock.patch("pipeline.environment.pipeline_revision", "2023.1.0.8")
    def test_pick_results_file_valid_cases(self) -> None:
        """Tests that _pick_results_file correctly extracts and selects the best matching file."""
        reference_files = [
            "test_results_casa-6.4.0-20-pipeline-2022.4.0.1",
            "test_results_casa-6.6.0.8-pipeline-2023.2.0.140",  # Exceeds both current versions
            "test_results_casa-6.6.0.8-pipeline-2023.1.0.8",  # Exceeds current CASA version
            "test_results_casa-6.5.1-15-pipeline-2023.2.0.140",  # Exceeds current pipeline version
            "test_results_casa-6.5.1-15-pipeline-2023.1.0.8",  # Exact match
        ]

        best_match = self.pipeline._pick_results_file(reference_files)
        self.assertEqual(best_match, "test_results_casa-6.5.1-15-pipeline-2023.1.0.8")

    @mock.patch("pipeline.environment.casa_version_string", "6.5.1.15")
    @mock.patch("pipeline.environment.pipeline_revision", "2023.1.0.8")
    def test_pick_results_file_exceeding_versions(self) -> None:
        """Tests that files with exceeding versions are ignored."""
        reference_files = [
            "test_results_casa-6.7.0.0-pipeline-2023.1.0.8",  # CASA version too high
            "test_results_casa-6.5.1-15-pipeline-2023.3.0.1",  # Pipeline version too high
        ]

        best_match = self.pipeline._pick_results_file(reference_files)
        self.assertIsNone(best_match)

    @mock.patch("pipeline.environment.casa_version_string", "6.5.1.15")
    @mock.patch("pipeline.environment.pipeline_revision", "2023.1.0.8")
    def test_results_file_heuristics_selects_best_match(self) -> None:
        """Tests that _results_file_heuristics picks the closest match."""
        reference_dict = {
            "test_results_casa-6.5.0-12-pipeline-2023.1.0.1": {
                "CASA version": packaging.version.parse("6.5.0.12"),
                "Pipeline version": packaging.version.parse("2023.1.0.1"),
            },
            "test_results_casa-6.4.0.33-pipeline-2022.4.0.125": {
                "CASA version": packaging.version.parse("6.4.0.33"),
                "Pipeline version": packaging.version.parse("2022.4.0.125"),
            },
            "test_results_casa-6.5.1-15-pipeline-2023.1.0.4": {
                "CASA version": packaging.version.parse("6.5.1.15"),
                "Pipeline version": packaging.version.parse("2023.1.0.4"),
            },
        }

        best_match = self.pipeline._results_file_heuristics(reference_dict)
        self.assertEqual(best_match, "test_results_casa-6.5.1-15-pipeline-2023.1.0.4")

    def test_compare_only_option(self) -> None:
        """Ensure compare-only option is set correctly."""
        self.assertEqual(self.pipeline.compare_only, self.compare_only)

    def test_regex_matching(self) -> None:
        """Tests that the regex correctly extracts CASA and Pipeline versions."""
        test_cases = [
            ("test_results_casa-6.5.0.5-pipeline-2023.1.0.20", "6.5.0.5", "2023.1.0.20"),
            ("test_results_casa-6.4.3-17-pipeline-2022.3.0.40", "6.4.3-17", "2022.3.0.40"),
            ("invalid_casa_pipeline-2021.1.0.12", None, "2021.1.0.12"),  # Missing CASA version
            ("invalid_casa-6.7.0.1-pipeline", "6.7.0.1", None),  # Missing pipeline version
            ("random_file.txt", None, None),  # No match
        ]

        for filename, expected_casa, expected_pipeline in test_cases:
            casa_match = self.pipeline.regex_casa_pattern.match(filename)
            pipeline_match = self.pipeline.regex_pipeline_pattern.match(filename)

            casa_version = casa_match.group(1) if casa_match else None
            pipeline_version = pipeline_match.group(1) if pipeline_match else None

            self.assertEqual(casa_version, expected_casa)
            self.assertEqual(pipeline_version, expected_pipeline)

    def test_remove_workdir_option(self):
        """Ensure remove_workdir option is set correctly."""
        self.assertEqual(self.pipeline.remove_workdir, self.remove_workdir)

    def test_remove_workdir(self):
        """Ensure workdir is properly removed given the right conditions."""
        workdir = self.pipeline.output_dir

        # If compare_only=True, the directory should never be created, so skip further checks
        if self.pipeline.compare_only:
            self.assertFalse(os.path.exists(workdir))
            return

        # Otherwise, verify the directory was created initially
        self.assertTrue(os.path.exists(workdir))

        # Run the cleanup logic
        self.pipeline._cleanup()

        # If remove_workdir=True, the directory should be deleted after instantiation
        if self.pipeline.remove_workdir:
            self.assertFalse(os.path.exists(workdir))  # Workdir should be removed
        else:
            self.assertTrue(os.path.exists(workdir))  # Workdir should still exist


class TestWeblogRenderingFailureDetection(unittest.TestCase):
    """Unit tests for weblog rendering failure detection in regression testing."""

    def setUp(self):
        """Create a temporary directory for test databases."""
        self.tmpdir = tempfile.mkdtemp(prefix='weblog_test_')

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        if os.path.exists(self.tmpdir):
            shutil.rmtree(self.tmpdir)

    def test_weblog_rendering_failures_no_database(self):
        """Test that function returns empty list when timetracker database doesn't exist."""
        # Create a mock context with non-existent database
        mock_context = mock.Mock()
        mock_context.output_dir = self.tmpdir
        mock_context.name = 'nonexistent_context'

        failed_stages = regression.weblog_rendering_failures(mock_context)

        self.assertEqual(failed_stages, [])
        self.assertIsInstance(failed_stages, list)

    def test_weblog_rendering_failures_empty_database(self):
        """Test that function returns empty list when database has no weblog data."""
        # Create a mock context
        mock_context = mock.Mock()
        mock_context.output_dir = self.tmpdir
        mock_context.name = 'test_context'

        # Create an empty timetracker database
        db_path = os.path.join(self.tmpdir, 'test_context.timetracker')
        with shelve.open(db_path) as db:
            db['tasks'] = {}
            db['results'] = {}
            # No weblog key

        failed_stages = regression.weblog_rendering_failures(mock_context)

        self.assertEqual(failed_stages, [])

    def test_weblog_rendering_failures_all_successful(self):
        """Test that function returns empty list when all weblog renders succeed."""
        mock_context = mock.Mock()
        mock_context.output_dir = self.tmpdir
        mock_context.name = 'test_context'

        # Create timetracker database with successful weblog renders
        db_path = os.path.join(self.tmpdir, 'test_context.timetracker')
        now = datetime.datetime.now(datetime.timezone.utc)

        with shelve.open(db_path) as db:
            db['weblog'] = {
                1: ExecutionState(stage=1, start=now, end=now, state='complete'),
                2: ExecutionState(stage=2, start=now, end=now, state='complete'),
                3: ExecutionState(stage=3, start=now, end=now, state='complete'),
            }

        failed_stages = regression.weblog_rendering_failures(mock_context)

        self.assertEqual(failed_stages, [])

    def test_weblog_rendering_failures_some_failed(self):
        """Test that function correctly identifies failed weblog renders."""
        mock_context = mock.Mock()
        mock_context.output_dir = self.tmpdir
        mock_context.name = 'test_context'

        # Create timetracker database with mixed success/failure
        db_path = os.path.join(self.tmpdir, 'test_context.timetracker')
        now = datetime.datetime.now(datetime.timezone.utc)

        with shelve.open(db_path) as db:
            db['weblog'] = {
                1: ExecutionState(stage=1, start=now, end=now, state='complete'),
                2: ExecutionState(stage=2, start=now, end=now, state='abnormal exit'),
                3: ExecutionState(stage=3, start=now, end=now, state='complete'),
                5: ExecutionState(stage=5, start=now, end=now, state='abnormal exit'),
                7: ExecutionState(stage=7, start=now, end=now, state='abnormal exit'),
            }

        failed_stages = regression.weblog_rendering_failures(mock_context)

        # Should return sorted list of failed stage numbers
        self.assertEqual(failed_stages, [2, 5, 7])

    def test_weblog_rendering_failures_returns_sorted(self):
        """Test that function returns stage numbers in sorted order."""
        mock_context = mock.Mock()
        mock_context.output_dir = self.tmpdir
        mock_context.name = 'test_context'

        # Create database with unsorted failed stages
        db_path = os.path.join(self.tmpdir, 'test_context.timetracker')
        now = datetime.datetime.now(datetime.timezone.utc)

        with shelve.open(db_path) as db:
            db['weblog'] = {
                10: ExecutionState(stage=10, start=now, end=now, state='abnormal exit'),
                3: ExecutionState(stage=3, start=now, end=now, state='abnormal exit'),
                7: ExecutionState(stage=7, start=now, end=now, state='abnormal exit'),
            }

        failed_stages = regression.weblog_rendering_failures(mock_context)

        self.assertEqual(failed_stages, [3, 7, 10])

    @mock.patch('pipeline.infrastructure.renderer.regression.errorexit_present', return_value=False)
    @mock.patch('pipeline.infrastructure.renderer.regression.manifest_present', return_value=True)
    @mock.patch('pipeline.infrastructure.renderer.regression.missing_directories', return_value=[])
    @mock.patch('pipeline.infrastructure.launcher.Pipeline')
    @mock.patch('tests.testing_utils.pytest.fail')
    def test_sanity_check_fails_on_weblog_errors(self, mock_fail, mock_pipeline,
                                                   mock_missing_dirs, mock_manifest, mock_errorexit):
        """Test that __do_sanity_checks raises pytest.fail when weblog rendering fails."""
        # Create a PipelineTester instance
        tester = PipelineTester(
            visname=['test.ms'],
            mode='regression',
            recipe='test.xml',
            output_dir=self.tmpdir,
        )

        # Create mock context with failed weblog stages
        mock_context = mock.Mock()
        mock_context.output_dir = self.tmpdir
        mock_context.name = 'test_context'
        mock_context.products_dir = self.tmpdir
        mock_pipeline.return_value.context = mock_context

        # Create timetracker database with failed stages
        db_path = os.path.join(self.tmpdir, f'{mock_context.name}.timetracker')
        now = datetime.datetime.now(datetime.timezone.utc)

        with shelve.open(db_path) as db:
            db['weblog'] = {
                2: ExecutionState(stage=2, start=now, end=now, state='abnormal exit'),
                5: ExecutionState(stage=5, start=now, end=now, state='abnormal exit'),
            }

        # Call the sanity check method
        tester._PipelineTester__do_sanity_checks()

        # Verify pytest.fail was called with the right message
        mock_fail.assert_called()
        call_args = mock_fail.call_args[0][0]
        self.assertIn('Weblog rendering failed', call_args)
        self.assertIn('2', call_args)
        self.assertIn('5', call_args)
