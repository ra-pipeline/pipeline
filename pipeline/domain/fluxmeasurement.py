# Do not evaluate type annotations at definition time.
from __future__ import annotations

from decimal import Decimal

from .measures import FluxDensity, FluxDensityUnits


class FluxMeasurement(object):
    """
    FluxMeasurement is a logical representation of a flux measurement.

    Attributes:
        spw_id: ID of spectral window associated with flux measurement.
        I: Stokes I flux density as FluxDensity object.
        Q: Stokes Q flux density as FluxDensity object.
        U: Stokes U flux density as FluxDensity object.
        V: Stokes V flux density as FluxDensity object.
        spix: Spectral index of the flux measurement.
        uvmin: Scale (in klambda) of the measured (large scale) extent of the
            flux source (if greater than zero).
        uvmax: Scale (in klambda) where (small scale) structure has been
            measured within the flux source, or a limit on the resolved
            structure.
        origin: Origin of the flux measurement.
        age: Age of the flux measurement.
        queried_at: Date-timestamp when flux measurement was queried (e.g. from
            catalog service).
    """
    def __init__(self,
                 spw_id: int | str,
                 I: int | float | FluxDensity,
                 Q: int | float | FluxDensity = FluxDensity(0),
                 U: int | float | FluxDensity = FluxDensity(0),
                 V: int | float | FluxDensity = FluxDensity(0),
                 spix: Decimal = Decimal('0.0'),
                 uvmin: Decimal = Decimal('0.0'),
                 uvmax: Decimal = Decimal('0.0'),
                 origin: str | None = None,
                 age: str | None = None,
                 queried_at: str | None = None) -> None:
        """
        Initialize a FluxMeasurement object.

        ``uvmin`` and ``uvmax`` are properties in the calibrator source catalog,
        see e.g. https://almascience.nrao.edu/alma-data/calibrator-catalogue.

        Args:
            spw_id: ID of spectral window associated with flux measurement, as
                integer or string representation of integer.
            I: Stokes I flux density, either as int/float (assumed to be flux
                density in Jansky) or a FluxDensity object.
            Q: Stokes Q flux density, either as int/float (assumed to be flux
                density in Jansky) or a FluxDensity object; optional, defaults
                to 0 Jansky.
            U: Stokes U flux density, either as int/float (assumed to be flux
                density in Jansky) or a FluxDensity object; optional, defaults
                to 0 Jansky.
            V: Stokes V flux density, either as int/float (assumed to be flux
                density in Jansky) or a FluxDensity object; optional, defaults
                to 0 Jansky.
            spix: Spectral index of the flux measurement; optional, defaults to 0.
            uvmin: Scale (in klambda) of the measured (large scale) extent of
                the flux source (if greater than zero); optional, defaults to 0.
            uvmax: Scale (in klambda) where (small scale) structure has been
                measured within the flux source, or a limit on the resolved
                structure; optional, defaults to 0.
            origin: Origin of the flux measurement; optional, defaults to None.
            age: Age of the flux measurement; optional, defaults to None.
            queried_at: Date-timestamp when flux measurement was queried (e.g.
                from catalog service); optional, defaults to None.
        """
        self.spw_id = int(spw_id)
        self.I = self._to_flux_density(I)
        self.Q = self._to_flux_density(Q)
        self.U = self._to_flux_density(U)
        self.V = self._to_flux_density(V)
        self.spix = self._to_decimal(spix)
        self.uvmin = self._to_decimal(uvmin)
        self.uvmax = self._to_decimal(uvmax)
        self.origin = origin
        self.age = age
        self.queried_at = queried_at

    @staticmethod
    def _to_flux_density(arg: int | float | FluxDensity) -> FluxDensity:
        """
        Return arg as a new FluxDensity. If arg is a number, it is assumed to
        be the flux density in Jy.
        """
        if isinstance(arg, FluxDensity):
            # create defensive copies of the flux arguments so they're not
            # shared between instances
            return FluxDensity(arg.value, arg.units)

        try:
            return FluxDensity(arg, FluxDensityUnits.JANSKY)
        except:
            raise ValueError('Could not convert {!r} to FluxDensity'.format(arg))

    @staticmethod
    def _to_decimal(arg: int | float | Decimal) -> Decimal:
        """Return arg as a Decimal."""
        if isinstance(arg, Decimal):
            return arg
        elif isinstance(arg, (int, float)):
            return Decimal(list(map(str, arg)))
        else:
            raise ValueError('Could not convert {!r} to Decimal'.format(arg))

    @property
    def casa_flux_density(self) -> list[float]:
        """Return list of Stokes I, Q, U, and V flux densities in Jansky."""
        iquv = [self.I.to_units(FluxDensityUnits.JANSKY),
                self.Q.to_units(FluxDensityUnits.JANSKY),
                self.U.to_units(FluxDensityUnits.JANSKY),
                self.V.to_units(FluxDensityUnits.JANSKY)]
        return list(map(float, iquv))

    def __str__(self) -> str:
        return '<FluxMeasurement(Spw #{spw}, IQUV=({iquv}), spix={spix}, uvmin={uvmin}, uvmax={uvmax}, origin={origin}>'.format(
            spw=self.spw_id,
            iquv=','.join(map(str, (self.I, self.Q, self.U, self.V))),
            spix=float(self.spix),
            uvmin=float(self.uvmin),
            uvmax=float(self.uvmax),
            origin=self.origin
        )

    def __add__(self, other: FluxMeasurement) -> FluxMeasurement:
        if not isinstance(other, self.__class__):
            raise TypeError("unsupported operand type(s) for +: '%s' and '%s'" % (self.__class__.__name__,
                                                                                  other.__class__.__name__))

        spw_id = self.spw_id
        I = self.I + other.I
        Q = self.Q + other.Q
        U = self.U + other.U
        V = self.V + other.V
        spix = self.spix
        uvmin = self.uvmin
        uvmax = self.uvmax

        return self.__class__(spw_id, I, Q, U, V, spix, uvmin, uvmax)

    def __truediv__(self, other: FluxMeasurement) -> FluxMeasurement:
        if not isinstance(other, (int, float, Decimal)):
            raise TypeError("unsupported operand type(s) for /: '%s' and '%s'" % (self.__class__.__name__,
                                                                                  other.__class__.__name__))

        spw_id = self.spw_id
        I = self.I / other
        Q = self.Q / other
        U = self.U / other
        V = self.V / other
        spix = self.spix
        uvmin = self.uvmin
        uvmax = self.uvmax

        return self.__class__(spw_id, I, Q, U, V, spix, uvmin, uvmax)

    def __mul__(self, other: FluxMeasurement) -> FluxMeasurement:
        if not isinstance(other, (int, float, Decimal)):
            raise TypeError("unsupported operand type(s) for *: '%s' and '%s'" % (self.__class__.__name__,
                                                                                  other.__class__.__name__))

        spw_id = self.spw_id
        I = self.I * other
        Q = self.Q * other
        U = self.U * other
        V = self.V * other
        spix = self.spix
        uvmin = self.uvmin
        uvmax = self.uvmax

        return self.__class__(spw_id, I, Q, U, V, spix, uvmin, uvmax,)

    def __rmul__(self, other: FluxMeasurement) -> FluxMeasurement:
        if not isinstance(other, (int, float, Decimal)):
            raise TypeError("unsupported operand type(s) for *: '%s' and '%s'" % (self.__class__.__name__,
                                                                                  other.__class__.__name__))

        spw_id = self.spw_id
        I = self.I * other
        Q = self.Q * other
        U = self.U * other
        V = self.V * other
        spix = self.spix
        uvmin = self.uvmin
        uvmax = self.uvmax

        return self.__class__(spw_id, I, Q, U, V, spix, uvmin, uvmax)
