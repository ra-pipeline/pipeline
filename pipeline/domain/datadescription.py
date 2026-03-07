"""Pydantic-based DataDescription domain object prototype for Phase 5 modernization."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field as PydanticField

polarization_map = {
    'linear': {0: ['XX', 9], 1: ['YY', 12], 2: ['XY', 10], 3: ['YX', 11]},
    'circular': {0: ['RR', 5], 1: ['LL', 8], 2: ['RL', 6], 3: ['LR', 7]},
    'stokes': {0: ['I', 1], 1: ['Q', 2], 2: ['U', 3], 3: ['V', 4]},
    'linpol': {0: ['Ptotal', 28], 1: ['Plinear', 29], 2: ['PFtotal', 30], 3: ['PFlinear', 31], 4: ['Pangle', 32]},
}

to_polid = {
    'XX': 0,
    'YY': 1,
    'XY': 2,
    'YX': 3,
    'RR': 0,
    'LL': 1,
    'RL': 2,
    'LR': 3,
    'I': 0,
    'Q': 1,
    'U': 2,
    'V': 3,
}


class DataDescription(BaseModel):
    """Data description domain object."""

    id: int = PydanticField(..., description='Numerical identifier of the data description')
    spw: Any = PydanticField(..., description='SpectralWindow object')
    pol_id: int = PydanticField(..., description='Polarization ID')
    obs_time: Any | None = PydanticField(default=None, description='Mean observation time')
    chan_freq: list[Any] = PydanticField(default_factory=list, description='Channel centre frequencies')
    corr_axis: list[str] = PydanticField(default_factory=list, description='Correlation axis labels')

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_default=True,
    )

    def __init__(self, id: int | None = None, spw: Any | None = None, pol_id: int | None = None, **data: Any) -> None:
        """Create a DataDescription.

        The legacy pipeline code constructs data descriptions positionally as
        ``DataDescription(id, spw, pol_id)``.
        """
        if id is not None and 'id' not in data:
            data['id'] = id
        if spw is not None and 'spw' not in data:
            data['spw'] = spw
        if pol_id is not None and 'pol_id' not in data:
            data['pol_id'] = pol_id
        super().__init__(**data)

    def __repr__(self) -> str:
        return 'DataDescription({0}, {1!r}, {2!r})'.format(self.id, self.spw, self.pol_id)

    def __hash__(self) -> int:
        spw_id = getattr(self.spw, 'id', None)
        return hash((self.__class__, self.id, spw_id, self.pol_id))

    def __str__(self) -> str:
        args = map(str, (self.id, self.spw.id, self.pol_id))
        return 'DataDescription({0})'.format(', '.join(args))

    @property
    def polarizations(self) -> list[str]:
        """Return polarizations in the DataDescription."""
        all_corrs = ''.join(self.corr_axis)
        pols = []
        if 'R' in all_corrs:
            pols.append('R')
        if 'L' in all_corrs:
            pols.append('L')
        if 'X' in all_corrs:
            pols.append('X')
        if 'Y' in all_corrs:
            pols.append('Y')
        return pols

    @property
    def num_polarizations(self) -> int:
        """Return number of polarizations in the DataDescription."""
        return len(self.polarizations)

    def get_polarization_label(self, pol_id: int) -> str:
        """Return polarization label associated with given ID."""
        corr_type = self.polarizations
        if 'X' in corr_type or 'Y' in corr_type:
            poltype = 'linear'
        elif 'R' in corr_type or 'L' in corr_type:
            poltype = 'circular'
        else:
            poltype = 'stokes'

        label, _ = polarization_map[poltype][pol_id]
        return label

    @staticmethod
    def get_polarization_id(pol: str) -> int:
        """Return polarization ID associated with given label."""
        return to_polid[pol]

    def to_dict(self) -> dict[str, Any]:
        """Export to dictionary (data fields only)."""
        data = self.model_dump(exclude={'spw'})
        if hasattr(self.spw, 'id'):
            data['spw_id'] = self.spw.id
        return data

    def to_json(self) -> str:
        """Export to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DataDescription:
        """Create from dictionary."""
        payload = dict(data)
        payload.pop('spw_id', None)
        return cls(**payload)

    @classmethod
    def from_json(cls, json_str: str) -> DataDescription:
        """Create from JSON string."""
        return cls.model_validate_json(json_str)
