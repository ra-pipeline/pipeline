import itertools
import pprint

import numpy

from pipeline.infrastructure import casa_tools


_pprinter = pprint.PrettyPrinter()


class Source:
    """A logical representation of an astronomical source.

    Attributes:
        id: The numerical identifier of the source.
        name: The name of the source.
        fields: List of Field objects for field(s) associated with the source.
        is_eph_obj: Boolean declaring whether this is a moving source (with
            entry in the ephemeris table).
    """
    def __init__(self, source_id: int | numpy.integer, name: str, direction: dict, proper_motion: dict[str, dict],
                 is_eph_obj: bool, table_name: str, avg_spacing: float | str) -> None:
        """Initialize a Source object.

        Args:
            source_id: The numerical identifier of the source.
            name: The name of the source.
            direction: The direction to the source as a CASA 'direction' measure dictionary.
            proper_motion: The proper motion of the source; provided as a
                2-element dictionary with keys "longitude" and "latitude",
                containing the respective components of the proper motion as
                CASA quantities (dictionaries).
            is_eph_obj: Boolean declaring whether this is a moving source (with
                entry in the ephemeris table).
            table_name: Base file name of ephemeris table (without extension).
            avg_spacing: Average time spacing (in minutes) between entries in
                the ephemeris table.
        """
        self.id = source_id
        self.name = name
        self.is_eph_obj = is_eph_obj

        # Fields associated with this source. Initialized as an empty list, and
        # expected to be populated in a separate step during the import of a
        # measurement set (see MeasurementSetReader.link_fields_to_sources).
        self.fields = []

        self._avg_spacing = avg_spacing
        self._direction = direction
        self._ephemeris_table = table_name
        self._proper_motion = proper_motion

    def __repr__(self) -> str:
        # use pretty printer so we have consistent ordering of dicts
        return '{0}({1}, {2!r}, {3}, {4})'.format(
            self.__class__.__name__,
            self.id,
            self.name,
            _pprinter.pformat(self._direction),
            _pprinter.pformat(self._proper_motion)
        )

    @property
    def dec(self) -> str:
        """Return declination of the source."""
        return casa_tools.quanta.formxxx(self.latitude, format='dms', prec=2)

    @property
    def direction(self) -> dict:
        """Return source direction as a CASA 'direction' measure dictionary."""
        return self._direction

    @property
    def frame(self) -> str:
        """Return reference frame code for the direction to the source."""
        return self._direction['refer']

    @property
    def intents(self) -> set[str]:
        """Return unique scan intents associated with the source."""
        return set(itertools.chain(*[f.intents for f in self.fields]))

    @property
    def latitude(self) -> dict:
        """Return latitude of the source."""
        return self._direction['m1']

    @property
    def longitude(self) -> dict:
        """Return longitude of the source."""
        return self._direction['m0']

    @property
    def pm_x(self) -> str:
        """Return string representation of longitudinal component of proper motion of the source."""
        return self.__format_pm(axis='longitude')

    @property
    def pm_y(self) -> str:
        """Return string representation of latitudinal component of proper motion of the source."""
        return self.__format_pm(axis='latitude')

    @property
    def proper_motion(self) -> str:
        """Return string representation of proper motion of the source."""
        qa = casa_tools.quanta
        return '%.3e %.3e %s' % (qa.getvalue(self.pm_x),
                                 qa.getvalue(self.pm_y),
                                 qa.getunit(self.pm_x))

    @property
    def ra(self) -> str:
        """Return right ascension of the source."""
        return casa_tools.quanta.formxxx(self.longitude, format='hms', prec=3)

    # Galactic Longitude: it is usually expressed in DMS format
    @property
    def gl(self) -> str:
        """Return longitude for the source, in DMS format."""
        return casa_tools.quanta.formxxx(self.longitude, format='dms', prec=2)

    # Galactic Latitude
    @property
    def gb(self) -> str:
        """Return declination of the source."""
        return self.dec

    @property
    def ephemeris_table(self) -> str:
        """
        Returns the name of the ephemeris table associated with this Source or
        "" if this is not an ephemeris source.
        """
        return self._ephemeris_table

    @property
    def avg_spacing(self) -> float | str:
        """
        Returns the average time spacing (in minutes) between table entries in
        the ephemeris table or "" if this is not an ephemeris source.
        """
        return self._avg_spacing

    def __format_pm(self, axis: str) -> str:
        """Return proper motion along given axis.

        Args:
            axis: Axis to return proper motion for; can be either 'longitude' or 'latitude'.

        Returns:
            String representation of proper motion along given axis.
        """
        qa = casa_tools.quanta
        val = qa.getvalue(self._proper_motion[axis])
        units = qa.getunit(self._proper_motion[axis])
        return '' if val == 0 else '%.3e %s' % (val, units)

    def __str__(self) -> str:
        return ('Source({0}:{1}, pos={2} {3} ({4}), pm={5})'
                ''.format(self.id, self.name, self.ra, self.dec, self.frame, 
                          self.proper_motion))
