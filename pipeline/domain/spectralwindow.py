"""
Store frequency information of MeasurementSet.

This module provides classes to store logical representation of spectral
windows, channel frequency information, and channel selection.
"""

# Do not evaluate type annotations at definition time.
from __future__ import annotations

import decimal
import itertools
import operator
from typing import Iterable, Iterator, Sequence

import numpy

from pipeline.infrastructure import casa_tools

from . import measures


class ArithmeticProgression:
    """
    A representation of an arithmetic progression that can generate sequence
    elements on demand.
    """
    __slots__ = ('start', 'delta', 'num_terms')

    def __getstate__(self) -> tuple[int | float, int | float, int]:
        return self.start, self.delta, self.num_terms

    def __setstate__(self, state: tuple[int | float, int | float, int]) -> None:
        self.start, self.delta, self.num_terms = state

    def __init__(self, start: int | float, delta: int | float, num_terms: int) -> None:
        """
        Initialize an ArithmeticProgression object.

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
    """
    Compress (if possible) a sequence of values.

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
    """
    A container/generator for Channel objects.

    A spectral window can contain thousands of channels. Rather than store all of
    these objects, a ChannelList generates and returns them lazily, on-demand.
    """
    def __init__(self,
                 chan_freqs: Sequence[int | float] | ArithmeticProgression,
                 chan_widths: Sequence[int | float] | ArithmeticProgression,
                 effbw: Sequence[int | float] | ArithmeticProgression) -> None:
        """
        Initialize a ChannelList object.

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
        return self.__create_channel(self.chan_freqs[index],
                                     self.chan_widths[index],
                                     self.chan_effbws[index])

    @staticmethod
    def __create_channel(centre: int | float, width: int | float, effective_bw: int | float) -> Channel:
        """
        Return a Channel object for given parameters.

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

        f_lo = measures.Frequency(dec_centre - delta,
                                  measures.FrequencyUnits.HERTZ)
        f_hi = measures.Frequency(dec_centre + delta,
                                  measures.FrequencyUnits.HERTZ)
        f_bw = measures.Frequency(effective_bw,
                                  measures.FrequencyUnits.HERTZ)
        return Channel(f_lo, f_hi, f_bw)


class Channel:
    """
    Representation of a channel within a spectral window.

    This object can be considered as a FrequencyRange object plus an effective
    bandwidth property. It provides the same interface as a FrequencyRange.

    Attributes:
        frequency_range: FrequencyRange object denoting the low- and high-end
            frequencies of this channel (in Hertz).
        effective_bw: The effective bandwidth of this channel (in Hertz).
    """
    __slots__ = ('frequency_range', 'effective_bw')

    def __init__(self, start: measures.Frequency, end: measures.Frequency, effective_bw: measures.Frequency) -> None:
        """Creates a new Channel with the given start and end frequency and
        effective bandwidth.

        Args:
            start: Start frequency of channel (in Hertz).
            end: End frequency of channel (in Hertz).
            effective_bw: Effective bandwidth of channel (in Hertz).
        """
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
        return 'Channel(%s, %s, %s)' % (self.frequency_range.low,
                                        self.frequency_range.high,
                                        self.effective_bw)

    @property
    def low(self) -> measures.Frequency:
        """Return the low end frequency of the Channel."""
        return self.frequency_range.low

    @property
    def high(self) -> measures.Frequency:
        """Returns the high end frequency of the Channel."""
        return self.frequency_range.high

    def contains(self, frequency: measures.Frequency | measures.FrequencyRange) -> bool:
        """Returns whether the Channel contains given frequency (range)."""
        return self.frequency_range.contains(frequency)

    def convert_to(self, newUnits: dict = measures.FrequencyUnits.GIGAHERTZ) -> measures.FrequencyRange:
        """Converts both endpoints of this Channel (frequency range) to the
        given units.

        This converts the endpoint frequency of the endpoints in-place, as well
        as returns a reference to the frequency range of this Channel.

        Args:
            newUnits: New units to convert the frequencies to. By default, this
                will convert to Gigahertz.
        """
        return self.frequency_range.convert_to(newUnits)

    def getCentreFrequency(self) -> measures.Frequency:
        """Returns the center frequency of the Channel."""
        return self.frequency_range.getCentreFrequency()

    def getOverlapWith(self, other: measures.FrequencyRange) -> measures.FrequencyRange:
        """Return a new frequency range that represents the region of overlap
        between this Channel (frequency range) and "other". If there is no
        overlap, None is returned.

        Args:
            other: Another frequency range that may overlap this Channel.

        Returns:
            FrequencyRange object representing the overlapping region of this
            range and other, or None if there is no overlap.
        """
        return self.frequency_range.getOverlapWith(other)

    def getGapBetween(self, other: measures.FrequencyRange) -> measures.FrequencyRange | None:
        """Returns a new frequency range that represents the region of frequency
        space between this Channel (frequency range) and ``other``. If the other
        range is coincident with, or overlaps, this Channel, None is returned.
        If the other range is None, None is returned.

        Args:
            other: Channel/frequency range for which to assess frequency gap
                with this Channel.

        Returns:
            The frequency gap between this range and ``other``."""
        return self.frequency_range.getGapBetween(other)

    def getWidth(self) -> measures.Frequency:
        """Returns the width of the Channel."""
        return self.frequency_range.getWidth()

    def overlaps(self, other: Channel) -> bool:
        """
        Returns whether this Channel overlaps with given ``other`` Channel.

        The Channel spans a frequency range that is a closed interval, that is,
        one that contains both of its endpoints.

        Args:
            other: Another Channel (frequency range) that may overlap this one.

        Returns:
            True if this Channel overlaps with ``other``. If ``other`` is not a
            Channel, the return value is False.
        """
        if isinstance(other, Channel):
            return self.frequency_range.overlaps(other.frequency_range)
        return False

    def set(self, frequency1: measures.Frequency, frequency2: measures.Frequency) -> None:
        """
        Set frequency range for this Channel based on given frequency endpoints.

        Args:
            frequency1: One endpoint of frequency range for this Channel.
            frequency2: Other endpoint of frequency range for this Channel.
        """
        self.frequency_range.set(frequency1, frequency2)


class SpectralWindow:
    """A logical representation of a spectral window (spw).

    Attributes:
        id: The numerical identifier of this spectral window within the
            SPECTRAL_WINDOW subtable of the MeasurementSet.
        band: Frequency band.
        bandwidth: The total bandwidth.
        baseband: The baseband.
        channels: Frequency information of each channel in spectral window,
            i.e., frequencies, channel width, effective bandwidth.
        freq_lo: A list of LO frequencies.
        intents: the observing intents that have been observed using this
            spectral window.
        mean_frequency: Mean frequency of spectral window.
        name: Spectral window name.
        receiver: Receiver type, e.g., 'TSB'.
        ref_frequency: The reference frequency.
        sideband: Side band.
        transitions: Spectral transitions recorded associated with spectral window.
        type: Spectral window type, e.g., 'TDM'.
        sdm_num_bin: Number of bins for online spectral averaging.
        correlation_bits: Number of bits used for correlation.
        median_receptor_angle: Median feed receptor angle.
        specline_window: Whether spw is intended for spectral line or continuum (VLA only).
        grouping_id: Grouping ID to uniquely identify this spw in different MOUS within the same GOUS (ALMA-only, introduced in Cycle 12).
    """
    __slots__ = ('id', 'band', 'bandwidth', 'type', 'intents', 'ref_frequency', 'name', 'baseband', 'sideband',
                 'receiver', 'freq_lo', 'mean_frequency', '_min_frequency', '_max_frequency', '_centre_frequency',
                 'channels', '_ref_frequency_frame', 'spectralspec', 'transitions', 'sdm_num_bin', 'correlation_bits',
                 'median_receptor_angle', 'specline_window', 'grouping_id')

    def __init__(
            self,
            spw_id: int,
            name: str,
            spw_type: str,
            bandwidth: float,
            ref_freq: dict,
            mean_freq: float,
            chan_freqs: numpy.ndarray,
            chan_widths: numpy.ndarray,
            chan_effective_bws: numpy.ndarray,
            sideband: int,
            baseband: int,
            receiver: str | None,
            freq_lo: list[float] | numpy.ndarray | None,
            band: str = 'Unknown',
            spectralspec: str | None = None,
            transitions: list[str] | None = None,
            sdm_num_bin: int | None = None,
            correlation_bits: str | None = None,
            median_receptor_angle: numpy.ndarray | None = None,
            specline_window: bool = False,
            grouping_id: str | None = None
            ):
        """
        Initialize SpectralWindow class.

        Args:
            spw_id: Spw ID.
            name: Spw name.
            spw_type: Spectral window type, e.g., 'TDM'.
            bandwidth: The total bandwidth.
            ref_freq: The reference frequency, as a CASA 'frequency' measure dictionary.
            mean_freq: Mean frequency of spectral window in Hz.
            chan_freqs: A list of frequency of each channel in spw in Hz.
            chan_widths: A list of channel width of each channel in spw in Hz.
            chan_effective_bws: A list of effective bandwidth of each channel in spw in Hz.
            sideband: Side band.
            baseband: The baseband.
            receiver: Receiver type, e.g., 'TSB'.
            freq_lo: A list of LO frequencies in Hz.
            band: Frequency band.
            spectralspec: SpectralSpec name.
            transitions: Spectral transitions recorded associated with spectral window.
            sdm_num_bin: Number of bins for online spectral averaging.
            correlation_bits: Number of bits used for correlation.
            median_receptor_angle: Median feed receptor angle.
            specline_window: Whether spw is intended for spectral line or continuum (VLA only).
            grouping_id: GOUS ID used to identify project group level (new in Cycle 12 ALMA data)  TODO improve description
        """
        if transitions is None:
            transitions = ['Unknown']

        self.id = spw_id
        self.bandwidth = measures.Frequency(bandwidth, measures.FrequencyUnits.HERTZ)

        ref_freq_hz = casa_tools.quanta.convertfreq(ref_freq['m0'], 'Hz')
        ref_freq_val = casa_tools.quanta.getvalue(ref_freq_hz)[0]
        self.ref_frequency = measures.Frequency(ref_freq_val, measures.FrequencyUnits.HERTZ)
        self._ref_frequency_frame = ref_freq['refer']

        self.mean_frequency = measures.Frequency(mean_freq, measures.FrequencyUnits.HERTZ)
        self.band = band
        self.type = spw_type
        self.spectralspec = spectralspec
        self.intents = set()

        # work around NumPy bug with empty strings
        # http://projects.scipy.org/numpy/ticket/1239
        self.name = str(name)
        self.sideband = str(sideband)
        self.baseband = str(baseband)
        self.receiver = receiver
        if freq_lo is not None:
            self.freq_lo = [measures.Frequency(freq, measures.FrequencyUnits.HERTZ) for freq in freq_lo]
        else:
            self.freq_lo = freq_lo

        chan_freqs = compress(chan_freqs)
        chan_widths = compress(chan_widths)
        chan_effective_bws = compress(chan_effective_bws)
        self.channels = ChannelList(chan_freqs, chan_widths, chan_effective_bws)

        self._min_frequency: measures.Frequency = min(self.channels, key=lambda r: r.low).low
        self._max_frequency: measures.Frequency = max(self.channels, key=lambda r: r.high).high
        self._centre_frequency: measures.Frequency = (self._min_frequency + self._max_frequency) / 2.0

        self.transitions = transitions
        self.sdm_num_bin = sdm_num_bin
        self.correlation_bits = correlation_bits
        self.median_receptor_angle = median_receptor_angle
        self.specline_window = specline_window
        self.grouping_id = grouping_id

    def __getstate__(self) -> tuple:
        """Define what to pickle as a class instance."""
        return (self.id, self.band, self.bandwidth, self.type, self.intents, self.ref_frequency, self.name,
                self.baseband, self.sideband, self.receiver, self.freq_lo, self.mean_frequency, self._min_frequency,
                self._max_frequency, self._centre_frequency, self.channels, self._ref_frequency_frame,
                self.spectralspec, self.transitions, self.sdm_num_bin, self.correlation_bits, self.median_receptor_angle,
                self.specline_window, self.grouping_id)

    def __setstate__(self, state: tuple) -> None:
        """Define how to unpickle a class instance."""
        (self.id, self.band, self.bandwidth, self.type, self.intents, self.ref_frequency, self.name, self.baseband,
         self.sideband, self.receiver, self.freq_lo, self.mean_frequency, self._min_frequency, self._max_frequency,
         self._centre_frequency, self.channels, self._ref_frequency_frame, self.spectralspec, self.transitions,
         self.sdm_num_bin, self.correlation_bits, self.median_receptor_angle, self.specline_window, self.grouping_id) = state

    def __repr__(self) -> str:
        chan_freqs = self.channels.chan_freqs
        if isinstance(chan_freqs, ArithmeticProgression):
            chan_freqs = numpy.array(list(chan_freqs))

        chan_widths = self.channels.chan_widths
        if isinstance(chan_widths, ArithmeticProgression):
            chan_widths = numpy.array(list(chan_widths))

        chan_effective_bws = self.channels.chan_effbws
        if isinstance(chan_effective_bws, ArithmeticProgression):
            chan_effective_bws = numpy.array(list(chan_effective_bws))

        return ('SpectralWindow({0!r}, {1!r}, {2!r}, {3!r}, {4!r}, {5!r}, {6}, {7}, {8}, {9!r}, {10!r}, {11!r}, '
                '{12!r}, {13}, {14}, {15!r}, {16}, {17})').format(
            self.id,
            self.name,
            self.type,
            float(self.bandwidth.to_units(measures.FrequencyUnits.HERTZ)),
            dict(m0={'unit': 'Hz',
                     'value': float(self.ref_frequency.to_units(measures.FrequencyUnits.HERTZ))},
                 refer=self._ref_frequency_frame,
                 type='frequency'),
            float(self.mean_frequency.to_units(measures.FrequencyUnits.HERTZ)),
            'numpy.array(%r)' % chan_freqs.tolist(),
            'numpy.array(%r)' % chan_widths.tolist(),
            'numpy.array(%r)' % chan_effective_bws.tolist(),
            self.sideband,
            self.baseband,
            self.band,
            self.transitions,
            self.sdm_num_bin,
            self.correlation_bits,
            self.median_receptor_angle,
            self.specline_window,
            self.grouping_id
        )

    @property
    def centre_frequency(self) -> measures.Frequency:
        """Return the center frequency of the SpectralWindow."""
        return self._centre_frequency

    def channel_range(self, minfreq: measures.Frequency, maxfreq: measures.Frequency) \
            -> tuple[int, int] | tuple[None, None]:
        """
        Return the channel range for given minimum/maximum frequency.

        Args:
            minfreq: Minimum frequency as measures.Frequency object.
            maxfreq: Maximum frequency as measures.Frequency object.

        Returns:
            2-Tuple of integers representing indices (min, max) of channel range
            end-points corresponding to given min/max frequency.
        """
        freqmin = minfreq
        freqmax = maxfreq

        # Check for the no overlap case.
        nchan = self.num_channels
        if freqmax < self.min_frequency:
            return None, None
        if freqmin > self.max_frequency:
            return None, None

        # Find the minimum channel
        chan_min = 0
        if self.channels[0].low < self.channels[nchan-1].low:
            for i in range(nchan):
                if self.channels[i].low > freqmin:
                    break
                chan_min = i
        else:
            for i in range(nchan):
                if self.channels[i].high < freqmax:
                    break
                chan_min = i

        # Find the maximum channel
        chan_max = nchan - 1
        if self.channels[0].low < self.channels[nchan-1].low:
            for i in range(nchan-1, -1, -1):
                if self.channels[i].high < freqmax:
                    break
                chan_max = i
        else:
            for i in range(nchan-1, -1, -1):
                if self.channels[i].low > freqmin:
                    break
                chan_max = i

        return chan_min, chan_max

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
    def num_channels(self) -> int:
        """Return the number of channels in the SpectralWindow."""
        return len(self.channels)

    def __str__(self) -> str:
        args = [str(x) for x in [self.id, self.centre_frequency, self.bandwidth, self.type]]
        return 'SpectralWindow({0})'.format(', '.join(args))


class SpectralWindowWithChannelSelection:
    """Wrapper for SpectralWindow that includes channel selection in the ID.

    This class wraps a SpectralWindow and modifies its ID property to include
    a channel selection string (e.g., '0:10~20;30~40').

    Attributes:
        id: Spectral window ID with appended channel selection string.
    """
    def __init__(self, subject: SpectralWindow, channels: Iterable[int]) -> None:
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
        """Returns the spectral window ID including channel selection."""
        channels = ':%s' % self._channels if self._channels else ''
        return f'{self._subject.id}{channels}'


def match_spw_basename(name1: str, name2: str) -> bool:
    """Determines if one SPW name is a suffix of the other, indicating equivalent SPW configurations.

    This function identifies spectral window settings that are functionally identical across different observation
    cycles, despite variations in naming conventions due to evolving metadata convention. The comparison is performed
    bidirectionally to accommodate naming changes where prefixes are usually added in newer cycles.

    ALMA naming convention change examples:

    Cycle 1-2 to Cycle 3-11 (partID addition for spectralspec identifiers):
        Before: `ALMA_RB_03#BB_1#SW-01#FULL_RES`
        After:  `X425992413#ALMA_RB_03#BB_2#SW-01#FULL_RES`

    Cycle 3-11 to Cycle 12 (groupID addition):
        Before: `X870829884#ALMA_RB_03#BB_1#SW-01#FULL_RES`
        After:  `X127/X45069401/X3370#X870829884#ALMA_RB_03#BB_1#SW-01#FULL_RES`

    Note: Cycle 0 data have fallback SPW names ("spw_i" where `i` is the SPW ID) in the `name` property of
    `SpectralWindow` domain objects since no specific names are assigned in the MS subtables.

    Args:
        name1: First spectral window name for comparison
        name2: Second spectral window name for comparison

    Returns:
        True if either name is a suffix of the other, False otherwise

    Raises:
        ValueError: If either name is shorter than 5 characters (insufficient for reliable matching)
    """
    # Validate minimum length requirement based on Pipeline fallback naming (spw_i)
    min_length = 5
    if len(name1) < min_length or len(name2) < min_length:
        msg = (
            f"SPW names too short for comparison: name1='{name1}', name2='{name2}'. "
            f"Minimum length is {min_length} characters."
        )
        LOG.error(msg)
        raise ValueError(msg)

    return name1.endswith(name2) or name2.endswith(name1)