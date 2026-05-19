# Do not evaluate type annotations at definition time.
from __future__ import annotations

import abc
import datetime
import decimal
import math
import re
import numbers
from typing import Any

import pipeline.infrastructure.utils as utils

from . import unitformat


class ArcUnits:
    DEGREE           = { 'name' : 'DEGREE'           , 'symbol' : 'd'   , 'html' : '&#x00B0;' , 'units per circle' : decimal.Decimal(360)        }
    RADIAN           = { 'name' : 'RADIAN'           , 'symbol' : 'rad' , 'html' : 'rad'      , 'units per circle' : decimal.Decimal(str(2*math.pi))  }
    PERCENT          = { 'name' : 'PERCENT'          , 'symbol' : '%'   , 'html' : '&#x0025;' , 'units per circle' : decimal.Decimal(100)        }
    HOUR             = { 'name' : 'HOUR'             , 'symbol' : 'h'   , 'html' : 'h'        , 'units per circle' : decimal.Decimal(24)         }
    MINUTE           = { 'name' : 'MINUTE'           , 'symbol' : 'm'   , 'html' : 'm'        , 'units per circle' : decimal.Decimal(1440)       }
    SECOND           = { 'name' : 'SECOND'           , 'symbol' : 's'   , 'html' : 's'        , 'units per circle' : decimal.Decimal(86400)      }
    ARC_MINUTE       = { 'name' : 'ARC_MINUTE'       , 'symbol' : "'"   , 'html' : '&#x0027;' , 'units per circle' : decimal.Decimal(21600)      }
    ARC_SECOND       = { 'name' : 'ARC_SECOND'       , 'symbol' : '"'   , 'html' : '&quot;'   , 'units per circle' : decimal.Decimal(1296000)    }
    MILLI_ARC_SECOND = { 'name' : 'MILLI_ARC_SECOND' , 'symbol' : 'mas' , 'html' : 'mas'      , 'units per circle' : decimal.Decimal(1296000000) }


class DistanceUnits:
    ANGSTROM          = { 'name' : 'ANGSTROM'          , 'symbol' : '\\u212B', 'metres' : decimal.Decimal('1e-10')              }
    NANOMETRE         = { 'name' : 'NANOMETRE'         , 'symbol' : 'nm'     , 'metres' : decimal.Decimal('1e-9')               }
    MICROMETRE        = { 'name' : 'MICROMETRE'        , 'symbol' : '\\u00B5m', 'metres' : decimal.Decimal('1e-6')               }
    MILLIMETRE        = { 'name' : 'MILLIMETRE'        , 'symbol' : 'mm'     , 'metres' : decimal.Decimal('0.001')              }
    CENTIMETRE        = { 'name' : 'CENTIMETRE'        , 'symbol' : 'cm'     , 'metres' : decimal.Decimal('0.01')               }
    METRE             = { 'name' : 'METRE'             , 'symbol' : 'm'      , 'metres' : decimal.Decimal(1)                    }
    KILOMETRE         = { 'name' : 'KILOMETRE'         , 'symbol' : 'km'     , 'metres' : decimal.Decimal(1000)                 }
    MILE              = { 'name' : 'MILE'              , 'symbol' : 'mi'     , 'metres' : decimal.Decimal('1609.347219')        }
    ASTRONOMICAL_UNIT = { 'name' : 'ASTRONOMICAL_UNIT' , 'symbol' : 'au'     , 'metres' : decimal.Decimal(149597870691)         }
    LIGHT_SECOND      = { 'name' : 'LIGHT_SECOND'      , 'symbol' : 'ls'     , 'metres' : decimal.Decimal(299792458)            }
    LIGHT_MINUTE      = { 'name' : 'LIGHT_MINUTE'      , 'symbol' : 'lm'     , 'metres' : decimal.Decimal(17987547480)          }
    LIGHT_YEAR        = { 'name' : 'LIGHT_YEAR'        , 'symbol' : 'ly'     , 'metres' : decimal.Decimal('9.4607304725808e15') }
    PARSEC            = { 'name' : 'PARSEC'            , 'symbol' : 'pc'     , 'metres' : decimal.Decimal('3.085677581306e16')  }
    KILOPARSEC        = { 'name' : 'KILOPARSEC'        , 'symbol' : 'kpc'    , 'metres' : decimal.Decimal('3.085677581306e19')  }
    MEGAPARSEC        = { 'name' : 'MEGAPARSEC'        , 'symbol' : 'Mpc'    , 'metres' : decimal.Decimal('3.085677581306e22')  }


class FluxDensityUnits:
    YOCTOJANSKY = { 'name' : 'YOCTOJANSKY' , 'symbol' : 'yJy'      , 'Jy' : decimal.Decimal('1e-24') }
    ZEPTOJANSKY = { 'name' : 'ZEPTOJANSKY' , 'symbol' : 'zJy'      , 'Jy' : decimal.Decimal('1e-21') }
    ATTOJANSKY  = { 'name' : 'ATTOJANSKY'  , 'symbol' : 'aJy'      , 'Jy' : decimal.Decimal('1e-18') }
    FEMTOJANSKY = { 'name' : 'FEMTOJANSKY' , 'symbol' : 'fJy'      , 'Jy' : decimal.Decimal('1e-15') }
    PICOJANSKY  = { 'name' : 'PICOJANSKY'  , 'symbol' : 'pJy'      , 'Jy' : decimal.Decimal('1e-12') }
    NANOJANSKY  = { 'name' : 'NANOJANSKY'  , 'symbol' : 'nJy'      , 'Jy' : decimal.Decimal('1e-9')  }
    MICROJANSKY = { 'name' : 'MICROJANSKY' , 'symbol' : '\\u03BCJy', 'Jy' : decimal.Decimal('1e-6')  }
    MILLIJANSKY = { 'name' : 'MILLIJANSKY' , 'symbol' : 'mJy'      , 'Jy' : decimal.Decimal('0.001') }
    CENTIJANSKY = { 'name' : 'CENTIJANSKY' , 'symbol' : 'cJy'      , 'Jy' : decimal.Decimal('0.01')  }
    DECIJANSKY  = { 'name' : 'DECIJANSKY'  , 'symbol' : 'dJy'      , 'Jy' : decimal.Decimal('0.1')   }
    JANSKY      = { 'name' : 'JANSKY'      , 'symbol' : 'Jy'       , 'Jy' : decimal.Decimal(1)       }
    DECAJANSKY  = { 'name' : 'DECAJANSKY'  , 'symbol' : 'daJy'     , 'Jy' : decimal.Decimal(10)      }
    HECTOJANSKY = { 'name' : 'HECTOJANSKY' , 'symbol' : 'hJy'      , 'Jy' : decimal.Decimal(100)     }
    KILOJANSKY  = { 'name' : 'KILOJANSKY'  , 'symbol' : 'kJy'      , 'Jy' : decimal.Decimal(1000)    }
    MEGAJANSKY  = { 'name' : 'MEGAJANSKY'  , 'symbol' : 'MJy'      , 'Jy' : decimal.Decimal('1e6')   }
    GIGAJANSKY  = { 'name' : 'GIGAJANSKY'  , 'symbol' : 'GJy'      , 'Jy' : decimal.Decimal('1e9')   }
    TERAJANSKY  = { 'name' : 'TERAJANSKY'  , 'symbol' : 'TJy'      , 'Jy' : decimal.Decimal('1e12')  }
    PETAJANSKY  = { 'name' : 'PETAJANSKY'  , 'symbol' : 'PJy'      , 'Jy' : decimal.Decimal('1e15')  }
    ETAJANSKY   = { 'name' : 'ETAJANSKY'   , 'symbol' : 'EJy'      , 'Jy' : decimal.Decimal('1e18')  }
    ZETTAJANSKY = { 'name' : 'ZETTAJANSKY' , 'symbol' : 'ZJy'      , 'Jy' : decimal.Decimal('1e21')  }
    YOTTAJANSKY = { 'name' : 'YOTTAJANSKY' , 'symbol' : 'YJy'      , 'Jy' : decimal.Decimal('1e24')  }


class FrequencyUnits:
    YOCTOHERTZ = { 'name' : 'YOCTOHERTZ' , 'symbol' : 'yHz'      , 'hz' : decimal.Decimal('1e-24') }
    ZEPTOHERTZ = { 'name' : 'ZEPTOHERTZ' , 'symbol' : 'zHz'      , 'hz' : decimal.Decimal('1e-21') }
    ATTOHERTZ  = { 'name' : 'ATTOHERTZ'  , 'symbol' : 'aHz'      , 'hz' : decimal.Decimal('1e-18') }
    FEMTOHERTZ = { 'name' : 'FEMTOHERTZ' , 'symbol' : 'fHz'      , 'hz' : decimal.Decimal('1e-15') }
    PICOHERTZ  = { 'name' : 'PICOHERTZ'  , 'symbol' : 'pHz'      , 'hz' : decimal.Decimal('1e-12') }
    NANOHERTZ  = { 'name' : 'NANOHERTZ'  , 'symbol' : 'nHz'      , 'hz' : decimal.Decimal('1e-9')  }
    MICROHERTZ = { 'name' : 'MICROHERTZ' , 'symbol' : '\\u03BCHz', 'hz' : decimal.Decimal('1e-6')  }
    MILLIHERTZ = { 'name' : 'MILLIHERTZ' , 'symbol' : 'mHz'      , 'hz' : decimal.Decimal('0.001') }
    CENTIHERTZ = { 'name' : 'CENTIHERTZ' , 'symbol' : 'cHz'      , 'hz' : decimal.Decimal('0.01')  }
    DECIHERTZ  = { 'name' : 'DECIHERTZ'  , 'symbol' : 'dHz'      , 'hz' : decimal.Decimal('0.1')   }
    HERTZ      = { 'name' : 'HERTZ'      , 'symbol' : 'Hz'       , 'hz' : decimal.Decimal(1)       }
    DECAHERTZ  = { 'name' : 'DECAHERTZ'  , 'symbol' : 'daHz'     , 'hz' : decimal.Decimal(10)      }
    HECTOHERTZ = { 'name' : 'HECTOHERTZ' , 'symbol' : 'hHz'      , 'hz' : decimal.Decimal(100)     }
    KILOHERTZ  = { 'name' : 'KILOHERTZ'  , 'symbol' : 'kHz'      , 'hz' : decimal.Decimal(1000)    }
    MEGAHERTZ  = { 'name' : 'MEGAHERTZ'  , 'symbol' : 'MHz'      , 'hz' : decimal.Decimal('1e6')   }
    GIGAHERTZ  = { 'name' : 'GIGAHERTZ'  , 'symbol' : 'GHz'      , 'hz' : decimal.Decimal('1e9')   }
    TERAHERTZ  = { 'name' : 'TERAHERTZ'  , 'symbol' : 'THz'      , 'hz' : decimal.Decimal('1e12')  }
    PETAHERTZ  = { 'name' : 'PETAHERTZ'  , 'symbol' : 'PHz'      , 'hz' : decimal.Decimal('1e15')  }
    ETAHERTZ   = { 'name' : 'ETAHERTZ'   , 'symbol' : 'EHz'      , 'hz' : decimal.Decimal('1e18')  }
    ZETTAHERTZ = { 'name' : 'ZETTAHERTZ' , 'symbol' : 'ZHz'      , 'hz' : decimal.Decimal('1e21')  }
    YOTTAHERTZ = { 'name' : 'YOTTAHERTZ' , 'symbol' : 'YHz'      , 'hz' : decimal.Decimal('1e24')  }


class LinearVelocityUnits:
    METRES_PER_SECOND     = { 'name' : 'METRES_PER_SECOND'     , 'symbol' : 'm/s'  , 'mps' : decimal.Decimal(1)         }
    KILOMETRES_PER_SECOND = { 'name' : 'KILOMETERS_PER_SECOND' , 'symbol' : 'km/s' , 'mps' : decimal.Decimal(1000)      }
    Z                     = { 'name' : 'Z'                     , 'symbol' : 'Z'    , 'mps' : decimal.Decimal(299792458) }


class FileSizeUnits:
    BYTES     = { 'name' : 'BYTES'    , 'symbol' : 'b' , 'bytes' : decimal.Decimal(1)               }
    KILOBYTES = { 'name' : 'KILOBYTES', 'symbol' : 'kb', 'bytes' : decimal.Decimal('1024')          }
    MEGABYTES = { 'name' : 'MEGABYTES', 'symbol' : 'Mb', 'bytes' : decimal.Decimal('1048576')       }
    GIGABYTES = { 'name' : 'GIGABYTES', 'symbol' : 'Gb', 'bytes' : decimal.Decimal('1073741824')    }
    TERABYTES = { 'name' : 'TERABYTES', 'symbol' : 'Tb', 'bytes' : decimal.Decimal('1099511627776') }


class ComparableUnit(abc.ABC):
    __slots__ = ('value', 'units')

    def __getstate__(self):
        return self.value, self.units

    def __setstate__(self, state) -> None:
        self.value, self.units = state

    @abc.abstractmethod
    def __init__(self, value: Any, units: Any) -> None:
        raise Exception('Must override __init__ of ComparableUnit')

    def __eq__(self, other: ComparableUnit) -> bool:
        if not isinstance(other, self.__class__):
            return False
        return other.to_units(self.units) == self.value

    def __ne__(self, other: ComparableUnit) -> bool:
        return not self.__eq__(other)

    def __abs__(self) -> ComparableUnit:
        if self.value < 0:
            return self.__class__(-self.value, self.units)
        else:
            return self.__class__(self.value, self.units)

    def __add__(self, other: ComparableUnit):
        if not isinstance(other, self.__class__):
            raise TypeError("unsupported operand type(s) for +: '%s' and '%s'" % (self.__class__.__name__,
                                                                                  other.__class__.__name__))
        return self.__class__(other.to_units(self.units) + self.value, self.units)

    def __truediv__(self, other: ComparableUnit | numbers.Number) -> ComparableUnit:
        if isinstance(other, self.__class__):
            return self.to_units() / other.to_units()
        if not isinstance(other, numbers.Number):
            raise TypeError("unsupported operand type(s) for /: '%s' and '%s'" % (self.__class__.__name__,
                                                                                  other.__class__.__name__))
        return self.__class__(self.value / decimal.Decimal(str(other)), self.units)

    def __floordiv__(self, other: ComparableUnit | numbers.Number) -> ComparableUnit:
        if isinstance(other, self.__class__):
            return self.to_units() // other.to_units()
        if not isinstance(other, numbers.Number):
            raise TypeError("unsupported operand type(s) for //: '%s' and '%s'" % (self.__class__.__name__,
                                                                                   other.__class__.__name__))
        return self.__class__(self.value // decimal.Decimal(str(other)), self.units)

    def __ge__(self, other: ComparableUnit) -> bool:
        if not isinstance(other, self.__class__):
            raise TypeError("unsupported operand type(s) for >=: '%s' and '%s'" % (self.__class__.__name__,
                                                                                   other.__class__.__name__))
        return self.value >= other.to_units(self.units)

    def __gt__(self, other: ComparableUnit) -> bool:
        if not isinstance(other, self.__class__):
            raise TypeError("unsupported operand type(s) for >: '%s' and '%s'" % (self.__class__.__name__,
                                                                                  other.__class__.__name__))
        return self.value > other.to_units(self.units)

    def __itruediv__(self, other: numbers.Number) -> ComparableUnit:
        if not isinstance(other, numbers.Number):
            raise TypeError("unsupported operand type(s) for /=: '%s' and '%s'" % (self.__class__.__name__,
                                                                                   other.__class__.__name__))
        self.value /= other
        return self

    def __ifloordiv__(self, other: numbers.Number) -> ComparableUnit:
        if not isinstance(other, numbers.Number):
            raise TypeError("unsupported operand type(s) for //=: '%s' and '%s'" % (self.__class__.__name__,
                                                                                   other.__class__.__name__))
        self.value //= other
        return self

    def __le__(self, other: ComparableUnit) -> bool:
        if not isinstance(other, self.__class__):
            raise TypeError("unsupported operand type(s) for <=: '%s' and '%s'" % (self.__class__.__name__,
                                                                                   other.__class__.__name__))
        return self.value <= other.to_units(self.units)

    def __lt__(self, other: ComparableUnit) -> bool:
        if not isinstance(other, self.__class__):
            raise TypeError("unsupported operand type(s) for <: '%s' and '%s'" % (self.__class__.__name__,
                                                                                  other.__class__.__name__))
        return self.value < other.to_units(self.units)

    def __mul__(self, other: numbers.Number) -> ComparableUnit:
        if not isinstance(other, numbers.Number):
            raise TypeError("unsupported operand type(s) for *: '%s' and '%s'" % (self.__class__.__name__,
                                                                                  other.__class__.__name__))
        return self.__class__(self.value * other, self.units)

    def __rmul__(self, other):
        if not isinstance(other, numbers.Number):
            raise TypeError("unsupported operand type(s) for *: '%s' and '%s'" % (self.__class__.__name__,
                                                                                  other.__class__.__name__))
        return self.__class__(self.value * other, self.units)

    def __repr__(self) -> str:
        return '%s %s' % (self.value, self.units['symbol'])

    def __sub__(self, other):
        if not isinstance(other, self.__class__):
            raise TypeError("unsupported operand type(s) for -: '%s' and '%s'" % (self.__class__.__name__,
                                                                                  other.__class__.__name__))
        return self.__class__(self.value - other.to_units(self.units), self.units)

    @abc.abstractmethod
    def convert_to(self, newUnits: dict):
        raise Exception('Must override convert_to of ComparableUnit')

    @abc.abstractmethod
    def to_units(self, otherUnits: dict):
        raise Exception('Must override to_units of ComparableUnit')


class Distance(ComparableUnit):
    def __init__(self, value: int | float | decimal.Decimal = 0, units: dict = DistanceUnits.KILOMETRE) -> None:
        """Creates a new distance with the given magnitude and units.

        If no arguments are given, a new distance of 0 km is created. If no
        units are given, kilometres are assumed.
        """
        if isinstance(value, (float, int)):
            value = str(value)
        self.value = decimal.Decimal(value)
        self.units = units

    def convert_to(self, newUnits: dict = DistanceUnits.METRE) -> Distance:
        """Converts this measure of distance to the new units.

        After this method is complete this distance will have units of newUnits
        and its value will have been converted accordingly.

        Args:
            newUnits: The new units for this distance (default: m).

        Returns:
            This distance. The reason for this return type is to allow code of
            this nature:

            kilometers = myDistance.convert_to(DistanceUnits.KILOMETRES).value
        """
        self.value = self.to_units(newUnits)
        self.units = newUnits
        return self

    def to_units(self, otherUnits: dict = DistanceUnits.METRE) -> decimal.Decimal:
        """Returns the magnitude of this distance in otherUnits.

        Note that this method does not alter the state of this distance.
        Contrast this with convert_to(DistanceUnits).

        Args:
            otherUnits: The units in which to express this distance's magnitude.

        Returns:
            This distance's value converted to otherUnits.
        """
        factor = self.units['metres'] / otherUnits['metres']
        return self.value * factor

    def __str__(self) -> str:
        return unitformat.distance.format(self.to_units(DistanceUnits.METRE))

    def __repr__(self) -> str:
        return 'Distance(%s, DistanceUnits.%s)' % (self.value,
                                                   self.units['name'])


class EquatorialArc(ComparableUnit):
    def __init__(self, value: int | float | decimal.Decimal = 0, units: dict = ArcUnits.DEGREE) -> None:
        """Creates a new equatorial arc with the given magnitude and units.

        If no arguments are given, a new arc of 0 degrees is created. If no
        units are given, degrees are assumed.

        Args:
            value: The magnitude for this arc.
            units: The new units for this arc.
        """
        if isinstance(value, (float, int)):
            value = str(value)
        self.value = decimal.Decimal(value)
        self.units = units

    def convert_to(self, newUnits: dict = ArcUnits.DEGREE) -> EquatorialArc:
        """Converts this arc to the new units.

        After this method is complete this arc will have units of units and its
        value will have been converted accordingly.

        Args:
            newUnits: The new units for this arc. Default: degrees.

        Returns:
            This arc. The reason for this return type is to allow code of this
            nature:

            radians = myArc.convert_to(ArcUnits.RADIAN).value;
        """
        self.value = self.to_units(newUnits)
        self.units = newUnits
        return self

    def to_units(self, otherUnits: dict = ArcUnits.DEGREE) -> decimal.Decimal:
        """Returns the magnitude of this arc in otherUnits.

        Note that this method does not alter the state of this arc. Contrast
        this with convert_to(ArcUnits).

        Args:
            otherUnits: The units in which to express this arc's magnitude
                (default: degrees)

        Returns:
            This arc's value converted to otherUnits.
        """
        factor = otherUnits['units per circle'] / self.units['units per circle']
        return self.value * factor

    def toDms(self) -> tuple[int, int, float]:
        """Returns a representation of this arc in degrees, minutes, and
        seconds.

        Returns:
            a tuple of size three in this order:
                An integer holding the number of degrees.
                An integer holding the number of arc minutes.
                A float holding the number of arc seconds.
        """
        degrees = self.to_units(ArcUnits.DEGREE)
        dd = abs(degrees)
        mm = dd * decimal.Decimal(60)
        ss = dd * decimal.Decimal(3600)

        dd = int(dd)
        mm = int(mm - 60*dd)
        ss = float(ss - 3600*dd - 60*mm)

        if degrees < 0:
            dd *= -1

        # sometimes have an overflow condition where secs=60
        if ss == 60:
            ss = 0
            mm += 1
        if mm == 60:
            dd += 1
            mm = 0

        return dd, mm, ss

    def toHms(self) -> tuple[int, int, float]:
        """Returns a representation of this arc in hours, minutes, and seconds.

        Returns:
            a tuple of size three in this order:
                An integer holding the number of hours.
                An integer holding the number of minutes.
                A float holding the number of seconds.
        """
        return (self / 15).toDms()

    def __repr__(self) -> str:
        return 'EquatorialArc(%s, ArcUnits.%s)' % (self.value,
                                                   self.units['name'])


class FluxDensity(ComparableUnit):
    def __init__(self, value: int | float | decimal.Decimal = 0, units: dict = FluxDensityUnits.JANSKY) -> None:
        """Create a new flux density with the given magnitude and units.

        If called without arguments, the constructor will create a
        default frequency of 0 Janskys

        Args:
            value: The magnitude for this flux density.
            units: The new units for this flux density.
        """
        if isinstance(value, (float, int)):
            value = str(value)
        self.value = decimal.Decimal(value)
        self.units = units

    def convert_to(self, newUnits: dict = FluxDensityUnits.JANSKY) -> FluxDensity:
        """Converts this measure of flux density to the new units.
        After this method is complete this flux density will have units of
        units and its value will have been converted accordingly.

        Args:
            newUnits: The new units for this flux density (default: Jy).

        Returns:
            This flux density. The reason for this return type is to allow code
            of this nature:

            janskies = myFluxDensity.convert_to(FluxDensityUnits.JANSKY)
        """
        self.value = self.to_units(newUnits)
        self.units = newUnits
        return self

    def to_units(self, otherUnits: dict = FluxDensityUnits.JANSKY) -> decimal.Decimal:
        """Returns the magnitude of this flux density in otherUnits.

        Note that this method does not alter the state of this flux density.
        Contrast this with convert_to(FluxDensityUnits).

        Args:
            otherUnits: The units in which to express this flux density's magnitude.

        Returns:
            This flux density's value converted to otherUnits.
        """
        factor = self.units['Jy'] / otherUnits['Jy']
        return self.value * factor

    def __str__(self) -> str:
        return unitformat.flux.format(self.to_units(FluxDensityUnits.JANSKY))

    def __repr__(self) -> str:
        return 'FluxDensity(%s, FluxDensityUnits.%s)' % (self.value,
                                                         self.units['name'])


class LinearVelocity(ComparableUnit):
    def __init__(self, value: int | float | decimal.Decimal = 0,
                 units: dict = LinearVelocityUnits.KILOMETRES_PER_SECOND) -> None:
        """Create a new linear velocity with the given magnitude and units.

        If called without arguments, the constructor will create a
        default linear velocity of 0 kilometres per second.

        Args:
            value: The magnitude for this linear velocity.
            units: The new units for this linear velocity.
        """
        if isinstance(value, (float, int)):
            value = str(value)
        self.value = decimal.Decimal(value)
        self.units = units

    def convert_to(self, newUnits: dict = LinearVelocityUnits.KILOMETRES_PER_SECOND) -> LinearVelocity:
        """Converts this measure of linear velocity to the new units.
        After this method is complete this linear veloity will have units of
        units and its value will have been converted accordingly.

        Args:
            newUnits: The new units for this linear velocity. If newUnits is
                None an IllegalArgumentException will be thrown.

        Returns:
            This linear velocity. The reason for this return type is to allow
            code of this nature:

            velocity = myLinearVelocity.convert_to(LinearVelocityUnits.Z)
        """
        self.value = self.to_units(newUnits)
        self.units = newUnits
        return self

    def to_units(self, otherUnits: dict = LinearVelocityUnits.KILOMETRES_PER_SECOND) -> decimal.Decimal:
        """Returns the magnitude of this linear velocity in otherUnits.

        Note that this method does not alter the state of this linear velocity.
        Contrast this with convert_to(LinearVelocityUnits).

        Args:
            otherUnits: The units in which to express this linear velocity's
                magnitude. If otherUnits is None an IllegalArgumentException
                will be thrown.

        Returns:
            This linear velocity's value converted to otherUnits.
        """
        factor = self.units['mps'] / otherUnits['mps']
        return self.value * factor

    def __str__(self) -> str:
        mps = self.to_units(LinearVelocityUnits.METRES_PER_SECOND)
        return unitformat.velocity.format(mps)

    def __repr__(self) -> str:
        return ('LinearVelocity(%s, '
                'LinearVelocityUnits.%s)' % (self.value, self.units['name']))


class FileSize(ComparableUnit):
    def __init__(self, value: int | float | decimal.Decimal = 0, units: dict = FileSizeUnits.MEGABYTES) -> None:
        """Creates a new file size with the given magnitude and units.

        If called without arguments, the constructor will create a
        default size of 0 megabytes.

        Args:
            value: The magnitude for this file size.
            units: The new units for this file size.
        """
        if isinstance(value, (float, int)):
            value = str(value)
        self.value = decimal.Decimal(value)
        self.units = units

    def convert_to(self, newUnits: dict = FileSizeUnits.MEGABYTES) -> FileSize:
        """Converts this measure of file size to the new units.

        After this method is complete this file size will have units of
        newUnits and its value will have been converted accordingly.

        Args:
            newUnits: The new units for this file size.

        Returns:
            this file size. The reason for this return type is to allow code of
            this nature:

            gigabytes = myFileSize.convert_to(FileSizeUnits.GIGABYTES)
        """
        self.value = self.to_units(newUnits)
        self.units = newUnits
        return self

    def to_units(self, otherUnits: dict = FileSizeUnits.GIGABYTES) -> decimal.Decimal:
        """Returns the magnitude of this file size in otherUnits.

        Note that this method does not alter the state of this file size.
        Contrast this with convert_to(FileSizeUnits).

        Args:
            otherUnits: the units in which to express this file size's magnitude.
                If newUnits is None, it will be treated as FileSizeUnits.GIGABYTES.

        Returns:
            this file size's value converted to otherUnits.
        """
        factor = self.units['bytes'] / otherUnits['bytes']
        return self.value * factor

    def __str__(self) -> str:
        return unitformat.file_size.format(self.to_units(FileSizeUnits.BYTES))

    def __repr__(self) -> str:
        return 'FileSize(%s, FileSizeUnits.%s)' % (self.value,
                                                   self.units['name'])


class Frequency(ComparableUnit):
    def __init__(self, value: int | float | decimal.Decimal = 0, units: dict = FrequencyUnits.GIGAHERTZ) -> None:
        """Creates a new frequency with the given magnitude and units.

        If called without arguments, the constructor will create a
        default frequency of 0 gigahertz.

        Args:
            value: The magnitude for this frequency.
            units: The new units for this frequency.
        """
        if isinstance(value, (float, int)):
            value = str(value)
        self.value = decimal.Decimal(value)
        self.units = units

    def convert_to(self, newUnits: dict = FrequencyUnits.GIGAHERTZ) -> Frequency:
        """Converts this measure of frequency to the new units.

        After this method is complete this frequency will have units of
        newUnits and its value will have been converted accordingly.

        Args:
            newUnits: The new units for this frequency; by default, it will
                convert the frequency to Gigahertz.

        Returns:
            this frequency. The reason for this return type is to allow code of
            this nature:

            gigahertz = myFrequency.convert_to(FrequencyUnits.GIGAHERTZ)
        """
        self.value = self.to_units(newUnits)
        self.units = newUnits
        return self

    def to_units(self, otherUnits: dict = FrequencyUnits.GIGAHERTZ) -> decimal.Decimal:
        """Returns the magnitude of this frequency in otherUnits.

        Note that this method does not alter the state of this frequency.
        Contrast this with convert_to(FrequencyUnits).

        Args:
            otherUnits: The units in which to express this frequency's
                magnitude. If newUnits is None, it will be treated as
                FrequencyUnits.GIGAHERTZ.

        Returns:
            this frequency's value converted to otherUnits.
        """
        factor = self.units['hz'] / otherUnits['hz']
        return self.value * factor

    def str_to_precision(self, precision: int) -> str:
        """
        Return the string representation of this Frequency to a fixed number
        of decimal places.

        Args:
            precision: Number of decimal places to use.

        Returns:
            String representation of this Frequency to fixed number of decimal
            places.
        """
        f = unitformat.get_frequency_format(precision)
        return f.format(self.to_units(FrequencyUnits.HERTZ))

    def __str__(self) -> str:
        return unitformat.frequency.format(self.to_units(FrequencyUnits.HERTZ))

    def __repr__(self) -> str:
        return 'Frequency(%s, FrequencyUnits.%s)' % (self.value,
                                                     self.units['name'])


class FrequencyRange:
    __slots__ = ('low', 'high')

    def __getstate__(self) -> tuple[Frequency, Frequency]:
        return self.low, self.high

    def __setstate__(self, state: tuple[Frequency, Frequency]) -> None:
        self.low, self.high = state

    def __init__(self, frequency1: Frequency | None = None, frequency2: Frequency | None = None) -> None:
        """Creates a new instance with the given endpoints.

        This method will set the lower value of its range to the lesser of the
        two parameter values. If either parameter is null, it will be
        interpreted as a signal to create a new default frequency. If both
        parameters are null, a frequency range spanning all positive
        frequencies will be returned.

        Note that this method makes copies of the parameters; it does not
        maintain a reference to either parameter. This is done in order to
        maintain the integrity of the relationship between the starting and
        ending points of this interval.

        Args:
            frequency1: One endpoint of this range.
            frequency2: The other endpoint of this range.
        """
        if frequency1 == frequency2 is None:
            frequency2 = Frequency(decimal.Decimal('Infinity'))
        self.set(frequency1, frequency2)

    def __composite_values__(self) -> list[Frequency, Frequency]:
        return [self.low, self.high]

    def __eq__(self, other: FrequencyRange) -> bool:
        if isinstance(other, FrequencyRange):
            return other.low == self.low and other.high == self.high
        return False

    def __ne__(self, other: FrequencyRange) -> bool:
        return not self.__eq__(other)

    def __repr__(self) -> str:
        return '<FrequencyRange(%s, %s)>' % (self.low, self.high)

    def contains(self, frequency: Frequency | FrequencyRange = None) -> bool:
        """Returns true if this range contains given frequency (range).

        The frequency argument can be a frequency or a frequency range. If the
        argument given is a Frequency range, then FrequencyRange A is said to
        contain range B if A's low frequency is less than or equal to B's low
        frequency and A's high frequency is greater than or each to B's high
        frequency. Notice that this means that if A equals B, it also contains
        B.

        Args:
            frequency: The frequency or range to test for inclusion in this range.

        Returns:
            True if this range contains frequency. If frequency is None, the
            return value will be false.
        """
        if isinstance(frequency, Frequency):
            return frequency >= self.low and frequency <= self.high
        if isinstance(frequency, FrequencyRange):
            return frequency.low >= self.low and frequency.high <= self.high
        return False

    def convert_to(self, newUnits: dict = FrequencyUnits.GIGAHERTZ) -> FrequencyRange:
        """Converts both endpoints of this range to the given units.

        After this method is complete both endpoints of this range will have
        units of units, and their values will have been converted accordingly.

        Args:
            newUnits: The new units for the endpoints of this range. If no units
                are specified, it will be treated as FrequencyUnits.GIGAHERTZ.

        Returns:
            this range.
        """
        self.low.convert_to(newUnits)
        self.high.convert_to(newUnits)
        return self

    def getCentreFrequency(self) -> Frequency:
        """Returns the frequency that is midway between the endpoints of this
        range.

        The units for the returned frequency will be the same as those of the
        high frequency of this range.

        Returns:
            The center frequency of this range.
        """
        c = (self.low + self.high) / 2
        return c.convert_to(self.high.units)

    def getOverlapWith(self, other: FrequencyRange) -> FrequencyRange | None:
        """Returns a new range that represents the region of overlap between
        this range and other. If there is no overlap, None is returned.

        Args:
            other: Another range that may overlap this one.

        Returns:
            FrequencyRange object representing the overlapping region of this
            range and other, or None if there is no overlap.
        """
        if self.overlaps(other):
            if self.low > other.low:
                return FrequencyRange(self.low, other.high)
            else:
                return FrequencyRange(other.low, self.high)
        return None

    def getGapBetween(self, other: FrequencyRange | None = None) -> FrequencyRange | None:
        """Returns a new range that represents the region of frequency space
        between this range and other. If the other range is coincident with, or
        overlaps, this range, None is returned. If the other range is None,
        None is returned.

        Args:
            other: Another range that might not overlap this one.

        Returns:
            FrequencyRange object representing the frequency gap between this
            range and other, or None if there is no gap.
        """
        if other is None or self.overlaps(other):
            return None

        if self.low > other.low:
            return FrequencyRange(other.high, self.low)
        else:
            return FrequencyRange(self.high, other.low)

    def getWidth(self) -> Frequency:
        """Returns the width of this range.

        The units for the returned frequency will be the same as those of the
        high frequency of this range.

        Returns:
            the width of this range.
        """
        return self.high - self.low

    def overlaps(self, other: FrequencyRange | None = None) -> bool:
        """Returns whether this frequency range overlaps with ``other`` frequency range.

        Remember that this range is a closed interval, that is, one that
        contains both of its endpoints.

        Args:
            other: another range that may overlap this one.

        Returns:
            True if this range overlaps with other. If ``other`` is not a
            FrequencyRange, the return value is False.
        """
        if isinstance(other, FrequencyRange):
            if self.low < other.low:
                return self.high >= other.low
            else:
                return other.high >= self.low
        return False

    def set(self, frequency1: Frequency | None = None, frequency2: Frequency | None = None) -> None:
        """Sets the frequencies of this range.

        This method will set the lower value of its range to the lesser of the
        two parameter values. If either parameter is None, it will be
        interpreted as a signal to create a new default frequency (0 GHz).

        Note that this method makes copies of the parameters; it does not
        maintain a reference to either parameter. This is done in order to
        maintain the integrity of the relationship between the starting and
        ending points of this interval.

        Args:
            frequency1: One endpoint of this range.
            frequency2: The other endpoint of this range.
        """
        if frequency1 is None:
            frequency1 = Frequency()
        if frequency2 is None:
            frequency2 = Frequency()

        if frequency1 > frequency2:
            self.high = Frequency(frequency1.value, frequency1.units)
            self.low = Frequency(frequency2.value, frequency2.units)
        else:
            self.low = Frequency(frequency1.value, frequency1.units)
            self.high = Frequency(frequency2.value, frequency2.units)


class Latitude(EquatorialArc):
    patt = re.compile(r'\s*' +
                      r'(?P<degs>[-+]?\d+)' +
                      r'\s*:?\s*' +
                      r'(?P<mins>\d+)' +
                      r'\s*:?\s*' +
                      r'(?P<secs>\d+\.?\d*)' +
                      r'\s*')

    def __init__(self, value: int | float | decimal.Decimal = 0, units: dict = ArcUnits.DEGREE) -> None:
        """Creates a new latitude with the given magnitude and units.

        If no magnitude or units are give, a latitude of 0 degrees will be
        created.

        If magnitude is not a valid value for latitude, it will be normalised
        in a way that will transform it to a legal value. To be legal,
        magnitude must be greater than or equal to the negative of one-quarter
        of a circle and less than or equal to one-quarter of a circle, in the
        given units.

        Args:
            value: The magnitude for this latitude.
            units: The units for this latitude.
        """
        super().__init__(value, units)
        perCircle = self.units['units per circle']
        perHalf = perCircle / 2
        perQuarter = perCircle / 4
        threeQuarters = perHalf + perQuarter

        # normalize value to < 360 degrees
        self.value -= (self.value // perCircle) * perCircle

        if self.value > threeQuarters:
            self.value = -perCircle + self.value
        if self.value > perQuarter:
            self.value = perHalf - self.value
        if self.value < -threeQuarters:
            self.value = perCircle + self.value
        if self.value < -perQuarter:
            self.value = -perHalf - self.value

    @staticmethod
    def parse(value: str) -> Latitude:
        """Returns a new Latitude based on the given text.

        See the parse method of Angle for information on the format of text.
        This Latitude class offers two other formats:

            dd:mm:ss.sss
            dd mm ss.sss

        Both of the above are in degrees, arc-minutes, and arc-seconds. For the
        first alternative form, whitespace is permitted around the colon
        characters. For the second alternative form, any type and number of
        whitespace characters may be used in between the three parts.

        The parsed value, if not a legal value for latitude, will be normalised
        in such a way that it is transformed to a legal value. To be legal,
        magnitude must be greater than or equal to the negative of one-quarter
        of a circle and less than or equal to one-quarter of a circle, in the
        given units.

        Args:
            value: A string that will be converted into a latitude.

        Returns:
            A new Latitude. If parsing was successful, the value of the
            latitude will be based on the parameter string. If it was not, the
            returned latitude will be of zero degrees.

        Raises:
            ValueError - if text is not in the expected form.
        """
        m = Latitude.patt.match(value)

        try:
            y = abs(decimal.Decimal(m.group('degs'))) + decimal.Decimal(m.group('mins'))/60 \
                + decimal.Decimal(m.group('secs'))/3600
        except AttributeError:
            raise ValueError

        # Check & fix for negativity
        if m.group('degs').startswith('-'):
            y *= -1

        return Latitude(y, ArcUnits.DEGREE)

    def isNorthOfEquator(self) -> bool:
        """Returns True if this latitude is north of the equator.

        Returns:
            True if this latitude is north of the equator.
        """
        return self.value > 0

    def isSouthOfEquator(self) -> bool:
        """Returns True if this latitude is south of the equator.

        Returns:
            True if this latitude is south of the equator.
        """
        return self.value < 0

    def isNorthOf(self, other: Latitude) -> bool:
        """Returns True if this latitude is north of other.

        Args:
            other: The latitude to be tested.

        Returns:
            True if this latitude is north of other.
        """
        return self > other

    def isSouthOf(self, other: Latitude) -> bool:
        """Returns True if this latitude is south of other.

        Args:
            other: The latitude to be tested.

        Returns:
            True if this latitude is south of other.
        """
        return self < other

    def __repr__(self) -> str:
        return 'Latitude(%s, ArcUnits.%s)' % (self.value,
                                              self.units['name'])

    def __str__(self) -> str:
        (d, m, s) = self.toDms()
        return '%+.2d%s%.2d%s%05.2f%s' % (d, ArcUnits.DEGREE['symbol'],
                                          m, ArcUnits.ARC_MINUTE['symbol'],
                                          utils.round_half_up(s, 2), ArcUnits.ARC_SECOND['symbol'])


class Longitude(EquatorialArc):
    patt = re.compile(r'\s*' +
                      r'(?P<hours>\d+)' +
                      r'\s*:?\s*' +
                      r'(?P<mins>\d+)' +
                      r'\s*:?\s*' +
                      r'(?P<secs>\d+\.?\d*)' +
                      r'\s*')

    def __init__(self, value: int | float | decimal.Decimal = 0, units: dict = ArcUnits.DEGREE) -> None:
        """Creates a new longitude with the given magnitude and units.

        If magnitude is not a valid value1 for longitude, it will be normalised
        in a way that will transform it to a legal value. To be legal,
        magnitude must be greater than or equal to zero and less than one full
        circle, in the given units.

        If no arguments are given, a longitude of 0 degrees will be created.

        Args:
            value: The magnitude of the longitude.
            units: The units of longitude.
        """
        super().__init__(value, units)
        perCircle = self.units['units per circle']

        # normalize value to < 360 degrees
        self.value -= (self.value // perCircle) * perCircle

        if self.value < 0:
            self.value += perCircle

    @staticmethod
    def parse(value: str) -> Longitude:
        """Returns a new longitude based on the given text.

        See the parse method of Angle for information on the format of text.
        This Longitude class offers two other formats:

            hh:mm:ss.sss
            hh mm ss.sss

        Both of the above are in hours, minutes, and seconds. For the first
        alternative form, whitespace is permitted around the colon characters.
        For the second alternative form, any type and number of whitespace
        characters may be used in between the three parts.

        The parsed value, if not a legal value for longitude, will be
        normalised in such a way that it is transformed to a legal value. To be
         legal, magnitude must be greater than or equal zero and less than or
         equal to one full circle, in the given units.

        Args:
            value: A string that will be converted into a longitude.

        Returns:
            A new Longitude. If parsing was successful, the value of the
            Longitude will be based on the parameter string. If it was not, the
            returned longitude will be of zero degrees.

        Raises:
            ValueError - if text is not in the expected form.
        """
        match = Longitude.patt.match(value)

        try:
            h = decimal.Decimal(match.group('hours')).to_integral()
            m = decimal.Decimal(match.group('mins')).to_integral()
            s = decimal.Decimal(match.group('secs'))
            x = 15*h + 15*m/60 + 15*s/3600
            return Longitude(x, ArcUnits.DEGREE)
        except AttributeError:
            raise ValueError

    def isOpposite(self, other: Longitude) -> bool:
        """Returns True if this longitude and other are separated by one half
        circle.

        Args:
            other: The other longitude to be tested.

        Returns:
            True if other is separated from this longitude by one half circle.
        """
        halfCircle = self.units['units per circle'] / 2
        difference = abs(self.value - other.to_units(self.units))
        return difference == halfCircle

    def isEastOf(self, other: Longitude) -> bool:
        """Returns true if this longitude is east of other.

        One longitude is east of another if there are fewer lines of longitude
        to cross by travelling eastward along a given latitude than there would
        be by travelling westward along that same latitude.

        Two special cases are worth noting. First, a longitude that is equal to
        this one is neither east nor west of this one. Second, a longitude that
        is opposite this one is both east and west of this one.

        Args:
            other: The longitude to be tested.

        Returns:
            True if this longitude is east of other.
        """
        o = other.to_units(self.units)
        # calculate opposite angle
        r = self.units['units per circle'] / 2 + self.value
        return o < self.value or o >= r

    def isWestOf(self, other: Longitude):
        """Returns True if this longitude is west of other.

        One longitude is west of another if there are fewer lines of longitude
        to cross by travelling westward along a given latitude than there would
        be by travelling eastward along that same latitude.

        Two special cases are worth noting. First, a longitude that is equal to
        this one is neither east nor west of this one. Second, a longitude that
        is opposite this one is both east and west of this one.

        Args:
            other: The longitude to be tested.

        Returns:
            True if this longitude is west of other.
        """
        o = other.to_units(self.units)
        # calculate opposite angle
        r = self.units['units per circle'] / 2 + self.value
        return not (o <= self.value or o > r)

    def __repr__(self) -> str:
        return 'Longitude(%s, ArcUnits.%s)' % (self.value,
                                               self.units['name'])

    def __str__(self) -> str:
        (h, m, s) = self.toHms()
        return '%.2d%s%.2d%s%05.2f%s' % (h, ArcUnits.HOUR['symbol'],
                                         m, ArcUnits.MINUTE['symbol'],
                                         utils.round_half_up(s, 2), ArcUnits.SECOND['symbol'])


class TimeInterval:
    """
    Logical representation of a time interval.

    Attributes:
        start: start time of interval, as datetime object.
        end: end time of interval, as datetime object.
    """
    __slots__ = ('start', 'end')

    FOREVER = datetime.datetime(9999, 12, 31, tzinfo=datetime.timezone.utc)

    def __getstate__(self) -> tuple[datetime.datetime, datetime.datetime]:
        return self.start, self.end

    def __setstate__(self, state: tuple[datetime.datetime, datetime.datetime]):
        self.start, self.end = state

    def __init__(self, start: datetime.datetime | None = None, end: datetime.datetime | None = None) -> None:
        """
        Initialize a TimeInterval object.

        Args:
            start: start time of interval, as datetime object.
            end: end time of interval, as datetime object.
        """
        self.start = start
        self.end = end

    def __composite_values__(self) -> tuple[datetime.datetime, datetime.datetime]:
        return self.start, self.end

    def __set_composite_values__(self, start: datetime.datetime, end: datetime.datetime) -> None:
        self.start = start
        self.end = end

    def __eq__(self, other: TimeInterval) -> bool:
        if not isinstance(other, self.__class__):
            return False
        return other.start == self.start and other.end == self.end

    def __ne__(self, other: TimeInterval) -> bool:
        return not self.__eq__(other)

    def __repr__(self) -> str:
        return 'TimeInterval(%s, %s)' % (self.start, self.end)

    def contains(self, time: datetime.datetime | TimeInterval) -> bool:
        """Returns True if time is contained in this interval.

        Note that this interval is half-open; it does not include its ending
        point. Note also that an interval that is equal to this one is not
        contained by this one. The best analogy is that of a rigid box with
        infinitely thin walls: a box that is exactly the same as another cannot
        fit inside it.

        Args:
            time: The datetime or TimeInterval to be tested for containment.

        Returns:
            True if time is contained in this interval.
        """
        if isinstance(time, datetime.datetime):
            return time >= self.start and time < self.end
        if isinstance(time, TimeInterval):
            if time.end == TimeInterval.FOREVER and self.end == TimeInterval.FOREVER:
                return self.start < time.start
            return self.contains(time.start) and self.contains(time.end)
        return False

    def is_empty(self) -> bool:
        """Returns True if this TimeInterval is empty.
        """
        return self.start > self.end

    def overlaps(self, ti: TimeInterval) -> bool:
        """
        Returns True if this interval overlaps with the given interval.

        Args:
            ti: TimeInterval object to test overlap with.

        Returns:
            Boolean denoting whether this time interval overlaps with given interval.
        """
        if isinstance(ti, TimeInterval):
            return ti.contains(self.start) or ti.contains(self.end) or self.contains(ti)
        return False

    @classmethod
    def starting_from(cls, start: datetime.datetime) -> TimeInterval:
        """
        Returns an open-ended TimeInterval starting from the given time.

        Args:
            start (object): Datetime object denoting start time of interval.

        Returns:
            TimeInterval object from given time until 31-12-9999.
        """
        return cls(start, cls.FOREVER)

    @classmethod
    def starting_from_now(cls) -> TimeInterval:
        """
        Returns an open-ended TimeInterval starting from now.

        Returns:
            TimeInterval object.
        """
        return cls(datetime.datetime.now(datetime.timezone.utc), cls.FOREVER)
