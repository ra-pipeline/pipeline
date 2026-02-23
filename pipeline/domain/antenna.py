"""The antenna module defines the Antenna class."""
import pprint

from pipeline.infrastructure import casa_tools

_pprinter = pprint.PrettyPrinter()


class Antenna:
    """A logical representation of an antenna.

    Attributes:
        id: Numerical identifier of this antenna within the ANTENNA subtable
            of the measurement set.
        name: The (potentially empty) name of the antenna.
        station: The station pad on which the antenna is situated.
        diameter: Physical diameter of the antenna in meters.
        position: Dictionary with longitude, latitude, and height of the antenna.
        offset: Offset position of the antenna relative to AntennaArray.position
            (the antenna array reference position).
        longitude: Longitude of the antenna as a CASA quantity in radians.
        latitude: Latitude of the antenna as a CASA quantity in radians.
        height: Radial distance of the antenna from the Earth's centre in meters.
        direction: J2000 position on the sky to which the antenna points.
    """
    def __init__(self, antenna_id: int, name: str, station: str, position: dict, offset: dict, diameter: float) -> None:
        """
        Initialize an Antenna object.

        Args:
            antenna_id: The numerical identifier of the antenna.
            name: The name of the antenna.
            station: The station pad on which the antenna is situated.
            position: Dictionary with longitude, latitude, and height of the antenna.
            offset: The offset position of the antenna relative to AntennaArray.position
                (the antenna array reference position).
            diameter: The physical diameter of the antenna in meters.
        """
        self.id = antenna_id

        # work around NumPy bug with empty strings
        # http://projects.scipy.org/numpy/ticket/1239
        self.name = str(name)
        self.station = str(station)

        self.diameter = diameter
        self.position = position
        self.offset = offset

        # The longitude, latitude and height of a CASA position are given in
        # canonical units, so we don't need to perform any further conversion
        self.longitude = position['m0']  # CASA quantity in radians
        self.latitude = position['m1']  # CASA quantity in radians
        self.height = position['m2']  # CASA quantity in meters

        mt = casa_tools.measures
        self.direction = mt.direction(v0=self.longitude, v1=self.latitude)

    def __repr__(self) -> str:
        return '{0}({1}, {2!r}, {3!r}, {4}, {5}, {6})'.format(
            self.__class__.__name__,
            self.id,
            self.name,
            self.station,
            _pprinter.pformat(self.position),
            _pprinter.pformat(self.offset),
            self.diameter)

    def __str__(self) -> str:
        qt = casa_tools.quanta
        lon = qt.tos(self.longitude) 
        lat = qt.tos(self.latitude) 
        return '<Antenna {id} (lon={lon}, lat={lat})>'.format(
            id=self.identifier, lon=lon, lat=lat)

    @property
    def identifier(self) -> str:
        """Return a human-readable identifier for this Antenna."""
        return self.name if self.name else f"#{self.id}"
