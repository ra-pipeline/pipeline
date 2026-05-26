"""Pydantic-based unit formatting helpers."""

from __future__ import annotations

import bisect
import decimal
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field as PydanticField


class UnitOfMagnitude(BaseModel):
    """Models a unit of magnitude such as 'Kilobyte' or 'millimetre'."""

    magnitude: decimal.Decimal = PydanticField(..., description='Magnitude of the unit')
    format: str = PydanticField(..., description='Format string for rendering')
    html: str = PydanticField(..., description='HTML format string for rendering')

    model_config = ConfigDict(
        validate_default=True,
    )

    def __hash__(self) -> int:
        return hash((self.__class__, self.magnitude))

    def adjust(self, number: Any) -> decimal.Decimal:
        return decimal.Decimal(str(number)) / self.magnitude

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, UnitOfMagnitude):
            return False
        return self.magnitude == other.magnitude

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __lt__(self, other: UnitOfMagnitude) -> bool:
        return self.magnitude < other.magnitude

    def __le__(self, other: UnitOfMagnitude) -> bool:
        return self.magnitude <= other.magnitude

    def __gt__(self, other: UnitOfMagnitude) -> bool:
        return self.magnitude > other.magnitude

    def __ge__(self, other: UnitOfMagnitude) -> bool:
        return self.magnitude >= other.magnitude


class UnitFormat(BaseModel):
    """Utility for formatting values that are usually associated with a unit."""

    units: list[UnitOfMagnitude] = PydanticField(default_factory=list)
    prefer_integers: bool = PydanticField(default=False)

    model_config = ConfigDict(
        validate_default=True,
    )

    def __hash__(self) -> int:
        return hash((self.__class__, tuple(self.units)))

    def addUnitOfMagnitude(self, magnitude: Any, format: str, html: str | None = None) -> None:
        """Add a unit to this format.

        Args:
            magnitude: Magnitude of the unit relative to the base.
            format: Python format string for display.
            html: Optional HTML format string; defaults to format.
        """
        if html is None:
            html = format
        unit = UnitOfMagnitude(
            magnitude=decimal.Decimal(str(magnitude)),
            format=format,
            html=html,
        )
        bisect.insort(self.units, unit)

    def format(self, number: Any) -> str:
        best_unit = self.bestUnitForObject(number)
        number_adjusted = best_unit.adjust(number)
        return best_unit.format.format(number_adjusted)

    def html(self, number: Any) -> str:
        best_unit = self.bestUnitForObject(number)
        number_adjusted = best_unit.adjust(number)
        return best_unit.html.format(number_adjusted)

    def bestUnitForObject(self, number: Any) -> UnitOfMagnitude:
        if not self.units:
            raise LookupError()

        as_decimal = abs(decimal.Decimal(str(number)))

        default_units = [u for u in self.units if u.magnitude == 1][0]

        if as_decimal == 0:
            return default_units

        best_unit = default_units
        for unit in self.units:
            if as_decimal >= unit.magnitude:
                best_unit = unit

        if not self.prefer_integers:
            return best_unit

        try:
            next_best_unit = self.units[self.units.index(best_unit) - 1]
        except IndexError:
            return best_unit

        adjusted_best = best_unit.adjust(number)
        adjusted_next = next_best_unit.adjust(number)
        no_fraction_best = (adjusted_best % 1) == 0
        no_fraction_next = (adjusted_next % 1) == 0

        if not no_fraction_best and no_fraction_next:
            return next_best_unit
        return best_unit

    def to_dict(self) -> dict[str, Any]:
        """Export to dictionary."""
        return {
            'units': [u.model_dump() for u in self.units],
            'prefer_integers': self.prefer_integers,
        }

    def to_json(self) -> str:
        """Export to JSON string."""
        return json.dumps(self.to_dict())


file_size = UnitFormat()
file_size.addUnitOfMagnitude(1, '{0:.0f} bytes')
file_size.addUnitOfMagnitude(1024, '{0:.1f} KiB')
file_size.addUnitOfMagnitude(1024 * 1024, '{0:.1f} MiB')
file_size.addUnitOfMagnitude(1024 * 1024 * 1024, '{0:.1f} GiB')

distance = UnitFormat()
distance.addUnitOfMagnitude('.000001', '{0:.1f} &#181;m')
distance.addUnitOfMagnitude('.001', '{0:.1f} mm')
distance.addUnitOfMagnitude(1, '{0:.1f} m')
distance.addUnitOfMagnitude(1000, '{0:.1f} km')


def get_frequency_format(precision: int) -> UnitFormat:
    s = '{0:.' + str(precision) + 'f}'
    f = UnitFormat()
    f.addUnitOfMagnitude('.000001', s + ' &#181;Hz')
    f.addUnitOfMagnitude('.001', s + ' mHz')
    f.addUnitOfMagnitude(1, s + ' Hz')
    f.addUnitOfMagnitude(1000, s + ' kHz')
    f.addUnitOfMagnitude(1000000, s + ' MHz')
    f.addUnitOfMagnitude(1000000000, s + ' GHz')
    f.addUnitOfMagnitude(1000000000000, s + ' THz')
    return f


frequency = get_frequency_format(3)

flux = UnitFormat()
flux.addUnitOfMagnitude('.000000001', '{0:.3f} nJy')
flux.addUnitOfMagnitude('.000001', '{0:.3f} &#181;Jy')
flux.addUnitOfMagnitude('.001', '{0:.3f} mJy')
flux.addUnitOfMagnitude(1, '{0:.3f} Jy')
flux.addUnitOfMagnitude(1000, '{0:.3f} kJy')

energy = UnitFormat()
energy.addUnitOfMagnitude('.000000000000000000000001', '{0:.3f} yJ')
energy.addUnitOfMagnitude('.000000000000000000001', '{0:.3f} zJ')
energy.addUnitOfMagnitude('.000000000000000001', '{0:.3f} aJ')
energy.addUnitOfMagnitude('.000000000000001', '{0:.3f} fJ')
energy.addUnitOfMagnitude('.000000000001', '{0:.3f} pJ')
energy.addUnitOfMagnitude('.000000001', '{0:.3f} nJ')
energy.addUnitOfMagnitude('.000001', '{0:.3f} &#181;J')
energy.addUnitOfMagnitude('.001', '{0:.3f} mJ')
energy.addUnitOfMagnitude(1, '{0:.3f} J')
energy.addUnitOfMagnitude(1000, '{0:.3f} kJ')
energy.addUnitOfMagnitude(1000000, '{0:.3f} MJ')
energy.addUnitOfMagnitude(1000000000, '{0:.3f} GJ')
energy.addUnitOfMagnitude(1000000000000, '{0:.3f} TJ')
energy.addUnitOfMagnitude(1000000000000000, '{0:.3f} PJ')
energy.addUnitOfMagnitude(1000000000000000000, '{0:.3f} EJ')
energy.addUnitOfMagnitude(1000000000000000000000, '{0:.3f} ZJ')
energy.addUnitOfMagnitude(1000000000000000000000000, '{0:.3f} YJ')

velocity = UnitFormat()
velocity.addUnitOfMagnitude(1, '{0:.3f} m/s')
velocity.addUnitOfMagnitude(1000, '{0:.3f} km/s')

proper_motion = UnitFormat()
proper_motion.addUnitOfMagnitude(1, '{0:.3f} mas/yr')
proper_motion.addUnitOfMagnitude(1000, '{0:.3f} arcsec/yr')
proper_motion.addUnitOfMagnitude(60 * 1000, '{0:.3f} arcmin/yr')
proper_motion.addUnitOfMagnitude(60 * 60 * 1000, '{0:.3f} deg/yr')

temperature = UnitFormat()
temperature.addUnitOfMagnitude('.000000000000000000000001', '{0:.3f} yK')
temperature.addUnitOfMagnitude('.000000000000000000001', '{0:.3f} zK')
temperature.addUnitOfMagnitude('.000000000000000001', '{0:.3f} aK')
temperature.addUnitOfMagnitude('.000000000000001', '{0:.3f} fK')
temperature.addUnitOfMagnitude('.000000000001', '{0:.3f} pK')
temperature.addUnitOfMagnitude('.000000001', '{0:.3f} nK')
temperature.addUnitOfMagnitude('.000001', '{0:.3f} &#181;K')
temperature.addUnitOfMagnitude('.001', '{0:.3f} mK')
temperature.addUnitOfMagnitude(1, '{0:.3f} K')

arc = UnitFormat()
arc.addUnitOfMagnitude(1, '{0:.3f}\u00b0')
arc.addUnitOfMagnitude(1 / 60, '{0:.3f}\u2032')
arc.addUnitOfMagnitude(1 / 3600, '{0:.3f}\u2033')
arc.addUnitOfMagnitude(1 / 3600000, '{0:.3f} mas')
arc.addUnitOfMagnitude(1 / 3600000000, '{0:.3f} &#181;as')

time = UnitFormat()
time.addUnitOfMagnitude('.001', '{0:.0f} ms')
time.addUnitOfMagnitude(1, '{0:.1f} s')
time.addUnitOfMagnitude(60, '{0:.0f} mins')
