"""Serialization framework for pipeline results and context metadata.

This module provides structured serialization of pipeline execution metadata
to JSON and YAML formats, enabling human-readable storage and inspection
of pipeline state without relying entirely on pickle.

The framework is designed to coexist with existing pickle-based storage,
providing an additional layer of structured metadata that can be accessed
independently.

Classes:
    ResultMetadata: Structured metadata extracted from a Results object.
    ContextMetadata: Summary of context state at a given stage.
    MetadataSerializer: Base interface for serialization backends.
    JSONMetadataSerializer: JSON-based metadata export.
    YAMLMetadataSerializer: YAML-based metadata export.

Example:
    Extract and save metadata without pickling full result:

        from pipeline.infrastructure.serializers import ResultMetadata
        metadata = ResultMetadata.from_result(result)
        metadata.to_json('result-stage0.json')

    Load metadata efficiently:

        metadata = ResultMetadata.from_json('result-stage0.json')
        print(f'{metadata.task_name} took {metadata.duration_seconds}s')
"""

from __future__ import annotations

import abc
import dataclasses
import datetime
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

LOG = None  # Set via lazy import


@dataclasses.dataclass
class Timestamps:
    """Container for task execution timestamps."""

    start: datetime.datetime
    end: datetime.datetime

    @property
    def duration(self) -> datetime.timedelta:
        """Return duration between start and end."""
        return self.end - self.start

    @property
    def duration_seconds(self) -> float:
        """Return duration in seconds."""
        return self.duration.total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with ISO format strings."""
        # Ensure datetimes are UTC-aware
        start = self.start if self.start.tzinfo else self.start.replace(tzinfo=datetime.timezone.utc)
        end = self.end if self.end.tzinfo else self.end.replace(tzinfo=datetime.timezone.utc)
        return {
            'start': start.isoformat() if isinstance(start, datetime.datetime) else str(start),
            'end': end.isoformat() if isinstance(end, datetime.datetime) else str(end),
            'duration_seconds': self.duration_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> Timestamps:
        """Construct from dictionary."""
        # Parse ISO format strings and ensure UTC timezone
        start = datetime.datetime.fromisoformat(data['start'])
        end = datetime.datetime.fromisoformat(data['end'])
        
        # Ensure UTC timezone
        if start.tzinfo is None:
            start = start.replace(tzinfo=datetime.timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=datetime.timezone.utc)
        
        return cls(start=start, end=end)


@dataclasses.dataclass
class ResultMetadata:
    """Structured metadata extracted from a Results object.

    This captures essential information about a task result without
    requiring the full result object to be unpickled or loaded.

    Attributes:
        stage_number: Pipeline stage index.
        task_name: Human-readable task name.
        status: Execution status ('completed', 'failed', 'in_progress').
        timestamps: Start and end times for task execution.
        inputs: Dictionary of task input parameters.
        qa_scores: Dictionary of QA metrics if available.
        exception: Exception message if status is 'failed'.
        subtask_count: Number of subtasks if this is a compound task.
        notes: Optional user notes or warnings.
    """

    stage_number: int
    task_name: str
    status: str
    timestamps: Timestamps
    inputs: dict[str, Any] = dataclasses.field(default_factory=dict)
    qa_scores: dict[str, Any] = dataclasses.field(default_factory=dict)
    exception: str | None = None
    subtask_count: int = 0
    notes: str | None = None

    @classmethod
    def from_result(cls, result: Any) -> ResultMetadata:
        """Extract metadata from a Results object.

        This method safely extracts metadata from a result object without
        requiring full unpickling of complex attributes.

        Args:
            result: A pipeline Results object.

        Returns:
            ResultMetadata instance with extracted information.
        """
        # Get task name from result or its class
        task_name = getattr(result, 'pipeline_casa_task', result.__class__.__name__)

        # Determine status
        status = 'completed'
        exception_msg = None
        exception_value = getattr(result, 'exception', None)
        if isinstance(exception_value, BaseException):
            status = 'failed'
            exception_msg = str(exception_value)
        elif isinstance(exception_value, str) and exception_value:
            status = 'failed'
            exception_msg = exception_value

        # Extract timestamps
        timestamps = Timestamps(
            start=getattr(result, 'timestamps', {}).start if hasattr(result, 'timestamps') else datetime.datetime.now(datetime.timezone.utc),
            end=getattr(result, 'timestamps', {}).end if hasattr(result, 'timestamps') else datetime.datetime.now(datetime.timezone.utc),
        )

        # Extract inputs
        inputs = getattr(result, 'inputs', {})
        if callable(getattr(inputs, 'as_dict', None)):
            inputs = inputs.as_dict()
        elif not isinstance(inputs, dict):
            inputs = dict(inputs) if hasattr(inputs, '__iter__') else {}

        # Extract QA scores
        qa_scores = {}
        if hasattr(result, 'qa') and hasattr(result.qa, 'scores'):
            qa_scores = result.qa.scores if isinstance(result.qa.scores, dict) else {}

        # Count subtasks
        subtask_count = len(getattr(result, 'subtask_results', []))

        return cls(
            stage_number=getattr(result, 'stage_number', -1),
            task_name=task_name,
            status=status,
            timestamps=timestamps,
            inputs=inputs,
            qa_scores=qa_scores,
            exception=exception_msg,
            subtask_count=subtask_count,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert metadata to dictionary."""
        return {
            'stage_number': self.stage_number,
            'task_name': self.task_name,
            'status': self.status,
            'timestamps': self.timestamps.to_dict(),
            'inputs': self.inputs,
            'qa_scores': self.qa_scores,
            'exception': self.exception,
            'subtask_count': self.subtask_count,
            'notes': self.notes,
        }

    @property
    def duration_seconds(self) -> float:
        """Return duration in seconds."""
        return self.timestamps.duration_seconds

    def to_json(self, filepath: str | Path) -> None:
        """Save metadata to JSON file.

        Args:
            filepath: Path where JSON file will be written.
        """
        data = self.to_dict()
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    @classmethod
    def from_json(cls, filepath: str | Path) -> ResultMetadata:
        """Load metadata from JSON file.

        Args:
            filepath: Path to JSON file.

        Returns:
            ResultMetadata instance.
        """
        with open(filepath, 'r') as f:
            data = json.load(f)

        timestamps = Timestamps.from_dict(data['timestamps'])

        return cls(
            stage_number=data['stage_number'],
            task_name=data['task_name'],
            status=data['status'],
            timestamps=timestamps,
            inputs=data.get('inputs', {}),
            qa_scores=data.get('qa_scores', {}),
            exception=data.get('exception'),
            subtask_count=data.get('subtask_count', 0),
            notes=data.get('notes'),
        )

    def __repr__(self) -> str:
        return (f"ResultMetadata(stage={self.stage_number}, "
                f"task={self.task_name}, status={self.status}, "
                f"duration={self.timestamps.duration_seconds:.1f}s)")


@dataclasses.dataclass
class ContextMetadata:
    """Summary metadata for a pipeline Context at a given point.

    Attributes:
        name: Context name.
        output_dir: Working directory.
        task_counter: Last completed task index.
        subtask_counter: Last completed subtask index.
        num_results: Number of completed results.
        total_duration_seconds: Total execution time.
        last_update: Timestamp of last modification.
    """

    name: str
    output_dir: str
    task_counter: int
    subtask_counter: int
    num_results: int
    total_duration_seconds: float = 0.0
    last_update: datetime.datetime = dataclasses.field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            'name': self.name,
            'output_dir': self.output_dir,
            'task_counter': self.task_counter,
            'subtask_counter': self.subtask_counter,
            'num_results': self.num_results,
            'total_duration_seconds': self.total_duration_seconds,
            'last_update': self.last_update.isoformat(),
        }

    def to_json(self, filepath: str | Path) -> None:
        """Save context metadata to JSON file."""
        data = self.to_dict()
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    @classmethod
    def from_json(cls, filepath: str | Path) -> ContextMetadata:
        """Load context metadata from JSON file."""
        with open(filepath, 'r') as f:
            data = json.load(f)
        return cls(**data)


class MetadataSerializer(abc.ABC):
    """Abstract base class for metadata serializers."""

    @abc.abstractmethod
    def serialize_result(self, metadata: ResultMetadata, filepath: str | Path) -> None:
        """Serialize result metadata to file."""
        pass

    @abc.abstractmethod
    def deserialize_result(self, filepath: str | Path) -> ResultMetadata:
        """Deserialize result metadata from file."""
        pass

    @abc.abstractmethod
    def serialize_context(self, metadata: ContextMetadata, filepath: str | Path) -> None:
        """Serialize context metadata to file."""
        pass

    @abc.abstractmethod
    def deserialize_context(self, filepath: str | Path) -> ContextMetadata:
        """Deserialize context metadata from file."""
        pass


class JSONMetadataSerializer(MetadataSerializer):
    """JSON-based metadata serializer."""

    def serialize_result(self, metadata: ResultMetadata, filepath: str | Path) -> None:
        """Serialize result metadata to JSON."""
        metadata.to_json(filepath)

    def deserialize_result(self, filepath: str | Path) -> ResultMetadata:
        """Deserialize result metadata from JSON."""
        return ResultMetadata.from_json(filepath)

    def serialize_context(self, metadata: ContextMetadata, filepath: str | Path) -> None:
        """Serialize context metadata to JSON."""
        metadata.to_json(filepath)

    def deserialize_context(self, filepath: str | Path) -> ContextMetadata:
        """Deserialize context metadata from JSON."""
        return ContextMetadata.from_json(filepath)


def export_result_metadata(
    result: Any,
    stage_dir: str | Path,
    serializer: MetadataSerializer | None = None,
) -> None:
    """Export result metadata to structured format.

    This is a convenience function that can be called after a result
    is accepted into the context, creating a JSON metadata file
    alongside the pickled result.

    Args:
        result: The Results object to export metadata from.
        stage_dir: Directory where metadata file will be stored.
        serializer: Serializer to use (defaults to JSON).

    Example:
        from pipeline.infrastructure.serializers import export_result_metadata

        # After result.accept(context):
        export_result_metadata(result, context.report_dir)
    """
    if serializer is None:
        serializer = JSONMetadataSerializer()

    stage_num = getattr(result, 'stage_number', 0)
    metadata = ResultMetadata.from_result(result)

    output_path = Path(stage_dir) / f'result-stage{stage_num}-metadata.json'
    serializer.serialize_result(metadata, output_path)


def export_context_metadata(
    context: Any,
    output_path: str | Path,
    serializer: MetadataSerializer | None = None,
) -> None:
    """Export context metadata to structured format.

    Args:
        context: The Context object to export metadata from.
        output_path: Path where metadata file will be stored.
        serializer: Serializer to use (defaults to JSON).
    """
    if serializer is None:
        serializer = JSONMetadataSerializer()

    # Calculate total duration from results
    total_duration = 0.0
    if hasattr(context, 'results') and context.results:
        first_result = context.results[0].read() if hasattr(context.results[0], 'read') else context.results[0]
        last_result = context.results[-1].read() if hasattr(context.results[-1], 'read') else context.results[-1]

        if hasattr(first_result, 'timestamps') and hasattr(last_result, 'timestamps'):
            duration = last_result.timestamps.end - first_result.timestamps.start
            total_duration = duration.total_seconds()

    metadata = ContextMetadata(
        name=context.name,
        output_dir=context.output_dir,
        task_counter=context.task_counter,
        subtask_counter=context.subtask_counter,
        num_results=len(context.results) if hasattr(context, 'results') else 0,
        total_duration_seconds=total_duration,
    )

    serializer.serialize_context(metadata, output_path)
