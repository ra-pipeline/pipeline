"""Pydantic-based SpectralWindow domain object prototype for Phase 5 modernization."""

from __future__ import annotations

import decimal
import itertools
import json
import operator
from typing import TYPE_CHECKING, Any

import numpy
from pydantic import BaseModel, ConfigDict, Field as PydanticField, PrivateAttr, field_validator

from pipeline import infrastructure
from pipeline.domain import measures
from pipeline.infrastructure import casa_tools

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

LOG = infrastructure.logging.get_logger(__name__)


class ArithmeticProgression:
    """A representation of an arithmetic progression that can generate sequence elements on demand."""

    __slots__ = ('start', 'delta', 'num_terms')

    def __getstate__(self) -> tuple[int | float, int | float, int]:
        return self.start, self.delta, self.num_terms

    def __setstate__(self, state: tuple[int | float, int | float, int]) -> None:
        self.start, self.delta, self.num_terms = state

    def __init__(self, start: int | float, delta: int | float, num_terms: int) -> None:
        """Initialize an ArithmeticProgression object.

        Args:
            start: Value of first element in the progression.
            delta: Common difference between each element in the progression.
            num_terms: Number of elements in the progression.
        """
        self.start = start
        self.delta = delta
        self.num_terms = num_terms

    def __iter__(self):
        g = itertools.count(self.start, self.delta)
        return itertools.islice(g, 0, self.num_terms)

    def __len__(self) -> int:
        return self.num_terms

    def __getitem__(self, index: int):
        if abs(index) >= self.num_terms:
            raise IndexError
        if index < 0:
            index += self.num_terms
        return self.start + index * self.delta


def compress(values: Sequence[int | float]) -> Sequence[int | float] | ArithmeticProgression:
    """Compress (if possible) a sequence of values.

    If the numbers in the given list constitute an arithmetic progression,
    return an ArithmeticProgression object that summarises it as such. If
    the list cannot be summarised as a simple arithmetic progression,
    return the list as given.
    """
    deltas = set(numpy.diff(values))
    if len(deltas) == 1:
        delta = deltas.pop()
        return ArithmeticProgression(values[0], delta, len(values))
    else:
        return values


class ChannelList:
    """A container/generator for Channel objects.

    A spectral window can contain thousands of channels. Rather than store all of
    these objects, a ChannelList generates and returns them lazily, on-demand.
    """

    def __init__(
        self,
        chan_freqs: Sequence[int | float] | ArithmeticProgression,
        chan_widths: Sequence[int | float] | ArithmeticProgression,
        effbw: Sequence[int | float] | ArithmeticProgression,
    ) -> None:
        """Initialize a ChannelList object.

        Args:
            chan_freqs: Sequence or ArithmeticProgression of center frequency of
                channel (in Hertz) for all channels in ChannelList.
            chan_widths: Sequence or ArithmeticProgression of channel width (in
                Hertz) for all channels in ChannelList.
            effbw: Sequence or ArithmeticProgression of effective bandwidth (in
                Hertz) for all channels in ChannelList.
        """
        assert len(chan_freqs) == len(chan_widths) == len(effbw)
        self.chan_freqs = chan_freqs
        self.chan_widths = chan_widths
        self.chan_effbws = effbw

    def __iter__(self) -> Iterator[Channel]:
        raw_channel_data = list(zip(self.chan_freqs, self.chan_widths, self.chan_effbws))
        for chan_centre, chan_width, chan_effective_bw in raw_channel_data:
            yield self.__create_channel(chan_centre, chan_width, chan_effective_bw)

    def __len__(self) -> int:
        return len(self.chan_freqs)

    def __getitem__(self, index: int) -> Channel:
        return self.__create_channel(
            self.chan_freqs[index],
            self.chan_widths[index],
            self.chan_effbws[index],
        )

    @staticmethod
    def __create_channel(
        centre: int | float,
        width: int | float,
        effective_bw: int | float,
    ) -> Channel:
        """Return a Channel object for given parameters.

        Args:
            centre: Center frequency of the channel (in Hertz).
            width: Frequency width of the channel (in Hertz).
            effective_bw: Effective bandwidth of the channel (in Hertz).

        Returns:
            Channel object.
        """
        dec_centre = decimal.Decimal(centre)
        dec_width = decimal.Decimal(width)
        # The abs() call is not strictly necessary as Channel extends
        # FrequencyRange, whose .set() method swaps low and high when
        # low > high.
        delta = abs(dec_width) / decimal.Decimal(2)

        f_lo = measures.Frequency(dec_centre - delta, measures.FrequencyUnits.HERTZ)
        f_hi = measures.Frequency(dec_centre + delta, measures.FrequencyUnits.HERTZ)
        f_bw = measures.Frequency(effective_bw, measures.FrequencyUnits.HERTZ)
        return Channel(f_lo, f_hi, f_bw)


class Channel:
    """Representation of a channel within a spectral window."""

    __slots__ = ('frequency_range', 'effective_bw')

    def __init__(
        self,
        start: measures.Frequency,
        end: measures.Frequency,
        effective_bw: measures.Frequency,
    ) -> None:
        """Creates a new Channel with the given start and end frequency and effective bandwidth."""
        self.frequency_range = measures.FrequencyRange(start, end)
        self.effective_bw = effective_bw

    def __getstate__(self) -> tuple[measures.FrequencyRange, measures.Frequency]:
        return self.frequency_range, self.effective_bw

    def __setstate__(self, state: tuple[measures.FrequencyRange, measures.Frequency]) -> None:
        self.frequency_range, self.effective_bw = state

    def __eq__(self, other: Channel) -> bool:
        if not isinstance(other, Channel):
            return False
        if other.frequency_range != self.frequency_range:
            return False
        if other.effective_bw != self.effective_bw:
            return False
        return True

    def __ne__(self, other: Channel) -> bool:
        return not self.__eq__(other)

    def __repr__(self) -> str:
        return 'Channel(%s, %s, %s)' % (self.frequency_range.low, self.frequency_range.high, self.effective_bw)

    def getCentreFrequency(self) -> measures.Frequency:
        """Return the frequency at the centre of this channel."""
        return self.frequency_range.getCentreFrequency()

    def getWidth(self) -> measures.Frequency:
        """Return the frequency width of this channel."""
        return self.frequency_range.getWidth()

    @property
    def low(self) -> measures.Frequency:
        return self.frequency_range.low

    @property
    def high(self) -> measures.Frequency:
        return self.frequency_range.high


class SpectralWindowWithChannelSelection:
    """Proxy that applies a channel selection to a spectral window."""

    def __init__(self, subject: Any, channels: Iterable[int]) -> None:
        self._subject = subject

        channels = sorted(list(channels))

        # prepare a string representation of the number of channels. If all
        # channels are specified for this spw, just specify the spw in the
        # string representation
        if set(channels).issuperset(set(range(0, subject.num_channels))):
            ranges = []
        else:
            ranges = []
            for _, g in itertools.groupby(enumerate(channels), lambda i_x: i_x[0] - i_x[1]):
                rng = list(map(operator.itemgetter(1), g))
                if len(rng) == 1:
                    ranges.append('%s' % rng[0])
                else:
                    ranges.append('%s~%s' % (rng[0], rng[-1]))
        self._channels = ';'.join(ranges)

    def __getattr__(self, name):
        return getattr(self._subject, name)

    @property
    def id(self) -> str:
        """Return the spectral window ID including channel selection."""
        channels = ':%s' % self._channels if self._channels else ''
        return f'{self._subject.id}{channels}'


def match_spw_basename(name1: str, name2: str) -> bool:
    """Determine if one SPW name is a suffix of the other.

    Raises ValueError if either name is shorter than 5 characters.
    """
    min_length = 5
    if len(name1) < min_length or len(name2) < min_length:
        msg = (
            f"SPW names too short for comparison: name1='{name1}', name2='{name2}'. "
            f"Minimum length is {min_length} characters."
        )
        LOG.error(msg)
        raise ValueError(msg)

    return name1.endswith(name2) or name2.endswith(name1)


class SpectralWindow(BaseModel):
    """Spectral window domain object."""

    id: int = PydanticField(..., description='Spectral window ID')
    name: str = PydanticField(..., description='Spectral window name')
    type: str = PydanticField(..., description='Spectral window type')
    bandwidth: measures.Frequency | float = PydanticField(
        ..., description='Bandwidth in Hz'
    )
    ref_freq: dict[str, measures.Frequency] = PydanticField(..., description='CASA frequency measure dictionary')
    mean_freq: float = PydanticField(..., description='Mean frequency in Hz')
    chan_freqs: Sequence[int | float] = PydanticField(..., description='Channel center frequencies')
    chan_widths: Sequence[int | float] = PydanticField(..., description='Channel widths')
    chan_effective_bws: Sequence[int | float] = PydanticField(..., description='Channel effective bandwidths')
    sideband: str | int = PydanticField(..., description='Sideband')
    baseband: str | int = PydanticField(..., description='Baseband')
    receiver: str | None = PydanticField(default=None, description='Receiver type')
    freq_lo: list[float] | numpy.ndarray | None = PydanticField(
        default=None,
        description='LO frequencies',
    )
    band: str = PydanticField(default='Unknown', description='Frequency band')
    spectralspec: str | None = PydanticField(default=None, description='SpectralSpec name')
    transitions: list[str] | None = PydanticField(default=None, description='Spectral transitions')
    sdm_num_bin: int | None = PydanticField(default=None, description='SDM num bin')
    correlation_bits: str | None = PydanticField(default=None, description='Correlation bits')
    median_receptor_angle: numpy.ndarray | None = PydanticField(default=None, description='Median receptor angle')
    specline_window: bool = PydanticField(default=False, description='Spectral line window flag')
    grouping_id: str | None = PydanticField(default=None, description='Grouping ID')
    intents: set[str] = PydanticField(default_factory=set, description='Observing intents')

    mean_frequency: measures.Frequency | None = PydanticField(default=None, exclude=True)
    channels: ChannelList | None = PydanticField(default=None, exclude=True)

    _min_frequency: measures.Frequency | None = PrivateAttr(default=None)
    _max_frequency: measures.Frequency | None = PrivateAttr(default=None)
    _centre_frequency: measures.Frequency | None = PrivateAttr(default=None)
    _ref_frequency: measures.Frequency | None = PrivateAttr(default=None)
    _ref_frequency_frame: str | None = PrivateAttr(default=None)

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_default=True,
    )

    @field_validator('chan_freqs', 'chan_widths', 'chan_effective_bws', 'transitions', mode='before')
    @classmethod
    def convert_numpy_to_list(cls, v: Any) -> list[int | float] | list[str] | Any:
        """Convert numpy arrays to lists for Pydantic validation."""
        if isinstance(v, numpy.ndarray):
            return v.tolist()
        return v

    def model_post_init(self, __context: object) -> None:
        if self.transitions is None:
            self.transitions = ['Unknown']

        ref_freq_hz = casa_tools.quanta.convertfreq(self.ref_freq['m0'], 'Hz')
        ref_freq_val = casa_tools.quanta.getvalue(ref_freq_hz)[0]
        self._ref_frequency = measures.Frequency(ref_freq_val, measures.FrequencyUnits.HERTZ)
        self._ref_frequency_frame = self.ref_freq['refer']

        if not isinstance(self.bandwidth, measures.Frequency):
            self.bandwidth = measures.Frequency(
                self.bandwidth,
                measures.FrequencyUnits.HERTZ,
            )
        self.mean_frequency = measures.Frequency(self.mean_freq, measures.FrequencyUnits.HERTZ)

        self.name = str(self.name)
        self.sideband = str(self.sideband)
        self.baseband = str(self.baseband)

        if self.freq_lo is not None:
            self.freq_lo = [
                measures.Frequency(freq, measures.FrequencyUnits.HERTZ)
                for freq in self.freq_lo
            ]

        chan_freqs = compress(self.chan_freqs)
        chan_widths = compress(self.chan_widths)
        chan_effective_bws = compress(self.chan_effective_bws)
        self.channels = ChannelList(chan_freqs, chan_widths, chan_effective_bws)

        self._min_frequency = min(self.channels, key=lambda r: r.low).low
        self._max_frequency = max(self.channels, key=lambda r: r.high).high
        self._centre_frequency = (self._min_frequency + self._max_frequency) / 2.0

    @property
    def ref_frequency(self) -> measures.Frequency:
        """Return the reference frequency."""
        return self._ref_frequency

    @property
    def frame(self) -> str:
        """Return the reference frame code of the SpectralWindow."""
        return self._ref_frequency_frame

    @property
    def min_frequency(self) -> measures.Frequency:
        """Return the minimum frequency of the SpectralWindow."""
        return self._min_frequency

    @property
    def max_frequency(self) -> measures.Frequency:
        """Return the maximum frequency of the SpectralWindow."""
        return self._max_frequency

    @property
    def centre_frequency(self) -> measures.Frequency:
        """Return the center frequency of the SpectralWindow."""
        return self._centre_frequency

    @property
    def num_channels(self) -> int:
        """Return the number of channels in the SpectralWindow."""
        return len(self.channels)

    def channel_range(
        self,
        minfreq: measures.Frequency,
        maxfreq: measures.Frequency,
    ) -> tuple[int, int] | tuple[None, None]:
        """Return the channel range for given minimum/maximum frequency."""
        nchan = self.num_channels
        if maxfreq < self.min_frequency:
            return None, None
        if minfreq > self.max_frequency:
            return None, None

        chan_min = 0
        if self.channels[0].low < self.channels[nchan - 1].low:
            for i in range(nchan):
                if self.channels[i].low > minfreq:
                    break
                chan_min = i
        else:
            for i in range(nchan):
                if self.channels[i].high < maxfreq:
                    break
                chan_min = i

        chan_max = nchan - 1
        if self.channels[0].low < self.channels[nchan - 1].low:
            for i in range(nchan - 1, -1, -1):
                if self.channels[i].high < maxfreq:
                    break
                chan_max = i
        else:
            for i in range(nchan - 1, -1, -1):
                if self.channels[i].low > minfreq:
                    break
                chan_max = i

        return chan_min, chan_max

    def __repr__(self) -> str:
        chan_freqs = self._sequence_to_list(self.channels.chan_freqs)
        chan_widths = self._sequence_to_list(self.channels.chan_widths)
        chan_effective_bws = self._sequence_to_list(self.channels.chan_effbws)

        return (
            'SpectralWindow({0!r}, {1!r}, {2!r}, {3!r}, {4!r}, {5!r}, {6}, {7}, {8}, {9!r}, {10!r}, {11!r}, '
            '{12!r}, {13}, {14}, {15!r}, {16}, {17})'
        ).format(
            self.id,
            self.name,
            self.type,
            float(self.bandwidth.to_units(measures.FrequencyUnits.HERTZ)),
            dict(
                m0={
                    'unit': 'Hz',
                    'value': float(
                        self.ref_frequency.to_units(measures.FrequencyUnits.HERTZ)
                    ),
                },
                refer=self.frame,
                type='frequency',
            ),
            float(self.mean_frequency.to_units(measures.FrequencyUnits.HERTZ)),
            'numpy.array(%r)' % chan_freqs,
            'numpy.array(%r)' % chan_widths,
            'numpy.array(%r)' % chan_effective_bws,
            self.sideband,
            self.baseband,
            self.band,
            self.transitions,
            self.sdm_num_bin,
            self.correlation_bits,
            self.median_receptor_angle,
            self.specline_window,
            self.grouping_id,
        )

    def __hash__(self) -> int:
        return hash((self.__class__, self.id, self.name, self.type))

    def __str__(self) -> str:
        args = [
            str(x)
            for x in [self.id, self.centre_frequency, self.bandwidth, self.type]
        ]
        return 'SpectralWindow({0})'.format(', '.join(args))

    def _sequence_to_list(
        self,
        values: Sequence[int | float] | ArithmeticProgression,
    ) -> list[float]:
        if isinstance(values, ArithmeticProgression):
            return list(values)
        if isinstance(values, numpy.ndarray):
            return values.tolist()
        return list(values)

    def to_dict(self) -> dict[str, Any]:
        """Export to dictionary with primitive values."""
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'bandwidth': float(
                self.bandwidth.to_units(measures.FrequencyUnits.HERTZ)
            ),
            'ref_freq': self.ref_freq,
            'mean_freq': float(
                self.mean_frequency.to_units(measures.FrequencyUnits.HERTZ)
            ),
            'chan_freqs': self._sequence_to_list(self.channels.chan_freqs),
            'chan_widths': self._sequence_to_list(self.channels.chan_widths),
            'chan_effective_bws': self._sequence_to_list(self.channels.chan_effbws),
            'sideband': self.sideband,
            'baseband': self.baseband,
            'receiver': self.receiver,
            'freq_lo': None
            if self.freq_lo is None
            else [
                float(freq.to_units(measures.FrequencyUnits.HERTZ))
                for freq in self.freq_lo
            ],
            'band': self.band,
            'spectralspec': self.spectralspec,
            'transitions': self.transitions,
            'sdm_num_bin': self.sdm_num_bin,
            'correlation_bits': self.correlation_bits,
            'median_receptor_angle': self.median_receptor_angle,
            'specline_window': self.specline_window,
            'grouping_id': self.grouping_id,
        }

    def to_json(self) -> str:
        """Export to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SpectralWindow:
        """Create from dictionary."""
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> SpectralWindow:
        """Create from JSON string."""
        return cls.model_validate_json(json_str)
