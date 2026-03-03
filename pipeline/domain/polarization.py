"""Pydantic-based Polarization domain object prototype for Phase 5 modernization."""

from __future__ import annotations

import json
from typing import Any

import numpy
from pydantic import BaseModel, ConfigDict, computed_field


class Polarization(BaseModel):
    """Polarization domain object."""

    id: int
    num_corr: int
    corr_type: Any
    corr_product: Any

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_default=True,
    )

    def __hash__(self) -> int:
        return hash((self.__class__, self.id, self.num_corr))

    @computed_field
    @property
    def corr_type_string(self) -> list[str]:
        """Return string representation of the Stokes type for each correlation."""
        stokes_enum = [
            'Undefined',
            'I',
            'Q',
            'U',
            'V',
            'RR',
            'RL',
            'LR',
            'LL',
            'XX',
            'XY',
            'YX',
            'YY',
            'RX',
            'RY',
            'LX',
            'LY',
            'XR',
            'XL',
            'YR',
            'YL',
            'PP',
            'PQ',
            'QP',
            'QQ',
            'RCircular',
            'LCircular',
            'Linear',
            'Ptotal',
            'Plinear',
            'PFtotal',
            'PFlinear',
            'Pangle',
        ]
        return [stokes_enum[c] for c in self._corr_type_list()]

    def _corr_type_list(self) -> list[int]:
        if isinstance(self.corr_type, numpy.ndarray):
            return self.corr_type.tolist()
        return list(self.corr_type)

    def __str__(self) -> str:
        return 'Polarization({!r}, {!r})'.format(self.id, self.corr_type_string)

    def __repr__(self) -> str:
        return 'Polarization({!r}, {!r}, {!r}, {!r})'.format(
            self.id,
            self.num_corr,
            self.corr_type,
            self.corr_product,
        )

    def to_dict(self) -> dict[str, Any]:
        """Export to dictionary (data fields only)."""
        data = self.model_dump(exclude={'corr_type_string'})
        if isinstance(data.get('corr_type'), numpy.ndarray):
            data['corr_type'] = data['corr_type'].tolist()
        if isinstance(data.get('corr_product'), numpy.ndarray):
            data['corr_product'] = data['corr_product'].tolist()
        return data

    def to_json(self) -> str:
        """Export to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Polarization:
        """Create from dictionary."""
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> Polarization:
        """Create from JSON string."""
        return cls.model_validate_json(json_str)
