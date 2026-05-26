"""Pydantic-based Antenna domain object prototype.

This module demonstrates how to refactor the current Antenna class to use Pydantic
for data validation and serialization while preserving the existing public API.

Key improvements:
- Strict type validation (Pydantic native)
- Automatic serialization/deserialization (to_dict, from_dict)
- JSON/YAML support via model_dump/model_validate
- Better IDE support (autocomplete, type hints)
- Backward compatible (existing code unchanged)
"""

from __future__ import annotations

import pprint
from typing import Any

from pydantic import BaseModel, Field as PydanticField, computed_field, ConfigDict

from pipeline.infrastructure import casa_tools

_pprinter = pprint.PrettyPrinter()


class Antenna(BaseModel):
    """Pydantic-based antenna domain object.

    A logical representation of an antenna with structured data model and
    automatic serialization support. Preserves all existing API behaviors
    through computed fields and properties.

    Attributes:
        id: Numerical identifier of antenna within ANTENNA subtable
        name: Name of the antenna (may be empty)
        station: Station pad where antenna is situated
        diameter: Physical diameter in meters
        position: Dict with longitude, latitude, height (CASA formats)
        offset: Dict with offset position relative to array reference
    """

    # -- 1. Data Fields (Serialized) --
    # These are the raw data that get persisted
    id: int = PydanticField(..., description='Numerical antenna identifier')
    name: str = PydanticField(default='', description='Antenna name')
    station: str = PydanticField(default='', description='Station pad identifier')
    diameter: float = PydanticField(..., description='Antenna diameter in meters')
    position: dict[str, Any] = PydanticField(..., description='Position dict (m0, m1, m2 keys)')
    offset: dict[str, Any] = PydanticField(..., description='Offset position dict (m0, m1, m2 keys)')

    # -- Pydantic Configuration --
    model_config = ConfigDict(
        # Allow any types (CASA tools objects, quantity dicts, etc)
        arbitrary_types_allowed=True,
        # Use both field names and aliases
        populate_by_name=True,
        # Don't populate from None values
        validate_default=True,
    )

    def __init__(
        self,
        antenna_id: int | None = None,
        name: str | None = None,
        station: str | None = None,
        position: dict[str, Any] | None = None,
        offset: dict[str, Any] | None = None,
        diameter: float | None = None,
        **data: Any,
    ) -> None:
        """Create an Antenna.

        The legacy pipeline code constructs antennas positionally as
        ``Antenna(id, name, station, position, offset, diameter)``.
        Pydantic models only accept keyword arguments by default, so we map
        these positional arguments onto the corresponding fields.
        """
        if antenna_id is not None and 'id' not in data:
            data['id'] = antenna_id
        if name is not None and 'name' not in data:
            data['name'] = name
        if station is not None and 'station' not in data:
            data['station'] = station
        if position is not None and 'position' not in data:
            data['position'] = position
        if offset is not None and 'offset' not in data:
            data['offset'] = offset
        if diameter is not None and 'diameter' not in data:
            data['diameter'] = diameter
        super().__init__(**data)

    # -- 2. Computed Attributes (Not Serialized) --
    # These derive from data fields
    @computed_field
    @property
    def longitude(self) -> Any:
        """Longitude of antenna as CASA quantity in radians."""
        return self.position.get('m0')

    @computed_field
    @property
    def latitude(self) -> Any:
        """Latitude of antenna as CASA quantity in radians."""
        return self.position.get('m1')

    @computed_field
    @property
    def height(self) -> Any:
        """Height of antenna (radial distance from Earth's centre) in meters."""
        return self.position.get('m2')

    @property
    def direction(self) -> dict[str, Any]:
        """J2000 position on the sky to which antenna points.

        Computed on access (not cached) to avoid pickling CASA tool objects.
        """
        if self.longitude is None or self.latitude is None:
            return {}
        mt = casa_tools.measures
        return mt.direction(v0=self.longitude, v1=self.latitude)

    @property
    def identifier(self) -> str:
        """Human-readable identifier for this antenna."""
        return self.name if self.name else f"#{self.id}"

    # -- 3. String Representations (Preserving Legacy Formatting) --
    def __repr__(self) -> str:
        """Return detailed string representation matching original Antenna class."""
        return '{0}({1}, {2!r}, {3!r}, {4}, {5}, {6})'.format(
            'Antenna',
            self.id,
            self.name,
            self.station,
            _pprinter.pformat(self.position),
            _pprinter.pformat(self.offset),
            self.diameter,
        )

    def __str__(self) -> str:
        """Return brief string representation matching original Antenna class."""
        lon_str = ''
        lat_str = ''

        if self.longitude is not None and self.latitude is not None:
            qt = casa_tools.quanta
            lon_str = qt.tos(self.longitude)
            lat_str = qt.tos(self.latitude)

        return f'<Antenna {self.identifier} (lon={lon_str}, lat={lat_str})>'

    def __hash__(self) -> int:
        return hash((self.__class__, self.id, self.name, self.station))

    # -- 4. Serialization Methods --
    # Built-in Pydantic serialization (data fields only)
    def to_dict(self) -> dict[str, Any]:
        """Export to dictionary (data fields only, no computed fields)."""
        return self.model_dump(exclude={'longitude', 'latitude', 'height'})

    def to_json(self) -> str:
        """Export to JSON string."""
        return self.model_dump_json(exclude={'longitude', 'latitude', 'height'})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Antenna:
        """Create from dictionary."""
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> Antenna:
        """Create from JSON string."""
        return cls.model_validate_json(json_str)

    # -- 5. Factory Methods for Common Scenarios --
    @classmethod
    def from_antenna_object(cls, old_antenna: Any) -> Antenna:
        """Create from legacy Antenna-like object for migration."""
        return cls(
            id=old_antenna.id,
            name=old_antenna.name,
            station=old_antenna.station,
            diameter=old_antenna.diameter,
            position=old_antenna.position,
            offset=old_antenna.offset,
        )


# -- 6. Migration Helper --
def upgrade_antenna(antenna_obj: Any) -> Antenna | None:
    """Upgrade a legacy Antenna object to Pydantic version.

    Args:
        antenna_obj: Instance of legacy Antenna class or Antenna

    Returns:
        Antenna instance, or None if input is invalid
    """
    # Already Pydantic?
    if isinstance(antenna_obj, Antenna):
        return antenna_obj

    # Legacy object?
    if hasattr(antenna_obj, 'id') and hasattr(antenna_obj, 'position'):
        return Antenna.from_antenna_object(antenna_obj)

    return None
