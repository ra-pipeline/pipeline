"""Pydantic-based FluxMeasurement domain object prototype."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from pipeline.domain.measures import FluxDensity, FluxDensityUnits


class FluxMeasurement(BaseModel):
    """Pydantic-based flux measurement domain object."""

    spw_id: int
    I: FluxDensity
    Q: FluxDensity = FluxDensity(0)
    U: FluxDensity = FluxDensity(0)
    V: FluxDensity = FluxDensity(0)
    spix: Decimal = Decimal('0.0')
    uvmin: Decimal = Decimal('0.0')
    uvmax: Decimal = Decimal('0.0')
    origin: str | None = None
    age: str | None = None
    queried_at: str | None = None
    uncertainty: FluxMeasurement | None = None

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_default=True,
    )

    def __init__(
        self,
        spw_id: int | None = None,
        I: FluxDensity | int | float | Decimal | None = None,
        Q: FluxDensity | int | float | Decimal | None = None,
        U: FluxDensity | int | float | Decimal | None = None,
        V: FluxDensity | int | float | Decimal | None = None,
        spix: Decimal | int | float | None = None,
        uvmin: Decimal | int | float | None = None,
        uvmax: Decimal | int | float | None = None,
        **data: Any,
    ) -> None:
        """Create a FluxMeasurement.

        The legacy pipeline code frequently constructs flux measurements
        positionally, e.g. ``FluxMeasurement(spw_id, I, Q, U, V, spix, uvmin, uvmax)``.
        """
        if spw_id is not None and 'spw_id' not in data:
            data['spw_id'] = spw_id
        if I is not None and 'I' not in data:
            data['I'] = I

        # Optional Stokes parameters: only override defaults when explicitly provided.
        if Q is not None and 'Q' not in data:
            data['Q'] = Q
        if U is not None and 'U' not in data:
            data['U'] = U
        if V is not None and 'V' not in data:
            data['V'] = V

        if spix is not None and 'spix' not in data:
            data['spix'] = spix
        if uvmin is not None and 'uvmin' not in data:
            data['uvmin'] = uvmin
        if uvmax is not None and 'uvmax' not in data:
            data['uvmax'] = uvmax
        super().__init__(**data)

    @field_validator('spw_id', mode='before')
    @classmethod
    def _coerce_spw_id(cls, value: Any) -> int:
        return int(value)

    @field_validator('I', 'Q', 'U', 'V', mode='before')
    @classmethod
    def _coerce_flux(cls, value: Any) -> FluxDensity:
        if isinstance(value, FluxDensity):
            return FluxDensity(value.value, value.units)
        return FluxDensity(value, FluxDensityUnits.JANSKY)

    @field_validator('spix', 'uvmin', 'uvmax', mode='before')
    @classmethod
    def _coerce_decimal(cls, value: Any) -> Decimal:
        if isinstance(value, Decimal):
            return value
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        raise ValueError('Could not convert {!r} to Decimal'.format(value))

    @field_validator('age', 'queried_at', mode='before')
    @classmethod
    def _coerce_string(cls, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        # Convert other types (float, datetime, etc.) to string
        return str(value)

    @property
    def casa_flux_density(self) -> list[float]:
        """Return list of Stokes I, Q, U, and V flux densities in Jansky."""
        iquv = [
            self.I.to_units(FluxDensityUnits.JANSKY),
            self.Q.to_units(FluxDensityUnits.JANSKY),
            self.U.to_units(FluxDensityUnits.JANSKY),
            self.V.to_units(FluxDensityUnits.JANSKY),
        ]
        return list(map(float, iquv))

    def __str__(self) -> str:
        return (
            '<FluxMeasurement(Spw #{spw}, IQUV=({iquv}), spix={spix}, uvmin={uvmin}, '
            'uvmax={uvmax}, origin={origin}>'
        ).format(
            spw=self.spw_id,
            iquv=','.join(map(str, (self.I, self.Q, self.U, self.V))),
            spix=float(self.spix),
            uvmin=float(self.uvmin),
            uvmax=float(self.uvmax),
            origin=self.origin,
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.__class__,
                self.spw_id,
                float(self.I.to_units(FluxDensityUnits.JANSKY)),
                float(self.Q.to_units(FluxDensityUnits.JANSKY)),
                float(self.U.to_units(FluxDensityUnits.JANSKY)),
                float(self.V.to_units(FluxDensityUnits.JANSKY)),
                float(self.spix),
                float(self.uvmin),
                float(self.uvmax),
                self.origin,
                self.age,
                self.queried_at,
            )
        )

    def __add__(self, other: FluxMeasurement) -> FluxMeasurement:
        if not isinstance(other, self.__class__):
            raise TypeError(
                "unsupported operand type(s) for +: '%s' and '%s'"
                % (self.__class__.__name__, other.__class__.__name__)
            )

        return self.__class__(
            spw_id=self.spw_id,
            I=self.I + other.I,
            Q=self.Q + other.Q,
            U=self.U + other.U,
            V=self.V + other.V,
            spix=self.spix,
            uvmin=self.uvmin,
            uvmax=self.uvmax,
        )

    def __truediv__(self, other: int | float | Decimal) -> FluxMeasurement:
        if not isinstance(other, (int, float, Decimal)):
            raise TypeError(
                "unsupported operand type(s) for /: '%s' and '%s'"
                % (self.__class__.__name__, other.__class__.__name__)
            )

        return self.__class__(
            spw_id=self.spw_id,
            I=self.I / other,
            Q=self.Q / other,
            U=self.U / other,
            V=self.V / other,
            spix=self.spix,
            uvmin=self.uvmin,
            uvmax=self.uvmax,
        )

    def __mul__(self, other: int | float | Decimal) -> FluxMeasurement:
        if not isinstance(other, (int, float, Decimal)):
            raise TypeError(
                "unsupported operand type(s) for *: '%s' and '%s'"
                % (self.__class__.__name__, other.__class__.__name__)
            )

        return self.__class__(
            spw_id=self.spw_id,
            I=self.I * other,
            Q=self.Q * other,
            U=self.U * other,
            V=self.V * other,
            spix=self.spix,
            uvmin=self.uvmin,
            uvmax=self.uvmax,
        )

    def __rmul__(self, other: int | float | Decimal) -> FluxMeasurement:
        return self.__mul__(other)

    def to_dict(self) -> dict[str, Any]:
        """Export to dictionary with scalar flux densities in Jansky."""
        return {
            'spw_id': self.spw_id,
            'I': float(self.I.to_units(FluxDensityUnits.JANSKY)),
            'Q': float(self.Q.to_units(FluxDensityUnits.JANSKY)),
            'U': float(self.U.to_units(FluxDensityUnits.JANSKY)),
            'V': float(self.V.to_units(FluxDensityUnits.JANSKY)),
            'spix': float(self.spix),
            'uvmin': float(self.uvmin),
            'uvmax': float(self.uvmax),
            'origin': self.origin,
            'age': self.age,
            'queried_at': self.queried_at,
        }

    def to_json(self) -> str:
        """Export to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FluxMeasurement:
        """Create from dictionary."""
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> FluxMeasurement:
        """Create from JSON string."""
        return cls.model_validate_json(json_str)

    @classmethod
    def from_flux_measurement(cls, flux: Any) -> FluxMeasurement:
        """Create from legacy FluxMeasurement object for migration."""
        return cls(
            spw_id=flux.spw_id,
            I=flux.I,
            Q=flux.Q,
            U=flux.U,
            V=flux.V,
            spix=flux.spix,
            uvmin=flux.uvmin,
            uvmax=flux.uvmax,
            origin=flux.origin,
            age=flux.age,
            queried_at=flux.queried_at,
        )


def upgrade_flux_measurement(flux_obj: Any) -> FluxMeasurement | None:
    """Upgrade a legacy FluxMeasurement object to Pydantic version."""
    if isinstance(flux_obj, FluxMeasurement):
        return flux_obj

    if isinstance(flux_obj, FluxMeasurement):
        return FluxMeasurement.from_flux_measurement(flux_obj)

    return None
