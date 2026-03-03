"""Pydantic-based Source domain object prototype for Phase 5 modernization.

This module demonstrates how to refactor the current Source class to use Pydantic
for data validation and serialization while preserving the existing public API.
"""

from __future__ import annotations

import itertools
import pprint
from typing import Any

from pydantic import BaseModel, ConfigDict, Field as PydanticField

from pipeline.infrastructure import casa_tools

_pprinter = pprint.PrettyPrinter()


class Source(BaseModel):
    """Source domain object.

    A logical representation of an astronomical source with structured data
    model and automatic serialization support.

    Attributes:
        id: Numerical identifier of the source.
        name: Name of the source.
        direction: CASA direction measure dictionary.
        proper_motion_data: Proper motion values as CASA quantity dictionaries.
        is_eph_obj: Whether this is a moving source (ephemeris table entry).
        table_name: Base file name of the ephemeris table (no extension).
        avg_spacing: Average time spacing (minutes) between ephemeris entries.
        fields: Field objects associated with this source.
    """

    id: int = PydanticField(..., description='Numerical source identifier')
    name: str = PydanticField(..., description='Source name')
    direction: dict[str, Any] = PydanticField(..., description='CASA direction measure')
    proper_motion_data: dict[str, dict[str, Any]] = PydanticField(..., alias='proper_motion')
    is_eph_obj: bool = PydanticField(..., description='Ephemeris table flag')
    table_name: str = PydanticField(..., description='Ephemeris table base name')
    avg_spacing: float | str = PydanticField(
        ..., description='Average ephemeris spacing in minutes'
    )
    fields: list[Any] = PydanticField(default_factory=list, description='Associated fields')

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        validate_default=True,
    )

    def __repr__(self) -> str:
        return '{0}({1}, {2!r}, {3}, {4})'.format(
            self.__class__.__name__,
            self.id,
            self.name,
            _pprinter.pformat(self.direction),
            _pprinter.pformat(self.proper_motion_data),
        )

    def __hash__(self) -> int:
        return hash((self.__class__, self.id, self.name))

    @property
    def dec(self) -> str:
        """Return declination of the source."""
        return casa_tools.quanta.formxxx(self.latitude, format='dms', prec=2)

    @property
    def frame(self) -> str:
        """Return reference frame code for the direction to the source."""
        return self.direction['refer']

    @property
    def intents(self) -> set[str]:
        """Return unique scan intents associated with the source."""
        return set(itertools.chain(*[f.intents for f in self.fields]))

    @property
    def latitude(self) -> dict[str, Any]:
        """Return latitude of the source."""
        return self.direction['m1']

    @property
    def longitude(self) -> dict[str, Any]:
        """Return longitude of the source."""
        return self.direction['m0']

    @property
    def pm_x(self) -> str:
        """Return longitudinal component of proper motion as a string."""
        return self._format_pm(axis='longitude')

    @property
    def pm_y(self) -> str:
        """Return latitudinal component of proper motion as a string."""
        return self._format_pm(axis='latitude')

    @property
    def proper_motion(self) -> str:
        """Return string representation of proper motion of the source."""
        qa = casa_tools.quanta
        pm_x = self.proper_motion_data['longitude']
        pm_y = self.proper_motion_data['latitude']
        return '%.3e %.3e %s' % (
            qa.getvalue(pm_x),
            qa.getvalue(pm_y),
            qa.getunit(pm_x),
        )

    @property
    def ra(self) -> str:
        """Return right ascension of the source."""
        return casa_tools.quanta.formxxx(self.longitude, format='hms', prec=3)

    @property
    def gl(self) -> str:
        """Return longitude for the source, in DMS format."""
        return casa_tools.quanta.formxxx(self.longitude, format='dms', prec=2)

    @property
    def gb(self) -> str:
        """Return declination of the source."""
        return self.dec

    @property
    def ephemeris_table(self) -> str:
        """Return name of the ephemeris table or '' if not an ephemeris source."""
        return self.table_name

    def _format_pm(self, axis: str) -> str:
        """Return proper motion along given axis.

        Args:
            axis: Axis to return proper motion for; 'longitude' or 'latitude'.

        Returns:
            String representation of proper motion along given axis.
        """
        qa = casa_tools.quanta
        val = qa.getvalue(self.proper_motion_data[axis])
        units = qa.getunit(self.proper_motion_data[axis])
        return '' if val == 0 else '%.3e %s' % (val, units)

    def __str__(self) -> str:
        return (
            'Source({0}:{1}, pos={2} {3} ({4}), pm={5})'
            ''.format(self.id, self.name, self.ra, self.dec, self.frame, self.proper_motion)
        )

    def to_dict(self) -> dict[str, Any]:
        """Export to dictionary (data fields only)."""
        return self.model_dump(by_alias=True, exclude={'fields'})

    def to_json(self) -> str:
        """Export to JSON string."""
        return self.model_dump_json(by_alias=True, exclude={'fields'})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Source:
        """Create from dictionary."""
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> Source:
        """Create from JSON string."""
        return cls.model_validate_json(json_str)

    @classmethod
    def from_source_object(cls, source: Any) -> Source:
        """Create from legacy Source-like object for migration."""
        proper_motion = getattr(source, '_proper_motion', None)
        if proper_motion is None:
            proper_motion = getattr(source, 'proper_motion', None)

        table_name = getattr(source, 'ephemeris_table', None)
        if table_name is None:
            table_name = getattr(source, 'table_name', None)

        return cls(
            id=getattr(source, 'id', None),
            name=getattr(source, 'name', None),
            direction=getattr(source, 'direction', None),
            proper_motion=proper_motion,
            is_eph_obj=getattr(source, 'is_eph_obj', None),
            table_name=table_name,
            avg_spacing=getattr(source, 'avg_spacing', None),
            fields=getattr(source, 'fields', []),
        )


def upgrade_source(source_obj: Any) -> Source | None:
    """Upgrade a legacy Source-like object to Pydantic version.

    Args:
        source_obj: Instance of legacy Source-like object or SourcePydantic.

    Returns:
        SourcePydantic instance, or None if input is invalid.
    """
    if isinstance(source_obj, Source):
        return source_obj

    if source_obj is None:
        return None

    if hasattr(source_obj, 'id') and hasattr(source_obj, 'name'):
        return Source.from_source_object(source_obj)

    return None
