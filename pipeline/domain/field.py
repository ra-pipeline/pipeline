"""Provide a class to store logical representation of field."""
from __future__ import annotations

import datetime
import pprint
from typing import TYPE_CHECKING

import numpy as np

from pipeline.infrastructure import casa_tools, utils

if TYPE_CHECKING:
    from pipeline.infrastructure.utils.utils import DirectionDict, EpochDict, QuantityDict

_pprinter = pprint.PrettyPrinter(width=1e99)


class Field:
    """A logical representation of a field in a MeasurementSet.

    Attributes:
        id: Numerical identifier of this field within the FIELD subtable of
            the MeasurementSet.
        source_id: ID of the source associated with this field.
        time: Array of unique observation times for this field.
        name: Name of this field, formatted for use as a CASA argument.
        intents: Set of unique scan intents associated with this field.
        states: Set of unique State objects associated with this field.
        valid_spws: Set of unique SpectralWindow objects associated with
            this field.
        flux_densities: Set of unique flux measurements from setjy.
    """
    def __init__(
            self,
            field_id: int,
            name: str,
            source_id: int,
            time: np.ndarray,
            direction: DirectionDict,
            ) -> None:
        """
        Initialize a Field object.

        Args:
            field_id: Field ID.
            name: Field name.
            source_id: A source ID associated with this field.
            time: A list of the unique times for this field.
            direction: A CASA 'direction' measure dictionary for the phasecenter
                of this field.
        """
        self.id = field_id
        self.source_id = source_id
        self.time = time
        self.name = name

        self._mdirection = direction

        # Intents, states, and valid_spws are initialized as empty sets, and
        # expected to be populated in a separate step during the import of a
        # measurement set (see MeasurementSetReader.link_fields_to_states,
        # MeasurementSetReader.link_spws_to_fields).
        self.intents = set()
        self.states = set()
        self.valid_spws = set()

        # Flux densities are initialized as an empty set, and expected to be
        # populated in a separate step during importdata that retrieves fluxes
        # from multiple origins (Source.xml, user .CSV file). May also later be
        # updated by flux calibration pipeline tasks.
        self.flux_densities = set()

        # PIPE-2472: calculate zenith distance and telescope MJD of observation (TELMJD)
        # These are set to None until the import of the measurement set (see 
        # MeasurementSetReader.set_field_zd_telmjd)
        self._zd = None
        self._telmjd = None

    def __repr__(self) -> str:
        name = self.name
        if '"' in name:
            name = name[1:-1]

        return 'Field({0}, {1!r}, {2}, {3}, {4})'.format(
            self.id,
            name,
            self.source_id,
            'numpy.array(%r)' % self.time.tolist(),
            _pprinter.pformat(self._mdirection)
        )

    @property
    def clean_name(self) -> str:
        """
        Get the field name with illegal characters replaced with underscores.

        This property is used to determine whether the field name, when given
        as a CASA argument, should be enclosed in quotes.
        """
        return utils.fieldname_clean(self._name)

    @property
    def dec(self) -> str:
        """Return declination for the phasecenter of the field."""
        return casa_tools.quanta.formxxx(self.latitude, format='dms', prec=2)

    @property
    def frame(self) -> str:
        """Return reference frame code for the Field."""
        return self._mdirection['refer']

    @property
    def identifier(self) -> str:
        """
        A human-readable identifier for this Field.
        """
        return self.name if self.name else '#{0}'.format(self.id)

    @property
    def latitude(self) -> EpochDict:
        """Return latitude for the phasecenter of the field."""
        return self._mdirection['m1']

    @property
    def longitude(self) -> EpochDict:
        """Return longitude for the phasecenter of the field."""
        return self._mdirection['m0']

    @property
    def mdirection(self) -> DirectionDict:
        """Return direction measure dictionary for phasecenter of the field."""
        return self._mdirection

    @property
    def name(self) -> str:
        """Return name of field, in form that can be used as a CASA argument."""
        # SCOPS-1666
        # work around CASA data selection problems with names consisting
        # entirely of digits
        return utils.fieldname_for_casa(self._name)

    @name.setter
    def name(self, value: str) -> None:
        """Set name of field to given value."""
        self._name = value

    @property
    def ra(self) -> str:
        """Return right ascension for the phasecenter of the field."""
        return casa_tools.quanta.formxxx(self.longitude, format='hms', prec=3)

    # Galactic Longitude: it is usually expressed in DMS format
    @property
    def gl(self) -> str:
        """Return longitude for phasecenter of the field, in DMS format."""
        return casa_tools.quanta.formxxx(self.longitude, format='dms', prec=2)

    # Galactic Latitude
    @property
    def gb(self) -> str:
        """Return declination for the phasecenter of the field."""
        return self.dec

    @property
    def zd(self) -> QuantityDict:
        """Return the zenith distance in a CASA `quantity` quanta dictionary."""
        return self._zd

    @property
    def telmjd(self) -> QuantityDict:
        """Return the Modified Julian Date in a CASA `epoch` measure dictionary"""
        return self._telmjd

    def set_source_type(self, source_type: str) -> None:
        """
        Update the intent(s) associated with the field based on given source
        type(s).

        Source types from VLA datasets are translated to equivalent ALMA
        Pipeline intents.

        Args:
            source_type: String containing the source type(s) (aka intents)
                associated with the field.
        """
        source_type = source_type.strip().upper()

        # replace any VLA source_type with pipeline/ALMA intents
        source_type = source_type.replace('SOURCE', 'TARGET')
        source_type = source_type.replace('GAIN', 'PHASE')
        source_type = source_type.replace('FLUX', 'AMPLITUDE')

        for intent in ['BANDPASS', 'PHASE', 'AMPLITUDE', 'TARGET', 'POINTING',
                       'WVR', 'ATMOSPHERE', 'SIDEBAND', 'POLARIZATION',
                       'POLANGLE', 'POLLEAKAGE', 'CHECK', 'DIFFGAINREF',
                       'DIFFGAINSRC', 'UNKNOWN', 'SYSTEM_CONFIGURATION']:
            if source_type.find(intent) != -1:
                self.intents.add(intent)

    def set_zd_telmjd(self, observatory: str) -> None:
        """Calculate and set the zenith distance at the observation mid-time.

        Args:
            observatory: Name of the observatory (e.g., 'VLA', 'ALMA').
        """
        # Mean observing time
        mjd_epoch = datetime.datetime(1858, 11, 17)
        start_time = mjd_epoch + datetime.timedelta(seconds=min(self.time))
        end_time = mjd_epoch + datetime.timedelta(seconds=max(self.time))
        mid_time = utils.obs_midtime(start_time, end_time)

        # Calculate zenith distance using CASA measures
        zd_rad = utils.compute_zenith_distance(
            field_direction=self._mdirection,
            epoch=mid_time,
            observatory=observatory,
        )

        self._zd = casa_tools.quanta.convert(zd_rad, 'deg')
        self._telmjd = mid_time['m0']

    def __str__(self) -> str:
        return '<Field {id}: name=\'{name}\' intents=\'{intents}\'>'.format(
            id=self.identifier, name=self.name,
            intents=','.join(self.intents))
