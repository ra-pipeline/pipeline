"""Unit tests for the Prefect adapter module.

These tests exercise the adapter's feature-flag logic, the lightweight
``TaskResultSummary`` dataclass, and the task/flow delegation wrappers.
They are designed to run **with or without** the ``prefect`` package
installed.
"""

import dataclasses
import os
import unittest
from unittest import mock


class TestIsPrefectEnabled(unittest.TestCase):
    """Tests for ``is_prefect_enabled()``."""

    def _get_target(self):
        """Import inside test so mocks can affect module-level state."""
        from pipeline.infrastructure.prefect_adapter import is_prefect_enabled

        return is_prefect_enabled

    def test_disabled_when_env_not_set(self):
        """Returns False when no env var and config disabled."""
        with mock.patch.dict(os.environ, {}, clear=True):
            # Ensure env var is absent.
            os.environ.pop('PIPELINE_USE_PREFECT', None)
            result = self._get_target()()
            # Without prefect installed or the env var, should be False.
            self.assertFalse(result)

    def test_enabled_when_env_var_true(self):
        """Returns True when PIPELINE_USE_PREFECT=1 and prefect is importable."""
        with mock.patch.dict(os.environ, {'PIPELINE_USE_PREFECT': '1'}):
            from pipeline.infrastructure import prefect_adapter

            if not prefect_adapter._PREFECT_AVAILABLE:
                self.skipTest('prefect not installed')
            result = self._get_target()()
            self.assertTrue(result)

    def test_disabled_when_env_var_false(self):
        """Returns False when PIPELINE_USE_PREFECT=0."""
        with mock.patch.dict(os.environ, {'PIPELINE_USE_PREFECT': '0'}):
            result = self._get_target()()
            self.assertFalse(result)

    def test_disabled_when_prefect_not_available(self):
        """Returns False when _PREFECT_AVAILABLE is False."""
        from pipeline.infrastructure import prefect_adapter

        original = prefect_adapter._PREFECT_AVAILABLE
        try:
            prefect_adapter._PREFECT_AVAILABLE = False
            result = self._get_target()()
            self.assertFalse(result)
        finally:
            prefect_adapter._PREFECT_AVAILABLE = original


class TestTaskResultSummary(unittest.TestCase):
    """Tests for the ``TaskResultSummary`` dataclass."""

    def test_default_values(self):
        from pipeline.infrastructure.prefect_adapter import TaskResultSummary

        summary = TaskResultSummary()
        self.assertIsNone(summary.stage_number)
        self.assertEqual(summary.task_name, '')
        self.assertTrue(summary.success)
        self.assertEqual(summary.error_message, '')
        self.assertAlmostEqual(summary.duration_seconds, 0.0)

    def test_frozen(self):
        from pipeline.infrastructure.prefect_adapter import TaskResultSummary

        summary = TaskResultSummary(task_name='hifa_bandpass')
        with self.assertRaises(dataclasses.FrozenInstanceError):
            summary.task_name = 'other'

    def test_serialization_roundtrip(self):
        """TaskResultSummary should be dict-serializable (JSON-safe)."""
        from pipeline.infrastructure.prefect_adapter import TaskResultSummary

        summary = TaskResultSummary(
            stage_number=5,
            task_name='hifa_bandpass',
            success=True,
            duration_seconds=12.345,
        )
        as_dict = dataclasses.asdict(summary)
        restored = TaskResultSummary(**as_dict)
        self.assertEqual(summary, restored)

    def test_failed_summary(self):
        from pipeline.infrastructure.prefect_adapter import TaskResultSummary

        summary = TaskResultSummary(
            task_name='hifa_flagdata',
            success=False,
            error_message='Something went wrong',
        )
        self.assertFalse(summary.success)
        self.assertIn('went wrong', summary.error_message)


class TestExecutePipelineTask(unittest.TestCase):
    """Tests for ``_execute_pipeline_task()``."""

    @mock.patch('pipeline.cli.get_pipeline_task_with_name')
    @mock.patch('pipeline.infrastructure.utils.get_tracebacks', return_value=[])
    def test_successful_execution(self, mock_tracebacks, mock_get_task):
        """A successful task returns a summary with success=True."""
        from pipeline.infrastructure.prefect_adapter import _execute_pipeline_task

        mock_result = mock.MagicMock()
        mock_result.stage_number = 3
        mock_task_fn = mock.MagicMock(return_value=mock_result)
        mock_get_task.return_value = mock_task_fn

        summary = _execute_pipeline_task('hifa_bandpass', {'refant': 'DV01'})

        mock_get_task.assert_called_once_with('hifa_bandpass')
        mock_task_fn.assert_called_once_with(refant='DV01')
        self.assertTrue(summary.success)
        self.assertEqual(summary.stage_number, 3)
        self.assertEqual(summary.task_name, 'hifa_bandpass')
        self.assertGreater(summary.duration_seconds, 0.0)

    @mock.patch('pipeline.cli.get_pipeline_task_with_name')
    def test_unhandled_exception(self, mock_get_task):
        """An exception in the task returns a summary with success=False."""
        from pipeline.infrastructure.prefect_adapter import _execute_pipeline_task

        mock_get_task.return_value = mock.MagicMock(side_effect=RuntimeError('boom'))

        summary = _execute_pipeline_task('hifa_badtask', {})

        self.assertFalse(summary.success)
        self.assertIn('boom', summary.error_message)

    @mock.patch('pipeline.cli.get_pipeline_task_with_name')
    @mock.patch('pipeline.infrastructure.utils.get_tracebacks', return_value=['traceback line 1'])
    def test_pipeline_exception_on_tracebacks(self, mock_tracebacks, mock_get_task):
        """When tracebacks are present, PipelineException is raised."""
        from pipeline.infrastructure.prefect_adapter import _execute_pipeline_task
        from pipeline.infrastructure.exceptions import PipelineException

        mock_result = mock.MagicMock()
        mock_result.stage_number = 2
        mock_get_task.return_value = mock.MagicMock(return_value=mock_result)

        with self.assertRaises(PipelineException):
            _execute_pipeline_task('hifa_flagdata', {})


if __name__ == '__main__':
    unittest.main()
