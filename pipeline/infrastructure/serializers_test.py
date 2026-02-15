"""
Examples and tests for the results serialization framework.

This module demonstrates how to use the serialization framework to export
and inspect pipeline metadata without requiring full pickle deserialization.

Usage Examples:
    Basic metadata export:
        from pipeline.infrastructure.serializers import ResultMetadata, export_result_metadata
        metadata = ResultMetadata.from_result(result)
        metadata.to_yaml('result-stage0.yaml')

    Load and inspect metadata:
        metadata = ResultMetadata.from_yaml('result-stage0.yaml')
        print(f'Task: {metadata.task_name}')
        print(f'Duration: {metadata.duration_seconds}s')
        print(f'Status: {metadata.status}')

    Export after result acceptance:
        result.accept(context)
        export_result_metadata(result, context.report_dir)

    Batch metadata export:
        from pipeline.infrastructure.serializers import ResultMetadata
        for proxy in context.results:
            result = proxy.read()
            metadata = ResultMetadata.from_result(result)
            stage_num = result.stage_number
            metadata.to_yaml(f'stage{stage_num}-metadata.yaml')
"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

from pipeline.infrastructure.serializers import (
    ContextMetadata,
    JSONMetadataSerializer,
    YAMLMetadataSerializer,
    ResultMetadata,
    Timestamps,
)


class TestTimestamps(unittest.TestCase):
    """Tests for Timestamps dataclass."""

    def test_duration_calculation(self):
        """Test duration calculation between start and end."""
        start = datetime(2026, 1, 30, 14, 0, 0)
        end = datetime(2026, 1, 30, 14, 2, 30)

        ts = Timestamps(start=start, end=end)

        assert ts.duration == timedelta(minutes=2, seconds=30)
        assert ts.duration_seconds == 150.0

    def test_timestamps_serialization(self):
        """Test serialization to and from dict."""
        start = datetime(2026, 1, 30, 14, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 1, 30, 14, 5, 0, tzinfo=timezone.utc)

        ts = Timestamps(start=start, end=end)
        data = ts.to_dict()

        assert isinstance(data['start'], str)
        assert isinstance(data['end'], str)
        assert data['duration_seconds'] == 300.0

        ts2 = Timestamps.from_dict(data)
        assert ts2.start == start
        assert ts2.end == end


class TestResultMetadata(unittest.TestCase):
    """Tests for ResultMetadata extraction and serialization."""

    def setUp(self):
        """Set up mock result objects for testing."""
        self.start_time = datetime(2026, 1, 30, 10, 0, 0)
        self.end_time = datetime(2026, 1, 30, 10, 5, 0)

        # Create mock timestamps
        self.mock_timestamps = Mock()
        self.mock_timestamps.start = self.start_time
        self.mock_timestamps.end = self.end_time

    def _create_mock_result(self, task_name='test_task', status='completed', exception=None):
        """Create a mock result object."""
        result = Mock()
        result.pipeline_casa_task = task_name
        result.stage_number = 0
        result.timestamps = self.mock_timestamps
        result.inputs = {'vis': ['test.ms'], 'param': 'value'}
        result.qa = Mock()
        result.qa.scores = {'overall': 0.85, 'antenna': 0.92}
        result.subtask_results = []

        if exception:
            result.exception = exception

        return result

    def test_metadata_from_result(self):
        """Test extracting metadata from a result object."""
        result = self._create_mock_result(task_name='hifa_importdata')
        metadata = ResultMetadata.from_result(result)

        assert metadata.task_name == 'hifa_importdata'
        assert metadata.stage_number == 0
        assert metadata.status == 'completed'
        assert metadata.duration_seconds == 300.0
        assert metadata.inputs['vis'] == ['test.ms']
        assert metadata.qa_scores['overall'] == 0.85

    def test_metadata_from_failed_result(self):
        """Test extracting metadata from a failed result."""
        result = self._create_mock_result(exception=Exception('Test error'))
        metadata = ResultMetadata.from_result(result)

        assert metadata.status == 'failed'
        assert metadata.exception is not None

    def test_metadata_to_dict(self):
        """Test converting metadata to dictionary."""
        result = self._create_mock_result()
        metadata = ResultMetadata.from_result(result)
        data = metadata.to_dict()

        assert data['task_name'] == 'test_task'
        assert data['status'] == 'completed'
        assert data['timestamps']['duration_seconds'] == 300.0
        assert 'timestamps' in data
        assert 'inputs' in data

    def test_metadata_repr(self):
        """Test string representation of metadata."""
        result = self._create_mock_result(task_name='hifa_flagdata')
        metadata = ResultMetadata.from_result(result)
        repr_str = repr(metadata)

        assert 'hifa_flagdata' in repr_str
        assert 'completed' in repr_str
        assert '300.0s' in repr_str

    def test_metadata_json_roundtrip(self):
        """Test saving and loading metadata from JSON."""
        result = self._create_mock_result(task_name='hifa_calibration')
        original = ResultMetadata.from_result(result)

        # Save to JSON
        with tempfile.TemporaryDirectory() as temp_dir:
            json_file = Path(temp_dir) / 'metadata.json'
            original.to_json(json_file)

            # Load from JSON
            loaded = ResultMetadata.from_json(json_file)

        assert loaded.task_name == original.task_name
        assert loaded.stage_number == original.stage_number
        assert loaded.status == original.status
        assert loaded.duration_seconds == original.duration_seconds
        assert loaded.inputs == original.inputs
        assert loaded.qa_scores == original.qa_scores

    def test_metadata_yaml_roundtrip(self):
        """Test saving and loading metadata from YAML."""
        result = self._create_mock_result(task_name='hifa_calibration')
        original = ResultMetadata.from_result(result)

        # Save to YAML
        with tempfile.TemporaryDirectory() as temp_dir:
            yaml_file = Path(temp_dir) / 'metadata.yaml'
            original.to_yaml(yaml_file)

            # Load from YAML
            loaded = ResultMetadata.from_yaml(yaml_file)

        assert loaded.task_name == original.task_name
        assert loaded.stage_number == original.stage_number
        assert loaded.status == original.status
        assert loaded.duration_seconds == original.duration_seconds
        assert loaded.inputs == original.inputs
        assert loaded.qa_scores == original.qa_scores


class TestContextMetadata(unittest.TestCase):
    """Tests for ContextMetadata."""

    def test_context_metadata_creation(self):
        """Test creating context metadata."""
        metadata = ContextMetadata(
            name='test-context',
            output_dir='/tmp/test',
            task_counter=5,
            subtask_counter=0,
            num_results=5,
            total_duration_seconds=1250.0,
        )

        assert metadata.name == 'test-context'
        assert metadata.task_counter == 5
        assert metadata.num_results == 5
        assert metadata.total_duration_seconds == 1250.0

    def test_context_metadata_to_dict(self):
        """Test converting context metadata to dictionary."""
        metadata = ContextMetadata(
            name='test-context',
            output_dir='/tmp/test',
            task_counter=3,
            subtask_counter=1,
            num_results=3,
            total_duration_seconds=600.0,
        )

        data = metadata.to_dict()

        assert data['name'] == 'test-context'
        assert data['task_counter'] == 3
        assert data['num_results'] == 3
        assert data['total_duration_seconds'] == 600.0

    def test_context_metadata_json_roundtrip(self):
        """Test saving and loading context metadata from JSON."""
        original = ContextMetadata(
            name='test-ctx',
            output_dir='/data/output',
            task_counter=8,
            subtask_counter=2,
            num_results=8,
            total_duration_seconds=3600.0,
        )

        # Save to JSON
        with tempfile.TemporaryDirectory() as temp_dir:
            json_file = Path(temp_dir) / 'context-metadata.json'
            original.to_json(json_file)

            # Load from JSON
            loaded = ContextMetadata.from_json(json_file)

        assert loaded.name == original.name
        assert loaded.output_dir == original.output_dir
        assert loaded.task_counter == original.task_counter
        assert loaded.total_duration_seconds == original.total_duration_seconds

    def test_context_metadata_yaml_roundtrip(self):
        """Test saving and loading context metadata from YAML."""
        original = ContextMetadata(
            name='test-ctx',
            output_dir='/data/output',
            task_counter=8,
            subtask_counter=2,
            num_results=8,
            total_duration_seconds=3600.0,
        )

        # Save to YAML
        with tempfile.TemporaryDirectory() as temp_dir:
            yaml_file = Path(temp_dir) / 'context-metadata.yaml'
            original.to_yaml(yaml_file)

            # Load from YAML
            loaded = ContextMetadata.from_yaml(yaml_file)

        assert loaded.name == original.name
        assert loaded.output_dir == original.output_dir
        assert loaded.task_counter == original.task_counter
        assert loaded.total_duration_seconds == original.total_duration_seconds


class TestJSONMetadataSerializer(unittest.TestCase):
    """Tests for JSONMetadataSerializer."""

    def setUp(self):
        """Set up serializer and mock objects."""
        self.serializer = JSONMetadataSerializer()

        start = datetime(2026, 1, 30, 10, 0, 0)
        end = datetime(2026, 1, 30, 10, 10, 0)

        self.metadata = ResultMetadata(
            stage_number=2,
            task_name='hifa_checkphaseref',
            status='completed',
            timestamps=Timestamps(start=start, end=end),
            inputs={'caltable': 'cal.table'},
            qa_scores={'rms_error': 0.02},
        )

    def test_serialize_result_metadata(self):
        """Test serializing result metadata."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / 'result-metadata.json'
            self.serializer.serialize_result(self.metadata, output_file)

            assert output_file.exists()

    def test_deserialize_result_metadata(self):
        """Test deserializing result metadata."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / 'result-metadata.json'
            self.serializer.serialize_result(self.metadata, output_file)

            loaded = self.serializer.deserialize_result(output_file)

            assert loaded.task_name == self.metadata.task_name
            assert loaded.stage_number == self.metadata.stage_number
            assert loaded.status == self.metadata.status

    def test_serialize_context_metadata(self):
        """Test serializing context metadata."""
        ctx_metadata = ContextMetadata(
            name='integration-test',
            output_dir='/tmp/pipeline',
            task_counter=10,
            subtask_counter=0,
            num_results=10,
            total_duration_seconds=5000.0,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / 'context-metadata.json'
            self.serializer.serialize_context(ctx_metadata, output_file)

            assert output_file.exists()


class TestYAMLMetadataSerializer(unittest.TestCase):
    """Tests for YAMLMetadataSerializer."""

    def setUp(self):
        """Set up serializer and mock objects."""
        self.serializer = YAMLMetadataSerializer()

        start = datetime(2026, 1, 30, 10, 0, 0)
        end = datetime(2026, 1, 30, 10, 10, 0)

        self.metadata = ResultMetadata(
            stage_number=2,
            task_name='hifa_checkphaseref',
            status='completed',
            timestamps=Timestamps(start=start, end=end),
            inputs={'caltable': 'cal.table'},
            qa_scores={'rms_error': 0.02},
        )

    def test_serialize_result_metadata(self):
        """Test serializing result metadata to YAML."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / 'result-metadata.yaml'
            self.serializer.serialize_result(self.metadata, output_file)

            assert output_file.exists()

    def test_deserialize_result_metadata(self):
        """Test deserializing result metadata from YAML."""
        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / 'result-metadata.yaml'
            self.serializer.serialize_result(self.metadata, output_file)

            loaded = self.serializer.deserialize_result(output_file)

            assert loaded.task_name == self.metadata.task_name
            assert loaded.stage_number == self.metadata.stage_number
            assert loaded.status == self.metadata.status

    def test_serialize_context_metadata(self):
        """Test serializing context metadata to YAML."""
        ctx_metadata = ContextMetadata(
            name='integration-test',
            output_dir='/tmp/pipeline',
            task_counter=10,
            subtask_counter=0,
            num_results=10,
            total_duration_seconds=5000.0,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_file = Path(temp_dir) / 'context-metadata.yaml'
            self.serializer.serialize_context(ctx_metadata, output_file)

            assert output_file.exists()


# Example usage patterns (can be run as demonstrations)
def example_basic_export():
    """Example 1: Basic metadata export."""
    print('Example 1: Basic Metadata Export')
    print('-' * 50)

    # Create a mock result
    result = Mock()
    result.pipeline_casa_task = 'hifa_importdata'
    result.stage_number = 0
    result.timestamps = Mock(
        start=datetime(2026, 1, 30, 10, 0, 0),
        end=datetime(2026, 1, 30, 10, 5, 0),
    )
    result.inputs = {'vis': 'uid___A001_X1234.ms'}
    result.qa = Mock(scores={'overall': 0.92})
    result.subtask_results = []

    # Extract metadata
    metadata = ResultMetadata.from_result(result)

    print(f'Task: {metadata.task_name}')
    print(f'Duration: {metadata.timestamps.duration_seconds:.1f} seconds')
    print(f'Status: {metadata.status}')
    print(f'QA Score: {metadata.qa_scores.get("overall", "N/A")}')
    print()


def example_batch_inspection():
    """Example 2: Batch metadata inspection."""
    print('Example 2: Batch Metadata Inspection')
    print('-' * 50)

    # Simulate multiple results
    tasks = ['hifa_importdata', 'hifa_flagdata', 'hifa_calibration']
    durations = [300, 450, 1200]

    total_time = 0
    for task, duration in zip(tasks, durations):
        metadata = ResultMetadata(
            stage_number=tasks.index(task),
            task_name=task,
            status='completed',
            timestamps=Timestamps(
                start=datetime.now(),
                end=datetime.now() + timedelta(seconds=duration),
            ),
        )
        print(f'{metadata.stage_number}: {metadata.task_name} ({duration}s)')
        total_time += duration

    print(f'\nTotal execution time: {total_time}s ({total_time / 60:.1f} minutes)')
    print()


def example_serialization_workflow():
    """Example 3: Complete serialization workflow."""
    print('Example 3: Serialization Workflow')
    print('-' * 50)

    # Create metadata
    metadata = ResultMetadata(
        stage_number=5,
        task_name='hifa_imaging',
        status='completed',
        timestamps=Timestamps(
            start=datetime(2026, 1, 30, 14, 0, 0),
            end=datetime(2026, 1, 30, 14, 45, 0),
        ),
        inputs={'robust': 0.5, 'niter': 1000},
        qa_scores={'beam_shape': 0.88, 'image_rms': 0.92},
        notes='Imaging completed successfully with good beam quality',
    )

    # Show dictionary representation
    print('Metadata as Dictionary:')
    for key, value in metadata.to_dict().items():
        print(f'  {key}: {value}')
    print()


if __name__ == '__main__':
    # Run demonstrations
    example_basic_export()
    example_batch_inspection()
    example_serialization_workflow()

    # Run unit tests
    print('\n' + '=' * 50)
    print('Running Unit Tests')
    print('=' * 50 + '\n')

    unittest.main(argv=[''], exit=False, verbosity=2)
