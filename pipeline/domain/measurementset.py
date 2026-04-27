"""Pydantic-based MeasurementSet domain object (core port)."""

from __future__ import annotations

import collections
import contextlib
import datetime
import itertools
import operator
import os
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field as PydanticField, PrivateAttr, field_validator

from pipeline import infrastructure
from pipeline.domain import measures
from pipeline.domain import spectralwindow
from pipeline.infrastructure import casa_tools, tablereader, utils
from pipeline.infrastructure.launcher import current_task_name

if TYPE_CHECKING:
    from typing import Callable

    from numpy import floating

    from pipeline.domain import (Antenna, AntennaArray, DataDescription, DataType, Field,
                                 Polarization, Scan, SpectralWindow, State)
    from pipeline.infrastructure.utils.casa_types import EpochDict
    from pipeline.infrastructure.tablereader import RetrieveByIndexContainer

LOG = infrastructure.logging.get_logger(__name__)


class MeasurementSet(BaseModel):
    """MeasurementSet with core methods ported."""

    name: str = PydanticField(..., description='Path to the measurement set')
    session: str | None = PydanticField(default=None)

    exclude_num_chans: tuple[int, int] = PydanticField(default=(1, 4))
    filesize: measures.FileSize | None = PydanticField(default=None)

    acs_software_build_version: str | None = PydanticField(default=None)
    acs_software_version: str | None = PydanticField(default=None)
    antenna_array: AntennaArray | None = PydanticField(default=None)
    array_name: str = PydanticField(default='')
    correlator_name: str | None = PydanticField(default=None)
    data_column: dict = PydanticField(default_factory=dict)
    data_descriptions: RetrieveByIndexContainer = PydanticField(default_factory=RetrieveByIndexContainer)
    data_types_per_source_and_spw: dict = PydanticField(default_factory=dict)
    execblock_id: str = PydanticField(default='')
    fields: RetrieveByIndexContainer = PydanticField(default_factory=RetrieveByIndexContainer)
    observer: str = PydanticField(default='')
    observing_modes: list[str] = PydanticField(default_factory=list)
    polarizations: list[Polarization] = PydanticField(default_factory=list)
    project_id: str = PydanticField(default='')
    representative_target: tuple[str | None, dict | None, dict | None] = PydanticField(
        default=(None, None, None)
    )
    representative_window: str | None = PydanticField(default=None)
    scans: list[Scan] = PydanticField(default_factory=list)
    schedblock_id: str = PydanticField(default='')
    science_goals: dict = PydanticField(default_factory=dict)
    sources: RetrieveByIndexContainer = PydanticField(default_factory=RetrieveByIndexContainer)
    spectral_windows: RetrieveByIndexContainer = PydanticField(default_factory=RetrieveByIndexContainer)
    spectralspec_spwmap: dict = PydanticField(default_factory=dict)
    states: RetrieveByIndexContainer = PydanticField(default_factory=RetrieveByIndexContainer)

    derived_fluxes: dict[str, Any] | None = PydanticField(default=None)
    fluxscale_fluxes: dict[str, Any] | None = PydanticField(default=None)
    origin_ms: str | None = PydanticField(default=None)
    phase_calapps_for_check_sources: list[Any] = PydanticField(default_factory=list)
    phasecal_mapping: dict = PydanticField(default_factory=dict)
    phaseup_caltable_for_phase_rms: list[Any] = PydanticField(default_factory=list)
    reference_spwmap: list[int] | None = PydanticField(default=None)
    spwmaps: dict = PydanticField(default_factory=dict)
    reference_antenna_locked: bool = PydanticField(default=False)

    _reference_antenna: str | None = PrivateAttr(default=None)

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_default=True,
    )

    def __hash__(self) -> int:
        return hash((self.__class__, self.name))

    @field_validator('session', mode='before')
    @classmethod
    def _normalize_session(cls, value: str | None) -> str:
        return 'session_1' if value is None else value

    def model_post_init(self, __context: object) -> None:
        if self.origin_ms is None:
            self.origin_ms = self.name
        if self.filesize is None:
            self.filesize = self._calc_filesize()
        self._sync_data_column_with_datatypes()

    def _calc_filesize(self) -> measures.FileSize:
        """Calculate the disk usage of this measurement set."""
        if not os.path.exists(self.name):
            return measures.FileSize(0, measures.FileSizeUnits.BYTES)

        total_bytes = 0
        for dirpath, _, filenames in os.walk(self.name):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                total_bytes += os.path.getsize(filepath)

        return measures.FileSize(total_bytes, measures.FileSizeUnits.BYTES)

    def _sync_data_column_with_datatypes(self) -> None:
        """Ensure data_column dict is in sync with data_types_per_source_and_spw.

        This method reconstructs missing data_column entries based on datatypes
        found in data_types_per_source_and_spw. This is necessary when loading
        from serialized data where only one dict may have been populated.
        """
        if not self.data_types_per_source_and_spw:
            return

        # Collect all unique datatypes from data_types_per_source_and_spw
        all_datatypes = set()
        for datatypes_list in self.data_types_per_source_and_spw.values():
            all_datatypes.update(datatypes_list)

        # For each datatype, ensure it has an entry in data_column
        for dtype in all_datatypes:
            if dtype not in self.data_column:
                # Determine the appropriate column name for this datatype
                # RAW uses DATA column, everything else uses CORRECTED
                from pipeline.domain.datatype import DataType
                if dtype == DataType.RAW:
                    column = 'data'
                else:
                    column = 'corrected'
                self.data_column[dtype] = column
                LOG.debug('MS %s: Auto-populated data_column[%s] = %s', self.name, dtype, column)

    def __str__(self) -> str:
        return 'MeasurementSet({0})'.format(self.name)

    @property
    def intents(self) -> set[str]:
        """Return unique intents in the measurement set."""
        intents: set[str] = set()
        for field in self.fields:
            intents.update(field.intents)
        return intents

    @property
    def antennas(self) -> list[Antenna]:
        """Return list of Antenna objects for all antennas in the measurement set."""
        if self.antenna_array is None:
            return []
        return list(self.antenna_array.antennas)

    @property
    def basename(self) -> str:
        """Return base path to the measurement set."""
        return os.path.basename(self.name)

    @property
    def is_band_to_band(self) -> bool:
        """Return whether this MS is for band-to-band interferometry."""
        return 'BandToBand Interferometry' in self.observing_modes or self.get_diffgain_mode() == 'B2B'

    def get_antenna(self, search_term: str = '') -> list[Antenna]:
        """Return Antenna(s) for given antenna selection in CASA format."""
        if search_term == '':
            return self.antennas

        return [
            antenna
            for antenna in self.antennas
            if antenna.id in utils.ant_arg_to_id(self.name, search_term, self.antennas)
        ]

    def get_state(self, state_id: int | None = None) -> State | None:
        """Return State in MeasurementSet matching the given identifier."""
        match = [state for state in self.states if state.id == state_id]
        return match[0] if match else None

    def get_scans(
        self,
        scan_id: int | Sequence[int] | None = None,
        scan_intent: str | Sequence[str] | None = None,
        field: int | str | None = None,
        spw: int | str | Sequence[int] | Sequence[str] | None = None,
    ) -> list[Scan]:
        """Return scans matching the given criteria."""
        pool = self.scans

        if scan_id is not None:
            if not isinstance(scan_id, Sequence) or isinstance(scan_id, str):
                scan_id = (scan_id,)
            pool = [scan for scan in pool if scan.id in scan_id]

        if scan_intent is not None:
            if isinstance(scan_intent, str):
                if scan_intent in ('', '*'):
                    scan_intent = ','.join(self.intents)
                scan_intent = scan_intent.split(',')
            scan_intent = set(scan_intent)
            pool = [scan for scan in pool if not scan.intents.isdisjoint(scan_intent)]

        if field is not None:
            fields_with_name = frozenset(self.get_fields(task_arg=field))
            pool = [scan for scan in pool if not fields_with_name.isdisjoint(scan.fields)]

        if spw is not None:
            # Handle string representations first, before wrapping logic
            if isinstance(spw, str):
                if spw in ('', '*'):
                    spw = ','.join(str(item.id) for item in self.spectral_windows)
                if '~' in spw:
                    spw = utils.range_to_list(spw)
                else:
                    spw = spw.split(',')
            # Ensure spw is a sequence (wrap single non-string values)
            elif not isinstance(spw, Sequence):
                spw = (spw,)
            spw = {int(i) for i in spw}
            pool = {
                scan
                for scan in pool
                for scan_spw in scan.spws
                if scan_spw.id in spw
            }
            pool = sorted(pool, key=lambda scan: scan.id)

        return pool

    def get_data_description(self, spw: int | None = None, id: int | None = None) -> DataDescription | None:
        """Return the DataDescription matching the given criteria."""
        match = None
        if spw is not None:
            if hasattr(spw, 'id'):
                match = [dd for dd in self.data_descriptions if dd.spw is spw]
            elif isinstance(spw, int):
                match = [dd for dd in self.data_descriptions if dd.spw.id == spw]
        if id is not None:
            match = [dd for dd in self.data_descriptions if dd.id == id]

        return match[0] if match else None

    def get_representative_source_spw(self, source_name: str | None = None, source_spwid: int | None = None) -> tuple[str | None, int | None]:
        """Get the representative target source object and spectral window.

        * Use user name if ``source_name`` is supplied by user and it has TARGET intent.
        * Otherwise, use the source defined in the ASDM SBSummary table if it has TARGET intent.
        * Otherwise, use the first source in the source list with TARGET intent.

        Args:
            source_name: A string with the source name, or None for an automatic selection.
            source_spwid: An int with the spw id, or None for an automatic selection.

        Returns:
            A tuple with representative source name and spw id;
            if such a source cannot be identified, return (None, None),
            and if a spw cannot be determined, return (name, None).
        """
        from pipeline.infrastructure.launcher import current_task_name

        qa = casa_tools.quanta
        cme = casa_tools.measures

        if current_task_name.get() == 'hifa_imageprecheck':
            log_level = infrastructure.logging.WARNING
        else:
            log_level = infrastructure.logging.INFO

        if source_name:
            target_sources = [
                source for source in self.sources if source.name == source_name and 'TARGET' in source.intents
            ]
            if len(target_sources) > 0:
                LOG.info('Selecting user defined representative target source %s for data set %s',
                         source_name, self.basename)
                target_source = target_sources[0]
            else:
                LOG.warning('User defined representative target source %s not found in data set %s',
                            source_name, self.basename)
                target_source = None
        elif self.representative_target[0]:
            source_name = self.representative_target[0]
            target_sources = [
                source for source in self.sources if source.name == source_name and 'TARGET' in source.intents
            ]
            if len(target_sources) > 0:
                LOG.info('Selecting representative target source %s for data set %s',
                         self.representative_target[0], self.basename)
                target_source = target_sources[0]
            else:
                LOG.warning('Representative target source %s not found in data set %s',
                            self.representative_target[0], self.basename)
                target_sources = [source for source in self.sources if 'TARGET' in source.intents]
                if len(target_sources) > 0:
                    target_source = target_sources[0]
                    LOG.info('Falling back to first target source (%s) for data set %s',
                             target_source.name, self.basename)
                else:
                    LOG.warning('No target sources observed for data set %s', self.basename)
                    target_source = None
        else:
            target_sources = [source for source in self.sources if 'TARGET' in source.intents]
            if len(target_sources) > 0:
                target_source = target_sources[0]
                LOG.info('Undefined representative target source, defaulting to first target source (%s) for data set %s',
                         target_source.name, self.basename)
            else:
                LOG.warning('No target sources observed for data set %s', self.basename)
                target_source = None

        if target_source is None:
            return None, None

        target_source_name = target_source.name

        if source_spwid:
            found = False
            for field in target_source.fields:
                valid_spwids = [spw.id for spw in list(field.valid_spws)]
                if source_spwid in valid_spwids:
                    found = True
                    break
            if found:
                LOG.info('Selecting user defined representative spw %s for data set %s',
                         source_spwid, self.basename)
                return target_source_name, source_spwid
            else:
                LOG.warning('No target source data for representative spw %s in data set %s',
                            source_spwid, self.basename)
                return target_source_name, None

        target_spwid = None
        if self.representative_window is not None:
            try:
                target_spwid = [s.id for s in self.get_spectral_windows() if s.name == self.representative_window][0]
            except IndexError:
                LOG.log(log_level, 'Could not translate spw name %s to ID. Trying frequency matching heuristics.',
                        self.representative_window)

        if target_spwid is not None:
            return target_source_name, target_spwid

        if not self.representative_target[2]:
            if self.antenna_array and self.antenna_array.name not in ('VLA', 'EVLA'):
                LOG.warning('Undefined representative bandwidth for data set %s', self.basename)
            return target_source_name, None

        target_bw = cme.frequency(
            'TOPO',
            qa.quantity(qa.getvalue(self.representative_target[2]), qa.getunit(self.representative_target[2])),
        )

        if not self.representative_target[1]:
            LOG.warning('Undefined representative frequency for data set %s', self.basename)
            return target_source_name, None

        target_frequency = cme.frequency(
            'BARY',
            qa.quantity(qa.getvalue(self.representative_target[1]), qa.getunit(self.representative_target[1])),
        )

        cme.doframe(cme.observatory(self.antenna_array.name if self.antenna_array else 'ALMA'))
        cme.doframe(target_source.direction)
        target_scans = [
            scan for scan in self.get_scans(scan_intent='TARGET')
            if target_source.id in [field.source_id for field in scan.fields]
        ]
        if len(target_scans) > 0:
            cme.doframe(target_scans[0].start_time)
            target_frequency_topo = cme.measure(target_frequency, 'TOPO')
        else:
            LOG.error('Unable to convert representative frequency to TOPO for data set %s', self.basename)
            target_frequency_topo = None
        cme.done()

        if not target_frequency_topo:
            return target_source_name, None

        science_spw_ids = [spw.id for spw in self.get_spectral_windows()]
        target_spws = {
            spw for field in target_source.fields for spw in field.valid_spws if spw.id in science_spw_ids
        }

        target_spws_bw = [
            spw for spw in target_spws
            if spw.channels[0].getWidth().to_units(measures.FrequencyUnits.HERTZ) <= 1.01 * target_bw['m0']['value']
        ]

        if len(target_spws_bw) <= 0:
            LOG.warning('No target spws have channel width <= representative bandwidth in data set %s', self.basename)

            target_spws_freq = [
                spw for spw in target_spws
                if spw.min_frequency.value <= target_frequency_topo['m0']['value'] <= spw.max_frequency.value
            ]

            if len(target_spws_freq) <= 0:
                LOG.warning('No target spws overlap the representative frequency in data set %s', self.basename)

                max_freqdiff = float('inf')
                for spw in target_spws:
                    freqdiff = abs(float(spw.centre_frequency.value) - target_frequency_topo['m0']['value'])
                    if freqdiff < max_freqdiff:
                        target_spwid = spw.id
                        max_freqdiff = freqdiff
                LOG.info('Selecting spw %s which is closest to the representative frequency in data set %s',
                         target_spwid, self.basename)
            else:
                min_chanwidth = None
                for spw in target_spws_freq:
                    chanwidth = spw.channels[0].getWidth().to_units(measures.FrequencyUnits.HERTZ)
                    if not min_chanwidth or chanwidth < min_chanwidth:
                        target_spwid = spw.id
                        min_chanwidth = chanwidth
                LOG.info('Selecting the narrowest chanwidth spw id %s which overlaps the representative frequency in data set %s',
                         target_spwid, self.basename)

            return target_source_name, target_spwid

        target_spws_freq = [
            spw for spw in target_spws_bw
            if spw.min_frequency.value <= target_frequency_topo['m0']['value'] <= spw.max_frequency.value
        ]
        if len(target_spws_freq) <= 0:
            LOG.log(
                log_level,
                'No target spws with channel spacing <= representative bandwith overlap the representative frequency in data set %s',
                self.basename,
            )
            max_chanwidth = None
            for spw in target_spws_bw:
                chanwidth = spw.channels[0].getWidth().to_units(measures.FrequencyUnits.HERTZ)
                if (max_chanwidth is None) or (chanwidth > max_chanwidth):
                    target_spwid = spw.id
                    max_chanwidth = chanwidth
            LOG.info('Selecting widest channel width spw id %s with channel width <= representative bandwidth in data set %s',
                     str(target_spwid), self.basename)

            return target_source_name, target_spwid

        bestspw = None
        for spw in sorted(target_spws_freq, key=lambda x: x.id):
            if not bestspw:
                bestspw = spw
            elif spw.bandwidth.value > bestspw.bandwidth.value:
                bestspw = spw
        target_spwid = bestspw.id

        return target_source_name, target_spwid

    def get_fields(
        self,
        task_arg: int | str | None = None,
        field_id: int | Sequence[int] | None = None,
        name: str | Sequence[str] | None = None,
        intent: str | Sequence[str] | None = None,
    ) -> list[Field]:
        """Return fields matching the given criteria."""
        pool = self.fields

        if task_arg not in (None, ''):
            field_ids = utils.field_arg_to_id(self.name, task_arg, self.fields)
            pool = [field for field in pool if field.id in field_ids]

        if field_id is not None:
            if not isinstance(field_id, Sequence) or isinstance(field_id, str):
                field_id = (field_id,)
            pool = [field for field in pool if field.id in field_id]

        if name is not None:
            if isinstance(name, str):
                name = name.split(',')
            name = set(name)
            pool = [field for field in pool if field.name in name]

        if intent is not None:
            if isinstance(intent, str):
                if intent in ('', '*'):
                    intent = ','.join(self.intents)
                intent = intent.split(',')
            intent = set(intent)
            pool = [field for field in pool if not field.intents.isdisjoint(intent)]

        return pool

    def get_spectral_window(self, spw_id: int | str) -> SpectralWindow | None:
        """Return the SpectralWindow object matching the given identifier."""
        spw_id = int(spw_id)
        match = [spw for spw in self.spectral_windows if spw.id == spw_id]
        if match:
            return match[0]
        raise KeyError(
            'No spectral window with ID \'{0}\' found in {1}'.format(spw_id, self.basename)
        )

    def get_spectral_windows(
        self,
        task_arg: int | str = '',
        with_channels: bool = False,
        num_channels: list[int] | None = None,
        science_windows_only: bool = True,
        spectralspecs: list[str] | None = None,
        intent: str | None = None,
    ) -> list[SpectralWindow]:
        """Return spectral windows matching given criteria."""
        spws = self.get_all_spectral_windows(task_arg, with_channels)

        if num_channels:
            spws = [window for window in spws if window.num_channels in num_channels]

        if spectralspecs is not None:
            spws = [window for window in spws if window.spectralspec in spectralspecs]

        if intent is not None:
            spws = [window for window in spws if not set(intent.split(',')).isdisjoint(window.intents)]

        if not science_windows_only:
            return spws

        if self.antenna_array and self.antenna_array.name == 'ALMA':
            science_intents = {
                'TARGET',
                'PHASE',
                'BANDPASS',
                'AMPLITUDE',
                'POLARIZATION',
                'POLANGLE',
                'POLLEAKAGE',
                'CHECK',
                'DIFFGAINREF',
                'DIFFGAINSRC',
            }
            return [
                window
                for window in spws
                if window.num_channels not in self.exclude_num_chans
                and not science_intents.isdisjoint(window.intents)
            ]

        if self.antenna_array and self.antenna_array.name in ('VLA', 'EVLA'):
            science_intents = {
                'TARGET',
                'PHASE',
                'BANDPASS',
                'AMPLITUDE',
                'POLARIZATION',
                'POLANGLE',
                'POLLEAKAGE',
                'CHECK',
            }
            return [
                window
                for window in spws
                if window.num_channels not in self.exclude_num_chans
                and not science_intents.isdisjoint(window.intents)
                and 'POINTING' not in window.intents
            ]

        if self.antenna_array and self.antenna_array.name == 'NRO':
            science_intents = {'TARGET'}
            return [window for window in spws if not science_intents.isdisjoint(window.intents)]

        return spws

    def get_spectral_specs(self) -> list[str]:
        """Return list of all spectral specs used in the MS."""
        return list(self.spectralspec_spwmap.keys())

    def get_all_spectral_windows(
        self,
        task_arg: int | str = '',
        with_channels: bool = False,
    ) -> list[SpectralWindow]:
        """Return spectral windows corresponding to the given CASA-style spw argument."""
        if task_arg in (None, ''):
            task_arg = '*'

        selected = collections.defaultdict(set)
        for spw_id, start, end, step in utils.spw_arg_to_id(self.name, task_arg, self.spectral_windows):
            selected[spw_id].update(set(range(start, end + 1, step)))

        if not with_channels:
            return [spw for spw in self.spectral_windows if spw.id in selected]

        spws: list[SpectralWindow] = []
        for spw_id, channels in selected.items():
            spw_obj = self.get_spectral_window(spw_id)
            proxy = spectralwindow.SpectralWindowWithChannelSelection(spw_obj, channels)
            spws.append(proxy)
        return spws

    def get_diffgain_mode(self) -> str | None:
        """Determine if this MS uses a diffgain observing mode."""
        if 'DIFFGAINREF' in self.intents or 'DIFFGAINSRC' in self.intents:
            dg_refspws = self.get_spectral_windows(intent='DIFFGAINREF')
            if not dg_refspws:
                raise ValueError(
                    f'DIFFGAINREF intent missing in calibration sources for dataset {self.basename}'
                )
            dg_srcspws = self.get_spectral_windows(intent='DIFFGAINSRC')
            if not dg_srcspws:
                raise ValueError(
                    f'DIFFGAINSRC intent missing in science sources for dataset {self.basename}'
                )

            refcent = dg_refspws[0].centre_frequency.value
            scicent = dg_srcspws[0].centre_frequency.value
            refwidth = dg_refspws[0].bandwidth.value
            sciwidth = dg_srcspws[0].bandwidth.value

            if scicent / refcent > 1.661:
                return 'B2B'
            if refwidth / sciwidth > 1.5:
                return 'BWSW'

            raise ValueError(
                f'DIFFGAIN intent with an unsupported spectral setup for dataset {self.basename}'
            )

        return None

    def get_original_intent(self, intent: str) -> set[str]:
        """Get original obs_modes corresponding to the given pipeline intent(s)."""
        obs_modes = [state.get_obs_mode_for_intent(intent) for state in self.states]
        return set(itertools.chain(*obs_modes))

    def get_alma_cycle_number(self) -> int | None:
        """Get the ALMA cycle number from the observation start time."""
        cycle_numbers = {
            0: ['2011-09-30', '2013-01-20'],
            1: ['2013-01-21', '2014-06-02'],
            2: ['2014-06-03', '2015-09-30'],
            3: ['2015-10-01', '2016-09-30'],
            4: ['2016-10-01', '2017-09-30'],
            5: ['2017-10-01', '2018-09-30'],
            6: ['2018-10-01', '2019-09-30'],
            7: ['2019-10-01', '2021-09-30'],
            8: ['2021-10-01', '2022-09-30'],
            9: ['2022-10-01', '2023-09-30'],
            10: ['2023-10-01', '2024-09-30'],
            11: ['2024-10-01', '2025-09-30'],
            12: ['2025-10-01', '2026-09-30'],
        }
        if not self.antenna_array or self.antenna_array.name != 'ALMA':
            return None
        start_time = utils.get_epoch_as_datetime(self.start_time)
        for cycle, (start_str, end_str) in cycle_numbers.items():
            start = datetime.datetime.strptime(start_str, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)
            end = datetime.datetime.strptime(end_str, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)
            if start <= start_time <= end:
                return cycle
        return None

    @property
    def start_time(self) -> EpochDict | None:
        """Return start time for this measurement set as CASA 'epoch' measure dictionary."""
        if not self.scans:
            return None
        earliest, _ = min(
            [(scan, utils.get_epoch_as_datetime(scan.start_time)) for scan in self.scans],
            key=operator.itemgetter(1),
        )
        return earliest.start_time

    @property
    def end_time(self) -> EpochDict | None:
        """Return end time for this measurement set as CASA 'epoch' measure dictionary."""
        if not self.scans:
            return None
        latest, _ = max(
            [(scan, utils.get_epoch_as_datetime(scan.end_time)) for scan in self.scans],
            key=operator.itemgetter(1),
        )
        return latest.end_time

    def get_vla_corrstring(self) -> str:
        """Get correlation string for VLA."""
        corrstring_list = (
            self.polarizations[self.data_descriptions[0].pol_id].corr_type_string
            if len(self.polarizations) and len(self.data_descriptions) > 0
            else []
        )
        removal_list = ['RL', 'LR', 'XY', 'YX']
        corrstring_list = sorted(set(corrstring_list).difference(set(removal_list)))
        return ','.join(corrstring_list)

    def get_vla_corrlist_from_spw(self, spw: str | None = None) -> list[str]:
        """Get all VLA correlation labels as a list of string from selected spw(s)."""
        corrs: set[str] = set()
        for dd in self.data_descriptions:
            if spw in ('', '*', None) or (isinstance(spw, str) and str(dd.spw.id) in spw.split(',')):
                corrs = corrs.union(self.polarizations[dd.pol_id].corr_type_string)
        return sorted(corrs)

    def get_alma_corrstring(self) -> str:
        """Get correlation string for ALMA for the science spectral windows."""
        sci_spwlist = self.get_spectral_windows(science_windows_only=True)
        sci_spwids = [spw.id for spw in sci_spwlist]
        datadescs = [dd for dd in self.data_descriptions if dd.spw.id in sci_spwids]
        numpols = len(datadescs[0].polarizations)
        return 'XX' if numpols == 1 else 'XX,YY'

    def get_vla_spw2band(self) -> dict[int, str]:
        """Find spectral windows id-to-band mapping for VLA.

        Creat spw id-to-band mapping from spw names or derives it from reference frequency
        when name parsing fails. Handles special cases for KU and KA band naming conventions.

        Returns:
            Dictionary mapping spectral window IDs to single-letter band codes (e.g., '4', 'P', 'L',
            'S', 'C', 'X', 'U', 'K', 'A', 'Q').
        """
        spw2band: dict[int, str] = {}

        for spw in self.spectral_windows:

            try:
                # Extract band from 6th character of SPW name
                spw_name_chars = list(spw.name)
                band_char = spw_name_chars[5]

                if band_char in '4PLSCXUKAQ':
                    spw2band[spw.id] = band_char

                # Handle special multi-character band names
                if band_char == 'K' and len(spw_name_chars) > 6:
                    if spw_name_chars[6] == 'U':  # KU band
                        spw2band[spw.id] = 'U'
                    elif spw_name_chars[6] == 'A':  # KA band
                        spw2band[spw.id] = 'A'
            except IndexError:
                # SPW name too short or malformed
                pass

            # Fallback to frequency-based band determination
            if spw.id not in spw2band:
                evla_band = tablereader.find_EVLA_band(float(spw.ref_frequency.value))
                LOG.info(
                    "Unable to extract band name from SPW ID %s (name: %s); "
                    "derived band name %s from reference frequency",
                    spw.id, spw.name, evla_band)
                spw2band[spw.id] = evla_band

        return spw2band

    def get_vla_field_spws(self, spwlist=[]):
        """Find field spws for VLA

        Args:
            spwlist (List, optional): list of string spws   ['1', '2', '3']

        Returns:
            field_spws: List of dictionaries
        """
        # Map field IDs to spws
        field_spws = []

        spwlistint = [int(spw) for spw in spwlist]

        with casa_tools.MSMDReader(self.name) as msmd:
            spwsforfieldsall = msmd.spwsforfields()

            if spwlist != []:
                spwsforfields = {}
                for field, spws in spwsforfieldsall.items():
                    spwsforfields[field] = [spw for spw in spws if spw in spwlistint]
            else:
                spwsforfields = spwsforfieldsall

            spwfieldkeys = sorted([int(i) for i in spwsforfields])
            spwfieldkeys = [str(i) for i in spwfieldkeys]

            for key in spwfieldkeys:
                field_spws.append(spwsforfields[key])

        return field_spws

    def get_vla_numchan(self):
        """Get number of channels for VLA.

        Returns:
            channels:  NUM_CHAN column from spectral window table
        """
        vis = self.name

        with casa_tools.TableReader(vis+'/SPECTRAL_WINDOW') as table:
            channels = table.getcol('NUM_CHAN')

        return channels

    def get_vla_tst_bpass_spw(self, spwlist=[]):
        """Get VLA test bandpass or delay spws.

        This function replaced functionality for get_vla_tst_delay_spw - PIPE-1325

        Args:
            spwlist (List, optional): list of string spws   ['1', '2', '3']

        Returns:
            tst_bpass_spws: CASA argument format of spws:channels    '0:10~80, 1:15~60, 2:30~70'
        """
        tst_delay_spw = ''

        channels = self.get_vla_numchan()

        ispwlist = [int(spw) for spw in spwlist]
        for ispw in ispwlist:
            endch1 = int(channels[ispw]/3.0)
            endch2 = int(2.0*channels[ispw]/3.0)+1
            if ispw < max(ispwlist):
                tst_delay_spw = tst_delay_spw+str(ispw)+':'+str(endch1)+'~'+str(endch2)+','
            else:
                tst_delay_spw = tst_delay_spw+str(ispw)+':'+str(endch1)+'~'+str(endch2)

        tst_bpass_spw = tst_delay_spw

        return tst_bpass_spw

    def get_vla_critfrac(self) -> float:
        """Identify bands/basebands/spws.

        Returns:
            critical fraction
        """
        vis = self.name

        with casa_tools.TableReader(vis+'/SPECTRAL_WINDOW') as table:
            spw_names = table.getcol('NAME')

        # If the dataset is too old to have the bandname in it, assume that
        # either there are 8 spws per baseband (and allow for one or two for
        # pointing), or that this is a dataset with one spw per baseband

        if len(spw_names) >= 8:
            critfrac = 0.9/int(len(spw_names)/8.0)
        else:
            critfrac = 0.9/float(len(spw_names))

        if '#' in spw_names[0]:
            #
            # i assume that if any of the spw_names have '#', they all do...
            #
            bands_basebands_subbands = []
            for spw_name in spw_names:
                receiver_name, baseband, subband = spw_name.split('#')
                receiver_band = (receiver_name.split('_'))[1]
                bands_basebands_subbands.append([receiver_band, baseband, int(subband)])
            spws_info = [[bands_basebands_subbands[0][0], bands_basebands_subbands[0][1], [], []]]
            bands = [bands_basebands_subbands[0][0]]
            for ii in range(len(bands_basebands_subbands)):
                band, baseband, subband = bands_basebands_subbands[ii]
                found = -1
                for jj in range(len(spws_info)):
                    oband, obaseband, osubband, ospw_list = spws_info[jj]
                    if band == oband and baseband == obaseband:
                        osubband.append(subband)
                        ospw_list.append(ii)
                        found = jj
                        break
                if found >= 0:
                    spws_info[found] = [oband, obaseband, osubband, ospw_list]
                else:
                    spws_info.append([band, baseband, [subband], [ii]])
                    bands.append(band)

            # Critical fraction of flagged solutions in delay cal to avoid an
            # entire baseband being flagged on all antennas
            critfrac = 0.9/float(len(spws_info))
        elif ':' in spw_names[0]:
            print("old spw names with :")
        else:
            print("unknown spw names")

        return critfrac

    def get_vla_baseband_spws(
            self,
            science_windows_only: bool = True,
            return_select_list: bool = True,
            warning: bool = True,
            ) -> dict | list[list[int]]:
        """Get the SPW information from individual VLA band/baseband.

        Args:
            science_windows_only: Whether to include only science spectral windows.
            return_select_list: Whether to return SPW list of each baseband instead of full band/subband info.
            warning: Whether to log warnings for parsing errors.

        Returns:
            If return_select_list is False:
                Dictionary with SPW info organized as baseband_spws[band][baseband], where each
                entry contains a list of spw info as {spwid, (min_freq, max_freq, mean_freq, chan_width)}.

            If return_select_list is True:
                List of SPW ID lists for each band.baseband, e.g., [[0,1,2,3], [4,5,6,7]].
        """
        baseband_spws = collections.defaultdict(lambda: collections.defaultdict(list))
        spw2band = self.get_vla_spw2band()

        for spw in self.get_spectral_windows(science_windows_only=science_windows_only):
            try:
                band = spw2band.get(spw.id, 'unknown')
                # PIPE-2634: historically, the codes calling `ms.get_vla_baseband_spws` was imeplemented to
                # use two-letter convetions for KU and KA bands, e.g. 'KU' and 'KA' instead of 'U' and 'A'.
                if band in ('U', 'A'):
                    band = 'K' + band
                if '#' in spw.name:
                    baseband = spw.name.split('#')[1]
                else:
                    # older VLA data might have this spw naming pattern:
                    # spwid - name
                    #   0   - Subband:7
                    #   1   - Subband:5
                    #     ..
                    #   8   - Subband:7
                    # Here as a fallback, we use the full spw name as baseband; likely band name is generated from
                    # the frequency-base heuristics in ms.spw2band
                    baseband = spw.name
                min_freq = spw.min_frequency
                max_freq = spw.max_frequency
                mean_freq = spw.mean_frequency
                chan_width = spw.channels[0].getWidth()
                baseband_spws[band][baseband].append({spw.id: (min_freq, max_freq, mean_freq, chan_width)})
            except Exception as ex:
                if warning:
                    LOG.warning('Exception: Baseband name cannot be parsed. %s', ex)
                else:
                    pass

        if return_select_list:
            baseband_spws_list = []
            for band in baseband_spws.values():
                for baseband in band.values():
                    baseband_spws_list.append([[*spw_info][0] for spw_info in baseband])
            return baseband_spws_list
        else:
            return baseband_spws

    def get_integration_time_stats(
            self,
            intent: str | None = None,
            spw: str | None = None,
            science_windows_only: bool = False,
            stat_type: str = "max",
            band: str | None = None,
            ) -> float:
        """Get the given statistcs of integration time.

        Args:
            intent: The intent of the data of interest.
            spw: spw string list - '1,7,11,18'.
            science_windows_only: Use integration time of science spws only to compute the given statistics.
            stat_type: Type of the statistics.
            band: return maximum integration time for the given VLA band.
                Ignored for non-VLA datasets; has no effect in that case. Default is None.default None
        Returns
            Computed statistics value.
        """
        LOG.debug('inefficiency - MSFlagger reading file to get median integration '
                  'time for science targets')

        # get the field IDs and state IDs for fields in the measurement set,
        # filtering by intent if necessary
        if intent:
            field_ids = [field.id for field in self.fields
                         if intent in field.intents]
            state_ids = [state.id for state in self.states
                         if intent in state.intents]
        else:
            field_ids = [field.id for field in self.fields]
            state_ids = [state.id for state in self.states]

        if spw is None:
            spws = self.spectral_windows
        else:

            try:
                # Put csv string of spws into a list
                spw_string_list = spw.split(',')

                # Get all spw objects
                all_spws = self.spectral_windows

                # Filter out the science spw objects
                spws = [ispw for ispw in all_spws if str(ispw.id) in spw_string_list]
            except:
                LOG.error("Incorrect spw string format.")
        if band is not None:
            if self.antenna_array.name not in ('VLA', 'EVLA'):
                LOG.warning(
                    'The band parameter is only applicable to VLA data. For non-VLA datasets, '
                    'it has no effect on the maximum integration time calculation.'
                )
            spw2band = self.get_vla_spw2band()
            spws = [spw_obj for spw_obj in spws if spw2band[spw_obj.id].lower() == band.lower()]
            science_spw_dd_ids = [self.get_data_description(spw).id for spw in spws]
        if science_windows_only:
            # now get the science spws, those used for scientific intent
            science_spws = [
                ispw for ispw in spws
                if ispw.num_channels not in self.exclude_num_chans
                and not ispw.intents.isdisjoint(['BANDPASS', 'AMPLITUDE', 'PHASE',
                                                'TARGET'])]
            LOG.debug('science spws are: %s' % [ispw.id for ispw in science_spws])
            # and the science fields/states
            science_field_ids = [
                fid for fid in field_ids
                if not set(self.fields[fid].intents).isdisjoint(['BANDPASS', 'AMPLITUDE',
                                                                 'PHASE', 'TARGET'])]
            science_state_ids = [
                sid for sid in state_ids
                if not set(self.states[sid].intents).isdisjoint(['BANDPASS', 'AMPLITUDE',
                                                                 'PHASE', 'TARGET'])]

            science_spw_dd_ids = [self.get_data_description(spw).id for spw in science_spws]

        # VLA datasets have an empty STATE table; in the main table such rows
        # have a state ID of -1.
        if not state_ids:
            state_ids = [-1]

        state_str = utils.list_to_str(science_state_ids if science_windows_only else state_ids)
        field_str = utils.list_to_str(science_field_ids if science_windows_only else field_ids)
        spw_str = utils.list_to_str(science_spw_dd_ids) if science_windows_only or band is not None else ""

        taql = f"(STATE_ID IN {state_str} AND FIELD_ID IN {field_str}" + \
            (f" AND DATA_DESC_ID IN {spw_str}" if spw_str else "") + ")"

        with casa_tools.TableReader(self.name) as table:
            with contextlib.closing(table.query(taql)) as subtable:
                integration = subtable.getcol('INTERVAL')
            # PIPE-2370: convert np.float64 to a native float for better weblog presentations.
            if stat_type == "max":
                return float(np.max(integration))
            elif stat_type == "median":
                return float(np.median(integration))

    def get_times_on_source_per_field_id(self, field: str, intent: str) -> dict[int, floating]:
        """
        Return on-source time for given field ID(s) and intent(s).

        Args:
            field: Field name(s) to return times for.
            intent: Intent(s) to filter for.

        Returns:
            Dictionary of on-source times for selected field ID(s) and intent(s).
        """
        field_ids = [field.id for field in self.fields if intent in field.intents]
        state_ids = [state.id for state in self.states if intent in state.intents]
        scan_ids = [s.id for s in self.get_scans(field=field, scan_intent=intent)]
        # Need to select just one cross correlation row between antenna 1 and 2
        ant1 = self.antennas[0].id
        ant2 = self.antennas[1].id
        # Just a single spw since all spws are observed together
        first_science_spw_dd_id = [self.get_data_description(spw_id).id for spw_id in [s.id for s in self.get_spectral_windows()]][0]
        times_on_source_per_field_id = dict()
        for field_id in field_ids:
            with casa_tools.TableReader(self.name) as table:
                state_str = utils.list_to_str(state_ids)
                scan_str = utils.list_to_str(scan_ids)
                taql = (
                    f'(STATE_ID IN {state_str} AND FIELD_ID IN [{field_id}] '
                    f'AND DATA_DESC_ID IN [{first_science_spw_dd_id}] '
                    f'AND SCAN_NUMBER IN {scan_str} AND ANTENNA1={ant1} AND ANTENNA2={ant2})'
                )
                with contextlib.closing(table.query(taql)) as subtable:
                    integration = subtable.getcol('INTERVAL')
                times_on_source_per_field_id[field_id] = np.sum(integration)
        return times_on_source_per_field_id

    @property
    def reference_antenna(self) -> str | None:
        """Get the reference antenna list for this MS."""
        return self._reference_antenna

    @reference_antenna.setter
    def reference_antenna(self, value: str) -> None:
        """Set the reference antenna list for this MS."""
        if self.reference_antenna_locked:
            raise AttributeError(f'Refant list for {self.basename} is locked')
        self._reference_antenna = value

    def update_reference_antennas(
        self,
        ants_to_demote: set[str] | None = None,
        ants_to_remove: set[str] | None = None,
    ) -> None:
        """Update the reference antenna list to demote/remove specified antennas."""
        if not (self.reference_antenna and self.reference_antenna.strip()):
            LOG.warning(
                'No reference antennas registered set for MS {} ({}), cannot update its reference antenna list.'.format(
                    self.basename, hex(id(self))
                )
            )
            return

        previous_reference_antenna = self.reference_antenna

        refants_to_keep: list[str] = []
        refants_to_move: list[str] = []
        for ant in self.reference_antenna.split(','):
            if not ants_to_remove or ant not in ants_to_remove:
                if ants_to_demote and ant in ants_to_demote:
                    refants_to_move.append(ant)
                else:
                    refants_to_keep.append(ant)
        refants_to_keep.extend(refants_to_move)

        self.reference_antenna = ','.join(refants_to_keep)

        LOG.info(
            'ms.update_reference_antennas for MS %s (%s): previous list=%s, removed=%s, demoted=%s, new list=%s',
            self.basename,
            hex(id(self)),
            previous_reference_antenna,
            ','.join(sorted(ants_to_remove)) if ants_to_remove else 'none',
            ','.join(sorted(ants_to_demote)) if ants_to_demote else 'none',
            self.reference_antenna,
        )

    def _source_select_to_list(self, source_select: str | None) -> list[str]:
        """Convert a CASA-style source selection string to a list of source names.

        Args:
            source_select: Source string to convert.

        Returns:
            List of source names (as strings).
        """
        if source_select is None or not source_select.strip():
            # If None or empty or blank selection string, use all sources
            source_list = [utils.dequote(s.name) for s in self.sources]
        else:
            source_list = [utils.dequote(s.strip()) for s in source_select.split(',')]
        return source_list

    def _spw_select_to_list(self, spw_select: str | None) -> list[int]:
        """Convert a CASA-style spw selection string to a list of spw IDs.

        Args:
            spw_select: Spw selection string to convert.

        Returns:
            List of spw IDs (as integers).
        """
        if spw_select is None or not spw_select.strip():
            # If None or empty or blank selection string, use all spws
            spw_list = [s.id for s in self.spectral_windows]
        else:
            spw_list = utils.range_to_list(spw_select)
        return spw_list

    def get_data_column(self, dtype: DataType, source: str | None = None, spw: str | None = None) -> str | None:
        """Return all available column names for this MS."""
        with casa_tools.TableReader(self.name) as table:
            return table.colnames()

    def data_colnames(self) -> list[str]:
        """
        Return all data column names for this MS.
        """
        return [colname for colname in self.all_colnames() if colname in ('DATA', 'FLOAT_DATA', 'CORRECTED_DATA')]

    def set_data_type_dicts(
        self,
        data_type_per_column: dict[DataType, str],
        data_types_per_source_and_spw: dict[tuple[str, int], list[DataType]],
    ) -> None:
        """Set the data type lookup dictionaries from MS metadata.

        Args:
            data_type_per_column: Mapping of DataType to column name.
            data_types_per_source_and_spw: Mapping of (source, spw) to DataTypes.
        """
        self.data_column = dict(data_type_per_column)
        self.data_types_per_source_and_spw = dict(data_types_per_source_and_spw)

    def set_data_column(
        self,
        dtype: DataType,
        column: str,
        source: str | None = None,
        spw: str | None = None,
        save_to_ms: bool = True,
    ) -> None:
        """Set the column name associated with a DataType.

        Args:
            dtype: DataType to associate with the column.
            column: Name of column in MS.
            source: Source names (comma separated name selection string) to
                filter for. If unset, all sources will be used.
            spw: Spectral windows (comma separated real spw ID selection
                string) to filter for. If unset, all real spw IDs will be used.
            save_to_ms: Whether to persist the mapping to the MS on disk.
        """
        self.data_column[dtype] = column

        # Always populate data_types_per_source_and_spw. If source/spw filters are
        # provided, use only those; otherwise populate for all sources and SPWs.
        source_name_list = self._source_select_to_list(source)
        spw_id_list = self._spw_select_to_list(spw)
        for source_name in source_name_list:
            for spw_id in spw_id_list:
                key = (source_name, spw_id)
                self.data_types_per_source_and_spw.setdefault(key, [])
                if dtype not in self.data_types_per_source_and_spw[key]:
                    self.data_types_per_source_and_spw[key].append(dtype)

        if save_to_ms:
            # Legacy behavior writes datatype metadata into the MS history; keep
            # this as a no-op for now to preserve in-memory behavior.
            pass

    def get_data_column(self, dtype: DataType, source: str | None = None, spw: str | None = None) -> str | None:
        """
        Return the column name associated with a DataType in an MS domain
        object for given source and spectral window.

        If ``source`` and ``spw`` are both unset, the method will just look
        at the MS data type and column information. If one or both parameters
        are set, it will require all (source,spw) combinations to have data of
        the requested data type.

        Args:
            dtype: DataType to fetch column name for
            source: Source names (comma separated name selection string) to
                filter for. If unset, all sources will be used.
            spw: Spectral windows (comma separated real spw ID selection string)
                to filter for. If unset, all real spw IDs will be used.

        Returns:
            A name of column of a dtype. Returns None if dtype is not defined
            in the MS.
        """
        resolved_dtype = dtype
        if resolved_dtype not in self.data_column.keys():
            # Serialized contexts may carry string keys instead of DataType enums.
            dtype_name = getattr(dtype, 'name', str(dtype))
            if dtype_name in self.data_column:
                resolved_dtype = dtype_name
            else:
                return None

        if source is None and spw is None:
            return self.data_column[resolved_dtype]

        source_name_list = self._source_select_to_list(source)
        spw_id_list = self._spw_select_to_list(spw)

        # Check all (source,spw) combinations
        data_exists_for_all_source_spw_combinations = True
        for source_name in source_name_list:
            for spw_id in spw_id_list:
                key = (source_name, spw_id)
                dtype_list = self.data_types_per_source_and_spw.get(key, [])
                dtype_names = {getattr(entry, 'name', str(entry)) for entry in dtype_list}
                if getattr(dtype, 'name', str(dtype)) not in dtype_names:
                    data_exists_for_all_source_spw_combinations = False

        if data_exists_for_all_source_spw_combinations:
            return self.data_column[resolved_dtype]
        else:
            return None

    def get_data_type(self, column: str, source: str | None = None, spw: str | None = None) -> DataType | None:
        """Return the DataType associated with a column.

        If source and spw are both unset, the method will just look at the MS
        data type and column information. If one or both parameters are set,
        it will require all (source,spw) combinations to have data of the
        requested data type.

        Args:
            column: Name of column in MS.
            source: Source names (comma separated name selection string) to
                filter for. If unset, all sources will be used.
            spw: Spectral windows (comma separated real spw ID selection
                string) to filter for. If unset, all real spw IDs will be used.

        Returns:
            DataType associated with the column name. None if dtype is not
            defined in the MS or in the source/spw selection.
        """
        if column not in self.data_column.values():
            return None

        # Invert dictionary. This should not lead to wrong mappings
        # because data types and columns have a 1:1 relation.
        data_type = {v: k for k, v in self.data_column.items()}

        if source is None and spw is None:
            return data_type[column]

        source_name_list = self._source_select_to_list(source)
        spw_id_list = self._spw_select_to_list(spw)

        # Check all (source,spw) combinations
        data_exists_for_all_source_spw_combinations = True
        column_dtype = data_type[column]
        for source_name in source_name_list:
            for spw_id in spw_id_list:
                key = (source_name, spw_id)
                if column_dtype not in self.data_types_per_source_and_spw.get(key, []):
                    data_exists_for_all_source_spw_combinations = False

        if data_exists_for_all_source_spw_combinations:
            return column_dtype
        else:
            return None

    def _source_select_to_list(self, source_select: str | None) -> list[str]:
        """
        Convert a CASA-style source selection string to a list of source names.

        Args:
            source_select: source string to convert

        Returns:
            A list of source names (as strings)
        """
        if source_select is None or not source_select.strip():
            # if None or empty or blank selection string, use all sources
            source_list = [utils.dequote(s.name) for s in self.sources]
        else:
            source_list = [utils.dequote(s.strip()) for s in source_select.split(',')]

        return source_list

    def _spw_select_to_list(self, spw_select: str | None) -> list[int]:
        """
        Convert a CASA-style spw selection string to a list of spw IDs.

        Args:
            spw_select: spw selection string to convert

        Returns:
            A list of spw IDs (as integers)
        """
        if spw_select is None or not spw_select.strip():
            # if None or empty or blank selection string, use all spws
            spw_list = [s.id for s in self.spectral_windows]
        else:
            spw_list = utils.range_to_list(spw_select)

        return spw_list

    # PIPE-2307: moving compute_az_el_to_field, compute_az_el_for_ms methods from pipeline.infrastructure.htmlrenderer to here
    def compute_az_el_to_field(
        self, field: Field | None = None, epoch: EpochDict | None = None
    ) -> list[float]:
        """Compute azimuth and elevation of a field at a given epoch.

        Uses the CASA measures tool to convert the direction of a field to
        azimuth and elevation (AZELGEO frame) at the time specified by the
        epoch and location of the observatory.

        Args:
            field: Field domain object or None.
            epoch: Dictionary representing the time epoch.

        Returns:
            A list containing azimuth (degrees) and elevation (degrees), in that order.
        """
        me = casa_tools.measures
        me.doframe(epoch)
        me.doframe(me.observatory(self.antenna_array.name))
        myazel = me.measure(field.mdirection, 'AZELGEO')
        myaz = myazel['m0']['value']
        myel = myazel['m1']['value']
        myaz = (myaz * 180 / np.pi) % 360
        myel *= 180 / np.pi

        return [myaz, myel]

    def compute_az_el_for_ms(self, func: Callable) -> tuple[float, float]:
        """Computes overall azimuth and elevation values across POINTING, SIDEBAND, ATMOSPHERE scans.

        Applies the given aggregation function (e.g. min, max, mean) to
        azimuth and elevation values computed at the start and end of each
        field in science scans.

        Args:
            func: A function that takes a list of floats and returns a single float.
                Common examples include `min`, `max`, or `np.mean`.

        Returns:
            A tuple containing the aggregated azimuth and elevation values.
        """
        cal_scans = self.get_scans(scan_intent='POINTING,SIDEBAND,ATMOSPHERE')
        scans = [s for s in self.scans if s not in cal_scans]

        az = []
        el = []
        for scan in scans:
            for field in scan.fields:
                az0, el0 = self.compute_az_el_to_field(field, scan.start_time)
                az1, el1 = self.compute_az_el_to_field(field, scan.end_time)
                az.append(func([az0, az1]))
                el.append(func([el0, el1]))

        return func(az), func(el)
