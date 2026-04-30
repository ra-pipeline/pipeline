# Do not evaluate type annotations at definition time.
from __future__ import annotations

import datetime
import operator
import pprint
from typing import TYPE_CHECKING

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.utils as utils
from pipeline.infrastructure import casa_tools

if TYPE_CHECKING:  # Avoid circular import. Used only for type annotation.
    from pipeline.domain import Antenna, DataDescription, Field, SpectralWindow, State

_pprinter = pprint.PrettyPrinter()

LOG = infrastructure.get_logger(__name__)


class Scan:
    """A logical representation of a single scan.

    Attributes:
        id: The scan number within the MeasurementSet.
        antennas: Set of Antenna objects for antennas associated with this scan.
        intents: Set of Pipeline intents corresponding to the states associated
            with this scan.
        fields: Set of Field objects for fields associated with this scan.
        states: Set of State objects for states associated with this scan.
        data_descriptions: Set of DataDescription objects for data description
            entries associated with this scan.
    """
    def __init__(self, id: int | None = None, antennas: list[Antenna] | None = None, intents: list[str] | None = None,
                 fields: list[Field] | None = None, states: list[State] | None = None,
                 data_descriptions: list[DataDescription] | None = None, scan_times: dict | None = None) -> None:
        """
        Initialize a Scan object.

        Args:
            id: The scan number within the MeasurementSet.
            antennas: List of Antenna objects for antennas associated with this scan.
            intents: Set of Pipeline intents corresponding to the states
                associated with this scan.
            fields: List of Field objects for fields associated with this scan.
            states: List of State objects for states associated with this scan.
            data_descriptions: List of DataDescription objects for data
                description entries associated with this scan.
            scan_times: Dictionary mapping spectral window ID keys (for all
                spectral windows associated with this scan) to a list of
                2-tuples for all sub-scans, where each 2-tuple for a sub-scan
                contains the sub-scan epoch midpoint time and the sub-scan
                exposure time (for that spectral window). These are used to
                derive and store properties such as start-time, end-time,
                time-on-source.
        """
        self.id = id

        if antennas is None:
            antennas = []
        if intents is None:
            intents = []
        if fields is None:
            fields = []
        if states is None:
            states = []
        if data_descriptions is None:
            data_descriptions = []
        if scan_times is None:
            scan_times = {}

        self.antennas = frozenset(antennas)
        self.fields = frozenset(fields)
        self.intents = frozenset(intents)
        self.states = frozenset(states)
        self.data_descriptions = frozenset(data_descriptions)

        # the integration time should not vary per subscan, so we can
        # construct the integration-time-per-spw mapping directly from the
        # first subscan entry. The MS spec states that these integration 
        # values are given in seconds, which is just what we want
        int_seconds = {k: v[0][1]['value']
                       for k, v in scan_times.items()}
        self.__mean_intervals = {k: datetime.timedelta(seconds=v)
                                 for k, v in int_seconds.items()}

        # will hold the start and end epochs per spw
        self.__start_time = None
        self.__end_time = None

        # midpoints is a list of tuple of (midpoint epochs, integration time)
        sorted_epochs = {spw_id: sorted(midpoints, key=lambda e: e[0]['m0']['value'])
                         for spw_id, midpoints in scan_times.items()}

        qt = casa_tools.quanta
        mt = casa_tools.measures

        self.__exposure_time = {}
        for spw_id, epochs in sorted_epochs.items():
            (min_epoch, exposure) = epochs[0]
            max_epoch = epochs[-1][0]

            # add and subtract half the exposure to get the start and
            # end exposure times for this spw in the scan
            half_exposure = qt.div(exposure, 2)
            min_val = qt.sub(mt.getvalue(min_epoch)['m0'], half_exposure)
            max_val = qt.add(mt.getvalue(max_epoch)['m0'], half_exposure)

            # recalculate epochs for these adjusted times, which we can use to
            # set the mean interval for this spw and potentially for the
            # global start and end epochs for this scan
            range_start_epoch = mt.epoch(v0=min_val, rf=mt.getref(min_epoch))
            range_end_epoch = mt.epoch(v0=max_val, rf=mt.getref(max_epoch))

            dt_start = utils.get_epoch_as_datetime(range_start_epoch)
            dt_end = utils.get_epoch_as_datetime(range_end_epoch)
            self.__exposure_time[spw_id] = dt_end - dt_start            

            # set start time as earliest time over all spectral windows
            if self.__start_time is None or qt.lt(min_val, self.__start_time['m0']):
                self.__start_time = range_start_epoch

            # set end time as latest time over all spectral windows
            if self.__end_time is None or qt.gt(max_val, self.__end_time['m0']):
                self.__end_time = range_end_epoch

    def __repr__(self) -> str:
        mt = casa_tools.measures
        qt = casa_tools.quanta

        start_epoch = self.start_time
        end_epoch = self.end_time

        scan_times = {}
        for spw_id, interval in self.__mean_intervals.items():
            interval_quanta = qt.unit('{0}s'.format(interval.total_seconds()))
            half_interval = qt.div(interval_quanta, 2)

            exposure = qt.unit('{0}s'.format(self.__exposure_time[spw_id].total_seconds()))
            half_exposure = qt.div(exposure, 2)

            start_midpoint = qt.add(mt.getvalue(start_epoch)['m0'],
                                    half_interval)
            end_midpoint = qt.sub(mt.getvalue(end_epoch)['m0'],
                                  half_interval)

            e1 = mt.epoch(v0=start_midpoint, rf=start_epoch['refer'])
            e2 = mt.epoch(v0=end_midpoint, rf=end_epoch['refer'])

            scan_times[spw_id] = [(e1, interval_quanta),
                                  (e2, interval_quanta)]

        sort_by_id = lambda l: sorted(l, key=operator.attrgetter('id'))

        return ('Scan(id={id}, antennas={antennas!r}, intents={intents!r}, '
                'fields={fields!r}, states={states!r}, data_descriptions={dds!r}, '
                'scan_times={scan_times})'.format(
                    id=self.id,
                    antennas=sort_by_id(self.antennas),
                    intents=sorted(self.intents),
                    fields=sort_by_id(self.fields),
                    states=sort_by_id(self.states),
                    dds=sort_by_id(self.data_descriptions),
                    scan_times=_pprinter.pformat(scan_times)))

    def __str__(self) -> str:
        return ('<Scan #{id}: intents=\'{intents}\' start=\'{start}\' '
                'end=\'{end}\' duration=\'{duration}\'>'.format(
                    id=self.id,
                    intents=','.join(self.intents),
                    start=utils.get_epoch_as_datetime(self.start_time), 
                    end=utils.get_epoch_as_datetime(self.end_time), 
                    duration=str(self.time_on_source)))

    @property
    def start_time(self) -> dict:
        """Return start time of the Scan as a CASA 'epoch' measure dictionary."""
        return self.__start_time

    @property
    def end_time(self) -> dict:
        """Return end time of the Scan as a CASA 'epoch' measure dictionary."""
        return self.__end_time

    @property
    def time_on_source(self) -> datetime.timedelta:
        """Return time-on-source for the Scan."""
        # adding up the scan exposures does not give us the total time on 
        # source. Instead we should simply subtract the scan end time from the 
        # scan start time to calculate the total time
        start = utils.get_epoch_as_datetime(self.start_time)
        end = utils.get_epoch_as_datetime(self.end_time)
        return end - start

    def exposure_time(self, spw_id: int) -> datetime.timedelta:
        """
        Return exposure time for this Scan for given spectral window ID.

        Args:
            spw_id: Numerical identifier of spectral window to select.

        Returns:
            Exposure time for this Scan and given spectral window ID.
        """
        return self.__exposure_time[spw_id]

    def mean_interval(self, spw_id: int) -> datetime.timedelta:
        """
        Return the "mean" sub-scan integration time for given spectral window ID.

        Note: at present, it is assumed that the integration time does not vary
        per sub-scan, and it therefore takes the integration time from the first
        sub-scan in this Scan to be representative (i.e. it does not take the
        mean from all sub-scan integration times).

        Args:
            spw_id: Numerical identifier of spectral window to select.

        Returns:
            Sub-scan integration time for given spectral window ID.
        """
        return self.__mean_intervals[spw_id]

    @property
    def spws(self) -> set[SpectralWindow]:
        """Return set of SpectralWindow objects for spectral windows associated
        with this Scan."""
        return {dd.spw for dd in self.data_descriptions}
