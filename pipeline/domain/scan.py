"""Pydantic-based Scan domain object prototype for Phase 5 modernization."""

from __future__ import annotations

import datetime
import operator
import pprint
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field as PydanticField, PrivateAttr

import pipeline.infrastructure.utils as utils
from pipeline.infrastructure import casa_tools

if TYPE_CHECKING:  # Avoid circular import. Used only for type annotation.
    from pipeline.domain import Antenna, DataDescription, Field, SpectralWindow, State
    from pipeline.infrastructure.utils.casa_types import EpochDict

_pprinter = pprint.PrettyPrinter()


class Scan(BaseModel):
    """Scan domain object."""

    id: int | None = PydanticField(default=None, description='Scan number')
    antennas: list[Antenna] = PydanticField(default_factory=list)
    intents: list[str] = PydanticField(default_factory=list)
    fields: list[Field] = PydanticField(default_factory=list)
    states: list[State] = PydanticField(default_factory=list)
    data_descriptions: list[DataDescription] = PydanticField(default_factory=list)
    scan_times: dict[int, list[tuple[dict, dict]]] = PydanticField(default_factory=dict)

    _mean_intervals: dict[int, datetime.timedelta] = PrivateAttr(default_factory=dict)
    _start_time: EpochDict | None = PrivateAttr(default=None)
    _end_time: EpochDict | None = PrivateAttr(default=None)
    _exposure_time: dict[int, datetime.timedelta] = PrivateAttr(default_factory=dict)

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_default=True,
    )

    def __hash__(self) -> int:
        return hash((self.__class__, self.id))

    def model_post_init(self, __context: object) -> None:
        self.antennas = frozenset(self.antennas)
        self.fields = frozenset(self.fields)
        self.intents = frozenset(self.intents)
        self.states = frozenset(self.states)
        self.data_descriptions = frozenset(self.data_descriptions)

        int_seconds = {k: v[0][1]['value'] for k, v in self.scan_times.items()}
        self._mean_intervals = {k: datetime.timedelta(seconds=v) for k, v in int_seconds.items()}

        self._start_time = None
        self._end_time = None

        sorted_epochs = {
            spw_id: sorted(midpoints, key=lambda e: e[0]['m0']['value'])
            for spw_id, midpoints in self.scan_times.items()
        }

        qt = casa_tools.quanta
        mt = casa_tools.measures

        self._exposure_time = {}
        for spw_id, epochs in sorted_epochs.items():
            min_epoch, exposure = epochs[0]
            max_epoch = epochs[-1][0]

            half_exposure = qt.div(exposure, 2)
            min_val = qt.sub(mt.getvalue(min_epoch)['m0'], half_exposure)
            max_val = qt.add(mt.getvalue(max_epoch)['m0'], half_exposure)

            range_start_epoch = mt.epoch(v0=min_val, rf=mt.getref(min_epoch))
            range_end_epoch = mt.epoch(v0=max_val, rf=mt.getref(max_epoch))

            dt_start = utils.get_epoch_as_datetime(range_start_epoch)
            dt_end = utils.get_epoch_as_datetime(range_end_epoch)
            self._exposure_time[spw_id] = dt_end - dt_start

            if self._start_time is None or qt.lt(min_val, self._start_time['m0']):
                self._start_time = range_start_epoch

            if self._end_time is None or qt.gt(max_val, self._end_time['m0']):
                self._end_time = range_end_epoch

    def __repr__(self) -> str:
        mt = casa_tools.measures
        qt = casa_tools.quanta

        start_epoch = self.start_time
        end_epoch = self.end_time

        scan_times = {}
        for spw_id, interval in self._mean_intervals.items():
            interval_quanta = qt.unit('{0}s'.format(interval.total_seconds()))
            half_interval = qt.div(interval_quanta, 2)

            exposure = qt.unit('{0}s'.format(self._exposure_time[spw_id].total_seconds()))
            half_exposure = qt.div(exposure, 2)

            start_midpoint = qt.add(mt.getvalue(start_epoch)['m0'], half_interval)
            end_midpoint = qt.sub(mt.getvalue(end_epoch)['m0'], half_interval)

            e1 = mt.epoch(v0=start_midpoint, rf=start_epoch['refer'])
            e2 = mt.epoch(v0=end_midpoint, rf=end_epoch['refer'])

            scan_times[spw_id] = [(e1, interval_quanta), (e2, interval_quanta)]

        sort_by_id = lambda l: sorted(l, key=operator.attrgetter('id'))

        return (
            'Scan(id={id}, antennas={antennas!r}, intents={intents!r}, '
            'fields={fields!r}, states={states!r}, data_descriptions={dds!r}, '
            'scan_times={scan_times})'.format(
                id=self.id,
                antennas=sort_by_id(self.antennas),
                intents=sorted(self.intents),
                fields=sort_by_id(self.fields),
                states=sort_by_id(self.states),
                dds=sort_by_id(self.data_descriptions),
                scan_times=_pprinter.pformat(scan_times),
            )
        )

    def __str__(self) -> str:
        return (
            '<Scan #{id}: intents=\'{intents}\' start=\'{start}\' '
            'end=\'{end}\' duration=\'{duration}\'>'
        ).format(
            id=self.id,
            intents=','.join(self.intents),
            start=utils.get_epoch_as_datetime(self.start_time),
            end=utils.get_epoch_as_datetime(self.end_time),
            duration=str(self.time_on_source),
        )

    @property
    def start_time(self) -> EpochDict | None:
        """Return start time of the Scan as a CASA 'epoch' measure dictionary."""
        return self._start_time

    @property
    def end_time(self) -> EpochDict | None:
        """Return end time of the Scan as a CASA 'epoch' measure dictionary."""
        return self._end_time

    @property
    def time_on_source(self) -> datetime.timedelta:
        """Return time-on-source for the Scan."""
        start = utils.get_epoch_as_datetime(self.start_time)
        end = utils.get_epoch_as_datetime(self.end_time)
        return end - start

    def exposure_time(self, spw_id: int) -> datetime.timedelta:
        """Return exposure time for this Scan for given spectral window ID."""
        return self._exposure_time[spw_id]

    def mean_interval(self, spw_id: int) -> datetime.timedelta:
        """Return the mean sub-scan integration time for given spectral window ID."""
        return self._mean_intervals[spw_id]

    @property
    def spws(self) -> set[SpectralWindow]:
        """Return set of SpectralWindow objects for spectral windows in this Scan."""
        return {dd.spw for dd in self.data_descriptions}

    def to_dict(self) -> dict[str, Any]:
        """Export to dictionary (data fields only)."""
        return self.model_dump()

    def to_json(self) -> str:
        """Export to JSON string."""
        return self.model_dump_json()

    @classmethod
    def from_scan(cls, scan: Any) -> Scan | None:
        """Create from legacy Scan object for migration."""
        return cls(
            id=scan.id,
            antennas=list(scan.antennas),
            intents=list(scan.intents),
            fields=list(scan.fields),
            states=list(scan.states),
            data_descriptions=list(scan.data_descriptions),
            scan_times={},
        )


def upgrade_scan(scan_obj: Any) -> Scan | None:
    """Upgrade a legacy Scan object to Pydantic version."""
    if isinstance(scan_obj, Scan):
        return scan_obj

    if hasattr(scan_obj, 'antennas') and hasattr(scan_obj, 'intents'):
        return Scan.from_scan(scan_obj)

    return None
