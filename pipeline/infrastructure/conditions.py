"""Structured condition helpers for cross-stage pipeline state."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


CONDITION_CODE_CLEAN_LIST_INFO = 'imaging_target_selection_notice'
CONDITION_CODE_CONTINUUM_SELECTION_WARNING = 'continuum_selection_warning'
CONDITION_CODE_IMAGING_PARAMETER_OVERRIDE = 'imaging_parameter_override'
CONDITION_CODE_SIZE_MITIGATION = 'size_mitigation'


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


@dataclass
class PipelineCondition:
    """Structured non-fatal condition stored on the pipeline context."""

    code: str
    severity: str
    scope: str
    disposition: str
    message: str | None = None
    details: dict[str, Any] | None = None
    producer_stage: int | None = None
    producer_task: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            'code': self.code,
            'severity': self.severity,
            'scope': self.scope,
            'disposition': self.disposition,
            'message': self.message,
            'details': copy.deepcopy(self.details),
            'producer_stage': self.producer_stage,
            'producer_task': self.producer_task,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'active': self.active,
        }


def create_or_update_condition(
    *,
    existing: PipelineCondition | None,
    code: str,
    severity: str,
    scope: str,
    disposition: str,
    message: str | None,
    details: dict[str, Any] | None,
    producer_stage: int | None,
    producer_task: str | None,
) -> PipelineCondition:
    """Create or update a condition record."""

    timestamp = _utc_now()
    created_at = existing.created_at if existing is not None else timestamp
    return PipelineCondition(
        code=code,
        severity=severity,
        scope=scope,
        disposition=disposition,
        message=message,
        details=copy.deepcopy(details),
        producer_stage=producer_stage,
        producer_task=producer_task,
        created_at=created_at,
        updated_at=timestamp,
        active=True,
    )


def clear_existing_condition(existing: PipelineCondition) -> PipelineCondition:
    """Return a cleared copy of an existing condition."""

    cleared = copy.deepcopy(existing)
    cleared.active = False
    cleared.updated_at = _utc_now()
    return cleared


def get_size_mitigation_parameters(context: object) -> dict[str, Any]:
    """Return size mitigation parameters from the registry or legacy context."""

    get_condition = getattr(context, 'get_condition', None)
    if callable(get_condition):
        condition = get_condition(CONDITION_CODE_SIZE_MITIGATION)
        if condition is not None and isinstance(condition.details, dict):
            return copy.deepcopy(condition.details)

    parameters = getattr(context, 'size_mitigation_parameters', {})
    if isinstance(parameters, dict):
        return copy.deepcopy(parameters)
    return {}


def has_size_mitigation_error(context: object) -> bool:
    """Return whether size mitigation resolved to a blocking error."""

    return get_size_mitigation_parameters(context).get('status') == 'ERROR'


def get_clean_list_info(context: object) -> dict[str, Any]:
    """Return clean-list status information from the registry or legacy context."""

    get_condition = getattr(context, 'get_condition', None)
    if callable(get_condition):
        condition = get_condition(CONDITION_CODE_CLEAN_LIST_INFO)
        if condition is not None and isinstance(condition.details, dict):
            return copy.deepcopy(condition.details)

    info = getattr(context, 'clean_list_info', {})
    if isinstance(info, dict):
        return copy.deepcopy(info)
    return {}


def get_imaging_parameter_overrides(context: object) -> dict[str, Any]:
    """Return imaging parameter overrides from the registry or legacy context."""

    get_condition = getattr(context, 'get_condition', None)
    if callable(get_condition):
        condition = get_condition(CONDITION_CODE_IMAGING_PARAMETER_OVERRIDE)
        if condition is not None and isinstance(condition.details, dict):
            return copy.deepcopy(condition.details)

    parameters = getattr(context, 'imaging_parameters', {})
    if isinstance(parameters, dict):
        return copy.deepcopy(parameters)
    return {}


def get_imaging_parameter(context: object, key: str, default: Any = None) -> Any:
    """Return a single imaging parameter override, preferring the registry."""

    return get_imaging_parameter_overrides(context).get(key, default)


def get_continuum_selection_warnings(context: object) -> list[dict[str, Any]]:
    """Return structured findcont warnings from the registry."""

    get_condition = getattr(context, 'get_condition', None)
    if callable(get_condition):
        condition = get_condition(CONDITION_CODE_CONTINUUM_SELECTION_WARNING)
        if condition is not None and isinstance(condition.details, dict):
            warnings = condition.details.get('warnings', [])
            if isinstance(warnings, list):
                return copy.deepcopy(warnings)

    return []