"""Pydantic-based Field domain object prototype for Phase 5 modernization."""

from __future__ import annotations

import datetime
import json
import pprint
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field as PydanticField

from pipeline.infrastructure import casa_tools, utils

_pprinter = pprint.PrettyPrinter(width=1e99)


class Field(BaseModel):
    """Pydantic-based field domain object.

    Attributes:
        id: Field identifier within the FIELD subtable.
        source_id: Source identifier associated with the field.
        time: Array of unique observation times for this field.
        name_raw: Raw field name (unescaped).
        direction: CASA direction measure dictionary for the field phase center.
        intents: Scan intents associated with the field.
        states: State objects associated with the field.
        valid_spws: SpectralWindow objects associated with the field.
        flux_densities: Flux measurements associated with the field.
        zd: Zenith distance quantity dictionary.
        telmjd: Modified Julian Date epoch dictionary.
    """

    id: int = PydanticField(..., description='Field identifier')
    source_id: int = PydanticField(..., description='Associated source identifier')
    time: np.ndarray = PydanticField(..., description='Unique observation times')
    name_raw: str = PydanticField(..., alias='name', description='Raw field name')
    direction: dict[str, Any] = PydanticField(..., description='CASA direction measure')
    intents: set[str] = PydanticField(default_factory=set, description='Scan intents')
    states: set[Any] = PydanticField(default_factory=set, description='State objects')
    valid_spws: set[Any] = PydanticField(default_factory=set, description='Valid spectral windows')
    flux_densities: set[Any] = PydanticField(
        default_factory=set,
        description='Flux density measurements',
    )
    source: Any | None = PydanticField(default=None, exclude=True, description='Linked source object')
    zd: dict[str, Any] | None = PydanticField(default=None, description='Zenith distance')
    telmjd: dict[str, Any] | None = PydanticField(default=None, description='TELMJD epoch')

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        validate_default=True,
    )

    def __repr__(self) -> str:
        name = self.name
        if '"' in name:
            name = name[1:-1]

        return 'Field({0}, {1!r}, {2}, {3}, {4})'.format(
            self.id,
            name,
            self.source_id,
            'numpy.array(%r)' % self.time.tolist(),
            _pprinter.pformat(self.direction),
        )

    def __hash__(self) -> int:
        return hash((self.__class__, self.id, self.source_id, self.name_raw))

    @property
    def clean_name(self) -> str:
        """Return field name with illegal characters replaced."""
        return utils.fieldname_clean(self.name_raw)

    @property
    def dec(self) -> str:
        """Return declination for the phasecenter of the field."""
        return casa_tools.quanta.formxxx(self.latitude, format='dms', prec=2)

    @property
    def frame(self) -> str:
        """Return reference frame code for the Field."""
        return self.direction['refer']

    @property
    def identifier(self) -> str:
        """Return a human-readable identifier for this Field."""
        return self.name if self.name else '#{0}'.format(self.id)

    @property
    def latitude(self) -> dict[str, Any]:
        """Return latitude for the phasecenter of the field."""
        return self.direction['m1']

    @property
    def longitude(self) -> dict[str, Any]:
        """Return longitude for the phasecenter of the field."""
        return self.direction['m0']

    @property
    def mdirection(self) -> dict[str, Any]:
        """Return direction measure dictionary for phasecenter of the field."""
        return self.direction

    @property
    def name(self) -> str:
        """Return name of field, in form that can be used as a CASA argument."""
        return utils.fieldname_for_casa(self.name_raw)

    @name.setter
    def name(self, value: str) -> None:
        """Set name of field to given value."""
        self.name_raw = value

    @property
    def ra(self) -> str:
        """Return right ascension for the phasecenter of the field."""
        return casa_tools.quanta.formxxx(self.longitude, format='hms', prec=3)

    @property
    def gl(self) -> str:
        """Return longitude for phasecenter of the field, in DMS format."""
        return casa_tools.quanta.formxxx(self.longitude, format='dms', prec=2)

    @property
    def gb(self) -> str:
        """Return declination for the phasecenter of the field."""
        return self.dec

    def set_source_type(self, source_type: str) -> None:
        """Update intents based on given source type(s)."""
        source_type = source_type.strip().upper()

        source_type = source_type.replace('SOURCE', 'TARGET')
        source_type = source_type.replace('GAIN', 'PHASE')
        source_type = source_type.replace('FLUX', 'AMPLITUDE')

        for intent in [
            'BANDPASS',
            'PHASE',
            'AMPLITUDE',
            'TARGET',
            'POINTING',
            'WVR',
            'ATMOSPHERE',
            'SIDEBAND',
            'POLARIZATION',
            'POLANGLE',
            'POLLEAKAGE',
            'CHECK',
            'DIFFGAINREF',
            'DIFFGAINSRC',
            'UNKNOWN',
            'SYSTEM_CONFIGURATION',
        ]:
            if source_type.find(intent) != -1:
                self.intents.add(intent)

    def set_zd_telmjd(self, observatory: str) -> None:
        """Calculate and set the zenith distance at the observation mid-time."""
        mjd_epoch = datetime.datetime(1858, 11, 17)
        start_time = mjd_epoch + datetime.timedelta(seconds=min(self.time))
        end_time = mjd_epoch + datetime.timedelta(seconds=max(self.time))
        mid_time = utils.obs_midtime(start_time, end_time)

        zd_rad = utils.compute_zenith_distance(
            field_direction=self.direction,
            epoch=mid_time,
            observatory=observatory,
        )

        self.zd = casa_tools.quanta.convert(zd_rad, 'deg')
        self.telmjd = mid_time['m0']

    def __str__(self) -> str:
        return '<Field {id}: name=\'{name}\' intents=\'{intents}\'>'.format(
            id=self.identifier,
            name=self.name,
            intents=','.join(self.intents),
        )

    def to_dict(self) -> dict[str, Any]:
        """Export to dictionary (data fields only)."""
        data = self.model_dump(
            by_alias=True,
            exclude={'intents', 'states', 'valid_spws', 'flux_densities'},
        )
        if isinstance(data.get('time'), np.ndarray):
            data['time'] = data['time'].tolist()
        return data

    def to_json(self) -> str:
        """Export to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Field:
        """Create from dictionary."""
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> Field:
        """Create from JSON string."""
        return cls.model_validate_json(json_str)

    @classmethod
    def from_field_object(cls, field: Any) -> Field:
        """Create from legacy Field-like object for migration."""
        name = getattr(field, '_name', None)
        if name is None:
            name = getattr(field, 'name', None)

        direction = getattr(field, 'mdirection', None)
        if direction is None:
            direction = getattr(field, 'direction', None)

        field_id = getattr(field, 'id', None)
        if field_id is None:
            field_id = getattr(field, 'field_id', None)

        return cls(
            id=field_id,
            source_id=getattr(field, 'source_id', None),
            time=getattr(field, 'time', None),
            name=name,
            direction=direction,
            intents=getattr(field, 'intents', set()),
            states=getattr(field, 'states', set()),
            valid_spws=getattr(field, 'valid_spws', set()),
            flux_densities=getattr(field, 'flux_densities', set()),
            zd=getattr(field, 'zd', None),
            telmjd=getattr(field, 'telmjd', None),
        )


def upgrade_field(field_obj: Any) -> Field | None:
    """Upgrade a legacy Field-like object to Pydantic version."""
    if isinstance(field_obj, Field):
        return field_obj

    if field_obj is None:
        return None

    if hasattr(field_obj, 'id') or hasattr(field_obj, 'field_id'):
        return Field.from_field_object(field_obj)

    return None
