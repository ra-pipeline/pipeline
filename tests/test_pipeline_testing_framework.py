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
"""
from __future__ import annotations

import os
import tempfile
import unittest
from typing import TYPE_CHECKING
from unittest import mock

import packaging
import pytest

from tests.testing_utils import PipelineTester

if TYPE_CHECKING:
    from pytest import Config, FixtureRequest


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
