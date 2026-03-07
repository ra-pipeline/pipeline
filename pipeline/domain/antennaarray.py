"""Pydantic-based AntennaArray domain object prototype for Phase 5 modernization."""

from __future__ import annotations

import collections
import itertools
import math
import warnings
from typing import Any, Sequence

import numpy
from pydantic import BaseModel, ConfigDict, Field as PydanticField, PrivateAttr

from pipeline.domain import measures
from pipeline.domain.antenna import Antenna
from pipeline.domain.measures import Distance, DistanceUnits
from pipeline.infrastructure import casa_tools

Baseline = collections.namedtuple('Baseline', 'antenna1 antenna2 length')


class AntennaArray(BaseModel):
    """Pydantic-based antenna array domain object."""

    name: str = PydanticField(..., description='Name of the observatory')
    position: dict[str, Any] = PydanticField(..., description='CASA position measure')
    antennas: list[Any] = PydanticField(
        default_factory=list,
        description='Antenna objects in the array',
    )

    baseline_lookup: numpy.ndarray | None = PydanticField(default=None, exclude=True)
    baselines_m: numpy.ndarray | None = PydanticField(default=None, exclude=True)
    baseline_min: Baseline | None = PydanticField(default=None, exclude=True)
    baseline_max: Baseline | None = PydanticField(default=None, exclude=True)
    _baselines: list[Baseline] = PrivateAttr(default_factory=list)

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_default=True,
    )

    def __init__(
        self,
        name: str | None = None,
        position: dict[str, Any] | None = None,
        antennas: list[Any] | None = None,
        **data: Any,
    ) -> None:
        """Create an AntennaArray.

        The legacy pipeline code constructs arrays positionally as
        ``AntennaArray(name, position, antennas)``.
        """
        if name is not None and 'name' not in data:
            data['name'] = name
        if position is not None and 'position' not in data:
            data['position'] = position
        if antennas is not None and 'antennas' not in data:
            data['antennas'] = antennas
        super().__init__(**data)

    def model_post_init(self, __context: object) -> None:
        self.baseline_lookup = self._calc_baseline_lookup(self.antennas)
        self.baselines_m = self.baseline_lookup[
            numpy.tril_indices_from(self.baseline_lookup, -1)
        ]

        mask_self_corr = numpy.full(self.baseline_lookup.shape, True)
        numpy.fill_diagonal(mask_self_corr, False)
        ma = numpy.ma.array(self.baseline_lookup, mask=~mask_self_corr)

        if len(self.antennas) <= 1:
            self.baseline_min = None
            self.baseline_max = None
        else:
            min_x, min_y = numpy.unravel_index(
                indices=numpy.ma.argmin(ma, axis=None),
                shape=self.baseline_lookup.shape,
            )
            self.baseline_min = Baseline(
                antenna1=self.get_antenna(id=min_x),
                antenna2=self.get_antenna(id=min_y),
                length=Distance(
                    value=self.baseline_lookup[min_x][min_y],
                    units=DistanceUnits.METRE,
                ),
            )

            max_x, max_y = numpy.unravel_index(
                indices=numpy.argmax(ma, axis=None),
                shape=self.baseline_lookup.shape,
            )
            self.baseline_max = Baseline(
                antenna1=self.get_antenna(id=max_x),
                antenna2=self.get_antenna(id=max_y),
                length=Distance(
                    value=self.baseline_lookup[max_x][max_y],
                    units=DistanceUnits.METRE,
                ),
            )

        self._baselines = self.baselines_for_antennas([a.id for a in self.antennas])

    def __repr__(self) -> str:
        return 'AntennaArray({0!r}, {1}, {2!r})'.format(
            self.name,
            self.position,
            self.antennas,
        )

    def __hash__(self) -> int:
        return hash((self.__class__, self.name, tuple(a.id for a in self.antennas)))

    @property
    def elevation(self) -> dict[str, Any]:
        """Return array elevation as a CASA quantity."""
        return self.position['m2']

    @property
    def latitude(self) -> dict[str, Any]:
        """Return array latitude as a CASA quantity."""
        return self.position['m1']

    @property
    def longitude(self) -> dict[str, Any]:
        """Return array longitude as a CASA quantity."""
        return self.position['m0']

    def baselines_for_antennas(self, antenna_ids: Sequence[int]) -> list[Baseline]:
        """Return a list of Baseline tuples for input antenna IDs."""
        unique_ids = set(antenna_ids)
        return [
            Baseline(
                antenna1=self.get_antenna(id=ant1),
                antenna2=self.get_antenna(id=ant2),
                length=Distance(
                    self.baseline_lookup[ant1][ant2],
                    DistanceUnits.METRE,
                ),
            )
            for ant1, ant2 in itertools.combinations(unique_ids, 2)
        ]

    @property
    def baselines(self) -> list[Baseline]:
        """Return a list of Baseline tuples for all antennas in the array."""
        warnings.warn(
            'AntennaArray.baselines is deprecated. Use AntennaArray.baselines_m instead.',
            category=DeprecationWarning,
            stacklevel=2,
        )
        return self._baselines

    @staticmethod
    def _calc_baseline_lookup(antennas: list[Any]) -> numpy.ndarray:
        if len(antennas) < 2:
            return numpy.zeros(shape=(len(antennas),) * 2)

        max_id = max(a.id for a in antennas) + 1
        baselines = numpy.zeros((max_id, max_id))

        qa = casa_tools.quanta

        def diff(ant1: Antenna, ant2: Antenna, attr: str) -> float:
            v1 = qa.getvalue(ant1.offset[attr])[0]
            v2 = qa.getvalue(ant2.offset[attr])[0]
            return v1 - v2

        for ant1, ant2 in itertools.combinations(antennas, 2):
            baseline_m = math.sqrt(
                diff(ant1, ant2, 'longitude offset') ** 2
                + diff(ant1, ant2, 'latitude offset') ** 2
                + diff(ant1, ant2, 'elevation offset') ** 2
            )
            baselines[ant1.id][ant2.id] = baseline_m
            baselines[ant2.id][ant1.id] = baseline_m

        return baselines

    def get_offset(self, antenna: Any) -> tuple[Distance, Distance]:
        """Get the offset of the given antenna from the centre of the array."""
        dx = antenna.offset['longitude offset']['value']
        dy = antenna.offset['latitude offset']['value']

        x_offset = measures.Distance(dx, measures.DistanceUnits.METRE)
        y_offset = measures.Distance(dy, measures.DistanceUnits.METRE)

        return x_offset, y_offset

    def get_baseline(self, antenna1: int | str, antenna2: int | str) -> Baseline | None:
        """Get the baseline distance between two antennas."""
        def get_antenna_by_id_then_name(predicate: int | str) -> Any | None:
            try:
                return self.get_antenna(id=int(predicate))
            except (ValueError, IndexError):
                try:
                    return self.get_antenna(name=str(predicate))
                except IndexError:
                    return None

        ant1 = get_antenna_by_id_then_name(antenna1)
        ant2 = get_antenna_by_id_then_name(antenna2)
        if ant1 is None or ant2 is None:
            return None

        return Baseline(
            ant1,
            ant2,
            Distance(
                self.baseline_lookup[ant1.id][ant2.id],
                DistanceUnits.METRE,
            ),
        )

    def get_antenna(self, id: int | None = None, name: str | None = None) -> Any:
        """Return Antenna object for given antenna ID or name."""
        if id is not None:
            matches = [ant for ant in self.antennas if ant.id == id]
            if not matches:
                raise IndexError('No antenna with ID {0}'.format(id))
            return matches[0]

        if name is not None:
            matches = [ant for ant in self.antennas if ant.name == name]
            if not matches:
                raise IndexError('No antenna with name {0}'.format(name))
            return matches[0]

        raise Exception('No id or name given to get_antenna')

    @property
    def median_direction(self) -> dict[str, Any]:
        """Return the median center direction for the array."""
        qt = casa_tools.quanta
        longs = [qt.getvalue(antenna.longitude) for antenna in self.antennas]
        lats = [qt.getvalue(antenna.latitude) for antenna in self.antennas]

        med_lon = numpy.median(numpy.array(longs))
        med_lat = numpy.median(numpy.array(lats))

        mt = casa_tools.measures
        return mt.direction(
            v0=qt.quantity(med_lon, 'rad'),
            v1=qt.quantity(med_lat, 'rad'),
        )

    def __str__(self) -> str:
        names = ', '.join([antenna.name for antenna in self.antennas])
        return 'AntennaArray({0})'.format(names)

    def to_dict(self) -> dict[str, Any]:
        """Export to dictionary (data fields only)."""
        data = self.model_dump(
            exclude={
                'baseline_lookup',
                'baselines_m',
                'baseline_min',
                'baseline_max',
            }
        )
        return data

    def to_json(self) -> str:
        """Export to JSON string."""
        return self.model_dump_json(
            exclude={
                'baseline_lookup',
                'baselines_m',
                'baseline_min',
                'baseline_max',
            },
        )

    @classmethod
    def from_antenna_array(cls, array: Any) -> AntennaArray:
        """Create from legacy AntennaArray object for migration."""
        return cls(name=array.name, position=array.position, antennas=array.antennas)


def upgrade_antenna_array(array_obj: Any) -> AntennaArray | None:
    """Upgrade a legacy AntennaArray object to Pydantic version."""
    if isinstance(array_obj, AntennaArray):
        return array_obj

    if hasattr(array_obj, 'antennas') and hasattr(array_obj, 'position'):
        return AntennaArray.from_antenna_array(array_obj)

    return None
