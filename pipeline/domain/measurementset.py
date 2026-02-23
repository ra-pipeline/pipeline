"""Provide a class to store logical representation of MeasurementSet."""
# Do not evaluate type annotations at definition time.
from __future__ import annotations

import collections
import contextlib
import datetime
import itertools
import operator
import os
from collections.abc import Sequence
from typing import TYPE_CHECKING

import numpy as np

from pipeline import infrastructure
from pipeline.domain import measures, spectralwindow
from pipeline.infrastructure import casa_tools, tablereader, utils
from pipeline.infrastructure.launcher import current_task_name

if TYPE_CHECKING:
    from pipeline.domain import Antenna, AntennaArray, DataDescription, DataType, Field, Polarization, Scan, State
    from pipeline.infrastructure.tablereader import RetrieveByIndexContainer

LOG = infrastructure.logging.get_logger(__name__)


class MeasurementSet:
    """A logical representation of a MeasurementSet (MS).

    The MeasurementSet class represents the metadata and relationships held in a
    measurement set on disk, acting as an in-memory representation so that
    metadata and relationships can be quickly queried without additional disk I/O.

    MeasurementSet does not cache binary data or offer functions to facilitate
    processing of binary data held in the measurement set. For general reading
    of binary data, see the MSWrapper class.

    Attributes:
        name: Name of MeasurementSet, equivalent to file path to MeasurementSet.
        session: Name of session associated with MS.

        exclude_num_chans: Tuple containing spectral window sizes (in number of
            channels) used to filter out non-science-spectral-windows.
        filesize: Disk size of MS.

        acs_software_build_version: ALMA Common Software build version used to
            create this MS (None if not ALMA).
        acs_software_version: ALMA Common Software version used to create this
            MS (None if not ALMA).
        antenna_array: Antenna array information.
        array_name: Name of array configuration.
        correlator_name: The name of the correlator, populated from the
            PROCESSOR table. Example values: ALMA_ACA, ALMA_BASELINE.
        data_column: A dictionary to store data type (key) and corresponding
            data column (value).
        data_descriptions: A list of DataDescription objects associated with MS.
        data_types_per_source_and_spw: A dictionary to store a list of
            available data types (values) in this MS per (source,spw) tuples
            (keys).
        execblock_id: Execution Block ID for this MS (only for ALMA, VLA).
        fields: A list of Field objects associated with MS.
        observer: The name of the observer, as listed in the OBSERVATIONS table.
        observing_modes: The name(s) of the Observing Mode(s) used for this MS,
            populated from the ASDM_SBSUMMARY table (empty list if not ALMA).
        polarizations: A list of Polarization objects associated with the MS.
        project_id: Project ID associated with this MS, as listed in the
            OBSERVATIONS table.
        representative_target: A tuple of the name of representative source,
            frequency and bandwidth.
        representative_window: A representative spectral window name.
        scans: A list of Scan objects associated with MS.
        schedblock_id: Scheduling Block ID for this MS (only for ALMA, VLA).
        science_goals: A science goal information consists of min/max acceptable
            angular resolution, max allowed beam ratio, sensitivity, dynamic
            range, spectral dynamic range bandwidth (Cycle 10+), and SB name.
        sources: A list of Source objects associated with MS.
        spectral_windows: A list of SpectralWindow objects associated with MS.
        spectralspec_spwmap: A dictionary to map each SpectralSpec to a list of
            corresponding spectral window IDs.
        states: A list of State objects associated with MS.

        derived_fluxes: Calibrated visibility based flux measurements derived
            during pipeline run, used in subsequent imaging stages.
        fluxscale_fluxes: Flux measurements derived by CASA's fluxscale during
            the hifa_gfluxscale task, for use by a subsequent hifa_polcal task
            (ALMA interferometry polarisation calibration only).
        origin_ms: A path to the first generation MeasurementSet from which
            the current MS is generated. This is typically set by tasks such as
            h_mssplit, hif_mstransform, hifv_mstransform, hif_transformimagedata.
        phase_calapps_for_check_sources: List of CalApplications for the phase
            calibration of the check source(s) generated during hifa_gfluxscale.
            These are used in a subsequent hifa_timegaincal task to overplot
            the phase calibration for check source in its Diagnostic Phase Vs.
            Time plots.
        phasecal_mapping: A dictionary mapping phase calibrator fields to
            corresponding fields with TARGET or CHECK intent; typically
            populated by the hifa_spwphaseup task (ALMA-only).
        phaseup_caltable_for_phase_rms: The bandpass phase-up caltable created
            during the hifa_bandpass task (prior to deriving the bandpass
            solution), for use in subsequent phase RMS stability assessment
            during the hifa_spwphaseup task (ALMA-interferometry-only).
        reference_antenna_locked: If True, reference antenna is locked to
            prevent modification. Typically used in polarization calibration
            stages / recipes.
        reference_spwmap: Vector of spectral window IDs, enabling flux scaling
            across spectral windows. Typically populated by the hifa_fluxcalflag
            task, and used by a subsequent hifa_gfluxscale task in its call to
            CASA `fluxscale` task (ALMA-interferometry-only).
        spwmaps: Dictionary mapping (intent, field) keys to corresponding
            phase-up spectral window mapping to use for combining/mapping
            spectral windows; used in subsequent calibration tasks
            (ALMA-interferometry-only).
    """
    def __init__(self, name: str, session: str | None = None) -> None:
        """
        Initialize a MeasurementSet object.

        Args:
            name: A path to MS.
            session: Name of session associated with MS.
        """
        # Attributes based on input arguments.
        self.name: str = name
        self.session: str | None = session

        # Other attributes populated at init.
        self.exclude_num_chans: tuple[int, int] = (1, 4)
        self.filesize: measures.FileSize = self._calc_filesize()

        # Attributes expected to be populated during import of MS (see
        # infrastructure.tablereader.MeasurementSetReader.get_measurement_set).
        self.acs_software_build_version: str | None = None  # PIPE-132
        self.acs_software_version: str | None = None  # PIPE-132
        self.antenna_array: AntennaArray | None = None
        self.array_name: str = ''
        self.correlator_name: str | None = None
        self.data_column: dict = {}  # PIPE-1062
        self.data_descriptions: RetrieveByIndexContainer | list = []
        self.data_types_per_source_and_spw: dict = {}  # PIPE-1246
        self.execblock_id: str = ''
        self.fields: RetrieveByIndexContainer | list = []
        self.observer: str = ''
        self.observing_modes: list[str] = []  # PIPE-2084
        self.polarizations: list[Polarization] = []
        self.project_id: str = ''
        self.representative_target: tuple[str | None, dict | None, dict | None] = (None, None, None)
        self.representative_window: str | None = None
        self.scans: list = []
        self.schedblock_id: str = ''
        self.science_goals: dict = {}
        self.sources: RetrieveByIndexContainer | list = []
        self.spectral_windows: RetrieveByIndexContainer | list = []
        self.spectralspec_spwmap: dict = {}  # PIPE-1132
        self.states: RetrieveByIndexContainer | list = []

        # Attributes expected to be populated during the Pipeline run, to store
        # information derived by stages that is used in subsequent stages.
        self.derived_fluxes: collections.defaultdict | None = None  # PIPE-644, PIPE-660
        self.fluxscale_fluxes: collections.defaultdict | None = None  # PIPE-1776
        self.origin_ms: str = name  # PIPE-1062
        self.phase_calapps_for_check_sources = []  # PIPE-1377
        self.phasecal_mapping: dict = {}  # PIPE-1154
        self.phaseup_caltable_for_phase_rms = []  # PIPE-1624
        self.reference_spwmap: list[int] | None = None
        self.spwmaps: dict = {}  # PIPE-1154

        # Polarisation calibration requires the refant list be frozen, after
        # which subsequent gaincal calls are executed with
        # refantmode='strict'.
        #
        # To meet this requirement we make the MS refant list lockable. When
        # locked, the refant list cannot be changed. Additionally, gaincal
        # checks the lock status to know whether to set refantmode to strict.
        #
        # The backing property for the refant list.
        self._reference_antenna: str | None = None
        # The refant lock. Setting reference_antenna_locked to True prevents
        # the reference antenna list from being modified. I would have liked
        # to put the lock on a custom refant list class, but some tasks check
        # the type of reference_antenna directly which prevents that approach.
        self.reference_antenna_locked: bool = False

    def _calc_filesize(self) -> measures.FileSize:
        """
        Calculate the disk usage of this measurement set.
        """
        total_bytes = 0
        for dirpath, _, filenames in os.walk(self.name):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_bytes += os.path.getsize(fp)

        return measures.FileSize(total_bytes,
                                 measures.FileSizeUnits.BYTES)

    def __str__(self) -> str:
        return 'MeasurementSet({0})'.format(self.name)

    @property
    def intents(self) -> set[str]:
        """Return unique intents in the measurement set."""
        intents = set()
        # we look to field rather than state as VLA datasets don't have state
        # entries
        for field in self.fields:
            intents.update(field.intents)
        return intents

    @property
    def antennas(self) -> list[Antenna]:
        """Return list of Antenna objects for all antennas in the measurement set."""
        # return a copy rather than the underlying list
        return list(self.antenna_array.antennas)

    @property
    def basename(self) -> str:
        """Return base path to the measurement set."""
        return os.path.basename(self.name)

    @property
    def is_band_to_band(self) -> bool:
        """Return whether this MS is for band-to-band interferometry.

        Criteria adopted from PIPE-2084: an MS is deemed to be for band-to-band
        interferometry if either the observing mode declares it as band-to-band,
        or if the diffgain intent + SpW setup are consistent with band-to-band.
        The latter covers datasets that don't have correct observing mode set in
        their metadata.
        """
        return "BandToBand Interferometry" in self.observing_modes or self.get_diffgain_mode() == "B2B"

    def get_antenna(self, search_term: str = '') -> list[Antenna]:
        """
        Return Antenna(s) for given antenna selection in CASA format.

        If the ``search_term`` is omitted or an empty string, this will return
        all antennas in the measurement set.

        Args:
            search_term: Antenna selection string in CASA format.

        Returns:
            List of Antenna objects matching search term.
        """
        if search_term == '':
            return self.antennas

        return [a for a in self.antennas
                if a.id in utils.ant_arg_to_id(self.name, search_term, self.antennas)]

    def get_state(self, state_id: int | None = None) -> State | None:
        """
        Return State in MeasurementSet matching the given identifier.

        Args:
            state_id: Numerical identifier of state to search for.

        Returns:
            State object associated with matched identifier, or None if no match
            was found.
        """
        match = [state for state in self.states if state.id == state_id]
        if match:
            return match[0]
        else:
            return None

    def get_scans(
            self,
            scan_id: int | Sequence[int] | None = None,
            scan_intent: str | Sequence[str] | None = None,
            field: int | str | None = None,
            spw: int | str | Sequence[int] | Sequence[str] | None = None,
            ) -> list[Scan]:
        """
        Return Scan(s) in MeasurementSet matching the given criteria (ID,
        intent, field, and/or spectral window). If no criteria are given, all
        Scans in the MeasurementSet will be returned.

        Criteria arguments can be given as either single items of the expected
        type, sequences of the expected type, or in the case of intent or spw,
        as a comma-separated values string. For example, intent could be
        'ATMOSPHERE', 'ATMOSPHERE,BANDPASS', or ('ATMOSPHERE', 'BANDPASS').

        Args:
            scan_id: Scan ID(s) to match.
            scan_intent: Intent(s) to match.
            field: Field(s) to match, as field selection in CASA format.
            spw: Spectral window(s) to match.

        Returns:
            List of Scan objects for scans in MS matching the given criteria.
        """
        pool = self.scans

        if scan_id is not None:
            # encase raw numbers in a tuple
            if not isinstance(scan_id, collections.abc.Sequence):
                scan_id = (scan_id,)
            pool = [s for s in pool if s.id in scan_id]

        if scan_intent is not None:
            if isinstance(scan_intent, str):
                if scan_intent in ('', '*'):
                    # empty string equals all intents for CASA
                    scan_intent = ','.join(self.intents)
                scan_intent = scan_intent.split(',')
            scan_intent = set(scan_intent)
            pool = [s for s in pool if not s.intents.isdisjoint(scan_intent)]

        if field is not None:
            fields_with_name = frozenset(self.get_fields(task_arg=field))
            pool = [s for s in pool if not fields_with_name.isdisjoint(s.fields)]

        if spw is not None:
            if not isinstance(spw, collections.abc.Sequence):
                spw = (spw,)
            if isinstance(spw, str):
                if spw in ('', '*'):
                    spw = ','.join(str(spw.id) for spw in self.spectral_windows)
                if '~' in spw:
                    spw = utils.range_to_list(spw)
                else:
                    spw = spw.split(',')
            spw = {int(i) for i in spw}
            pool = {scan for scan in pool for scan_spw in scan.spws if scan_spw.id in spw}
            pool = sorted(pool, key=lambda s: s.id)

        return pool

    def get_data_description(
            self,
            spw: int | spectralwindow.SpectralWindow | None = None,
            id: int | None = None,
            ) -> DataDescription | None:
        """
        Return the DataDescription in the MeasurementSet that matches the given
        criteria (spectral window or ID). If no criteria are given, this will
        return None. If both `spw` and `id` are given, this will match by `id`
        only.

        Args:
            spw: Spectral window to match (as ID or SpectralWindow object).
            id: Data description numerical identifier to match.

        Returns:
            DataDescription matching the given criteria, or None if no match was found.
        """
        match = None
        if spw is not None:
            if isinstance(spw, spectralwindow.SpectralWindow):
                match = [dd for dd in self.data_descriptions
                         if dd.spw is spw]
            elif isinstance(spw, int):
                match = [dd for dd in self.data_descriptions
                         if dd.spw.id == spw]
        if id is not None:
            match = [dd for dd in self.data_descriptions if dd.id == id]

        if match:
            return match[0]
        else:
            return None

    def get_representative_source_spw(
            self,
            source_name: str | None = None,
            source_spwid: int | None = None,
            ) -> tuple[str | None, int | None]:
        """Get the representative target source object.

        * Use user name if ``source_name`` is supplied by user and it has TARGET intent.
        * Otherwise, use the source defined in the ASDM SBSummary table if it has TARGET intent.
        * Otherwise, use the first source in the source list with TARGET intent.

        Args:
            source_name: A string with the source name, or None for an automatic selection.
            source_spwid: An int with the spw id, or None for an automatic selection.

        Returns:
            a tuple with representative source name and spw id;
            if such a source cannot be identified, return (None, None),
            and if a spw cannot be determined, return (name, None).
        """
        qa = casa_tools.quanta
        cme = casa_tools.measures

        # PIPE-1504/PIPE-2859: only issue certain messages at the WARNING level if they are executed by hifa_imageprecheck
        if current_task_name.get() == 'hifa_imageprecheck':
            # Only issue messages at the WARNING level if they are executed by hifa_imageprecheck
            log_level = infrastructure.logging.WARNING
        else:
            log_level = infrastructure.logging.INFO

        if source_name:
            # Use the first target source that matches the user defined name
            target_sources = [source for source in self.sources
                              if source.name == source_name
                              and 'TARGET' in source.intents]
            if len(target_sources) > 0:
                LOG.info('Selecting user defined representative target source %s for data set %s',
                         source_name, self.basename)
                target_source = target_sources[0]
            else:
                LOG.warning('User defined representative target source %s not found in data set %s',
                            source_name, self.basename)
                target_source = None
        elif self.representative_target[0]:
            # Use the first target source that matches the representative source name in the ASDM
            # SBSummary table
            source_name = self.representative_target[0]
            target_sources = [source for source in self.sources
                              if source.name == source_name
                              and 'TARGET' in source.intents]
            if len(target_sources) > 0:
                LOG.info('Selecting representative target source %s for data set %s',
                         self.representative_target[0], self.basename)
                target_source = target_sources[0]
            else:
                LOG.warning('Representative target source %s not found in data set %s',
                            self.representative_target[0], self.basename)
                # Try to fall back first target source
                target_sources = [source for source in self.sources
                                  if 'TARGET' in source.intents]
                if len(target_sources) > 0:
                    target_source = target_sources[0]
                    LOG.info('Falling back to first target source (%s) for data set %s',
                             target_source.name, self.basename)
                else:
                    LOG.warning('No target sources observed for data set %s', self.basename)
                    target_source = None
        else:
            # Use first target source no matter what it is
            target_sources = [source for source in self.sources
                              if 'TARGET' in source.intents]
            if len(target_sources) > 0:
                target_source = target_sources[0]
                LOG.info('Undefined representative target source, defaulting to first target source (%s) for data set %s',
                         target_source.name, self.basename)
            else:
                LOG.warning('No target sources observed for data set %s', self.basename)
                target_source = None

        # Target source not found
        if target_source is None:
            return None, None

        # Target source name
        target_source_name = target_source.name

        # Check the user defined spw and return it if it was observed for the
        # representative source. If it was not observed quit.
        if source_spwid:
            found = False
            for f in target_source.fields:
                valid_spwids = [spw.id for spw in list(f.valid_spws)]
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
        # Check for representative spw from ASDM (>= Cycle 7)
        if self.representative_window is not None:
            try:
                target_spwid = [s.id for s in self.get_spectral_windows() if s.name == self.representative_window][0]
            except:
                LOG.log(log_level, 'Could not translate spw name %s to ID. Trying frequency matching heuristics.',
                        self.representative_window)

        if target_spwid is not None:
            return target_source_name, target_spwid

        # Get the representative bandwidth
        #     Return if there isn't one
        if not self.representative_target[2]:
            if self.antenna_array.name not in ('VLA', 'EVLA'):
                LOG.warning('Undefined representative bandwidth for data set %s', self.basename)
            return target_source_name, None

        target_bw = cme.frequency('TOPO',
            qa.quantity(qa.getvalue(self.representative_target[2]),
            qa.getunit(self.representative_target[2])))

        # Get the representative frequency
        #     Return if there isn't one
        if not self.representative_target[1]:
            LOG.warning('Undefined representative frequency for data set %s', self.basename)
            return target_source_name, None
        target_frequency = cme.frequency('BARY',
            qa.quantity(qa.getvalue(self.representative_target[1]),
            qa.getunit(self.representative_target[1])))

        # Convert BARY frequency to TOPO
        #    Use the start time of the first target source scan
        #    Note some funny business with source and field names
        cme.doframe(cme.observatory(self.antenna_array.name))
        cme.doframe(target_source.direction)
        target_scans = [
            scan for scan in self.get_scans(scan_intent='TARGET')
            if target_source.id in [f.source_id for f in scan.fields]]
        if len(target_scans) > 0:
            cme.doframe(target_scans[0].start_time)
            target_frequency_topo = cme.measure(target_frequency, 'TOPO')
        else:
            LOG.error('Unable to convert representative frequency to TOPO for data set %s', self.basename)
            target_frequency_topo = None
        cme.done()

        # No representative frequency
        if not target_frequency_topo:
            return target_source_name, None

        # Find the science spw

        # Get the science spw ids
        science_spw_ids = [spw.id for spw in self.get_spectral_windows()]

        # Get the target science spws observed for the target source
        target_spws = {spw for f in target_source.fields for spw in f.valid_spws
                       if spw.id in science_spw_ids}

        # Now find all the target_spws that have a channel width less than
        # or equal to the representative bandwidth
        # Note that the representative bandwidth can be slightly smaller than the actual channel width.
        # This is due to the details of online Hanning smoothing and is technically correct. We thus
        # apply a 1% margin (see CAS-11710).
        target_spws_bw = [spw for spw in target_spws
                          if spw.channels[0].getWidth().to_units(measures.FrequencyUnits.HERTZ) <= 1.01 * target_bw['m0']['value']]

        if len(target_spws_bw) <= 0:
            LOG.warning('No target spws have channel width <= representative bandwidth in data set %s', self.basename)

            # Now find all the target spws that contain the representative frequency.
            target_spws_freq = [spw for spw in target_spws
                                if spw.min_frequency.value <= target_frequency_topo['m0']['value'] <= spw.max_frequency.value]

            if len(target_spws_freq) <= 0:
                LOG.warning('No target spws overlap the representative frequency in data set %s', self.basename)

                # Now find the closest match to the center frequency
                max_freqdiff = np.finfo('d').max
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
                LOG.info('Selecting the narrowest chanwidth spw id %s which overlaps the representative frequency in data set %s',
                         target_spwid, self.basename)

            return target_source_name, target_spwid

        # Now find all the spw that contain the representative frequency
        target_spws_freq = [spw for spw in target_spws_bw
                            if spw.min_frequency.value <= target_frequency_topo['m0']['value'] <= spw.max_frequency.value]
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
            LOG.info('Selecting widest channel width spw id %s with channel width <= representative bandwidth in data'
                     ' set %s', str(target_spwid), self.basename)

            return target_source_name, target_spwid

        # For all the spws with channel width less than or equal
        # to the representative bandwidth which contain the
        # representative frequency select the one with the spw
        # with the greatest bandwidth.
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
        """
        Get Fields from this MeasurementSet matching the given criteria. If no
        criteria are given, all Fields in the MeasurementSet will be returned.

        Arguments can be given as either single items of the expected type,
        sequences of the expected type, or as comma separated strings in the
        case of name and/or intent. For instance, name could be 'HOIX',
        'HOIX,0841+708' or ('HOIX','0841+708').

        Args:
            task_arg: A field selection in CASA format to match.
            field_id: Field ID(s) to match.
            name: Field name(s) to match.
            intent: Select fields that are associated with these intents. If
                set to an empty string or '*', this is the equivalent to all
                intents in the measurement set.

        Returns:
            List of Field objects for fields in MS matching the given criteria.
        """
        pool = self.fields

        if task_arg not in (None, ''):
            field_id_for_task_arg = utils.field_arg_to_id(self.name, task_arg, self.fields)
            pool = [f for f in pool if f.id in field_id_for_task_arg]

        if field_id is not None:
            # encase raw numbers in a tuple
            if not isinstance(field_id, collections.abc.Sequence):
                field_id = (field_id,)
            pool = [f for f in pool if f.id in field_id]

        if name is not None:
            if isinstance(name, str):
                name = name.split(',')
            name = set(name)
            pool = [f for f in pool if f.name in name]

        if intent is not None:
            if isinstance(intent, str):
                if intent in ('', '*'):
                    # empty string equals all intents for CASA
                    intent = ','.join(self.intents)
                intent = intent.split(',')
            intent = set(intent)
            pool = [f for f in pool if not f.intents.isdisjoint(intent)]

        return pool

    def get_spectral_window(self, spw_id: int | str) -> spectralwindow.SpectralWindow:
        """
        Return the SpectralWindow object matching the given identifier.
        The identifier can be provided as an integer or string of integer.

        Args:
            spw_id: Numerical identifier of spectral window to match.

        Returns:
            SpectralWindow object for spectral window matching the identifier.

        Raises:
            KeyError if no matching spectral window is found for given identifier.
        """
        if spw_id is not None:
            spw_id = int(spw_id)
            match = [spw for spw in self.spectral_windows
                     if spw.id == spw_id]
            if match:
                return match[0]
            else:
                raise KeyError('No spectral window with ID \'{0}\' found in '
                               '{1}'.format(spw_id, self.basename))

    def get_spectral_windows(
            self,
            task_arg: int | str = '',
            with_channels: bool = False,
            num_channels: list | None = None,
            science_windows_only: bool = True,
            spectralspecs: list | None = None,
            intent: str | None = None,
            ) -> list[spectralwindow.SpectralWindow | spectralwindow.SpectralWindowWithChannelSelection]:
        """
        Return spectral windows matching given criteria.

        This returns spectral windows that correspond to the given CASA-style
        spw argument (specified as ``task_arg``), filtering out windows for a
        number of criteria: number of channels, science spectral windows,
        spectral specs, intents.

        By default, this returns a list of SpectralWindow objects; if
        ``with_channels`` is True, this will instead return the spectral windows
        as a list of SpectralWindowWithChannelSelection objects.

        Args:
            task_arg: Spectral window selection to match, as either single
                integer ID, or one-or-more IDs in CASA-style string format.
            with_channels: If True, return spectral window with channel selection.
            num_channels: Optional list of spectral window sizes in number of
                channels; if set, only return spectral windows whose number of
                channels matches any of the given sizes.
            science_windows_only: If True, only return "science" spectral
                windows, aka spectral windows associated with science intents.
            spectralspecs: Optional list of spectral specs; if set, only return
                spectral windows associated with given spectral specs.
            intent: Optional string of comma-separated intents; if set, only
                return spectral windows that observed given intent(s).

        Returns:
            List of SpectralWindow or SpectralWindowWithChannelSelection objects
            for given search criteria.
        """
        spws = self.get_all_spectral_windows(task_arg, with_channels)

        # If requested, filter spws by number of channels.
        if num_channels:
            spws = [w for w in spws if w.num_channels in num_channels]

        # If requested, filter spws by spectral specs.
        if spectralspecs is not None:
            spws = [w for w in spws if w.spectralspec in spectralspecs]

        # If requested, filter spws by intent(s).
        if intent is not None:
            spws = [w for w in spws if not set(intent.split(',')).isdisjoint(w.intents)]

        if not science_windows_only:
            return spws

        if self.antenna_array.name == 'ALMA':
            science_intents = {'TARGET', 'PHASE', 'BANDPASS', 'AMPLITUDE',
                               'POLARIZATION', 'POLANGLE', 'POLLEAKAGE',
                               'CHECK', 'DIFFGAINREF', 'DIFFGAINSRC'}
            return [w for w in spws if w.num_channels not in self.exclude_num_chans
                    and not science_intents.isdisjoint(w.intents)]

        if self.antenna_array.name in ('VLA', 'EVLA'):
            science_intents = {'TARGET', 'PHASE', 'BANDPASS', 'AMPLITUDE',
                               'POLARIZATION', 'POLANGLE', 'POLLEAKAGE',
                               'CHECK'}
            return [w for w in spws if w.num_channels not in self.exclude_num_chans
                    and not science_intents.isdisjoint(w.intents) and 'POINTING' not in w.intents]

        if self.antenna_array.name == 'NRO':
            science_intents = {'TARGET'}
            return [w for w in spws if not science_intents.isdisjoint(w.intents)]

        return spws

    def get_spectral_specs(self) -> list[str]:
        """Return list of all spectral specs used in the MS."""
        return list(self.spectralspec_spwmap.keys())

    def get_all_spectral_windows(
            self,
            task_arg: int | str = '',
            with_channels: bool = False,
            ) -> list[spectralwindow.SpectralWindow | spectralwindow.SpectralWindowWithChannelSelection]:
        """
        Return spectral windows corresponding to the given CASA-style spw
        argument.

        By default, this returns a list of SpectralWindow objects; if
        ``with_channels`` is True, this will instead return the spectral windows
        as a list of SpectralWindowWithChannelSelection objects.

        Args:
            task_arg: Spectral window selection to match, as either single
                integer ID, or one-or-more IDs in CASA-style string format.
            with_channels: If True, return spectral window with channel selection.

        Returns:
            List of SpectralWindow or SpectralWindowWithChannelSelection objects
            for given CASA-style search criteria.
        """
        # we may have more spectral windows in our MeasurementSet than have
        # data in the measurement set on disk. Ask for all
        if task_arg in (None, ''):
            task_arg = '*'

        # expand spw tuples into a range per spw, eg. spw9 : 1,2,3,4,5
        selected = collections.defaultdict(set)
        for (spw, start, end, step) in utils.spw_arg_to_id(self.name, task_arg, self.spectral_windows):
            selected[spw].update(set(range(start, end+1, step)))

        if not with_channels:
            return [spw for spw in self.spectral_windows if spw.id in selected]

        spws = []
        for spw_id, channels in selected.items():
            spw_obj = self.get_spectral_window(spw_id)
            proxy = spectralwindow.SpectralWindowWithChannelSelection(spw_obj, channels)
            spws.append(proxy)
        return spws

    def get_diffgain_mode(self) -> str | None:
        """
        Determine if the intents and SpW setup in this measurement set are
        consistent with an observing mode that uses a differential gain
        calibrator: BandToBand (B2B) or BandwidthSwitching (BWSW).

        Returns:
            - 'B2B' if the ratio of frequencies between on-source and reference spws is above 1.661;
            - 'BWSW' if the ratio of bandwidths between reference and on-source is above 1.5;
            - None if there are no DIFFGAIN* intents in this MS.

        Raises:
            ValueError if the DIFFGAIN* intents are present in the MS, but either
            a. the MS is missing diffgain reference or on-source SpWs, or
            b. the SpW setup does not match either BandToBand or BandwidthSwitching.
        """
        if 'DIFFGAINREF' in self.intents or 'DIFFGAINSRC' in self.intents:
            # Retrieve diffgain reference and diffgain on-source SpWs.
            dg_refspws = self.get_spectral_windows(intent='DIFFGAINREF')
            if not dg_refspws:
                raise ValueError(f'DIFFGAINREF intent missing in calibration sources for dataset {self.basename}')
            dg_srcspws = self.get_spectral_windows(intent='DIFFGAINSRC')
            if not dg_srcspws:
                raise ValueError(f'DIFFGAINSRC intent missing in science sources for dataset {self.basename}')

            # Retrieve the center frequency and bandwidth from the first
            # diffgain on-source SpW and first diffgain reference SpW. The setup
            # is expected to be the same for all SpWs.
            refcent = dg_refspws[0].centre_frequency.value
            scicent = dg_srcspws[0].centre_frequency.value
            refwidth = dg_refspws[0].bandwidth.value
            sciwidth = dg_srcspws[0].bandwidth.value

            # [at least] one of the above conditions has to be satisfied
            if scicent/refcent > 1.661:  # simple ratio to be out of band Cycle 10
                return 'B2B'
            elif refwidth/sciwidth > 1.5:
                return 'BWSW'

            raise ValueError(f'DIFFGAIN intent with an unsupported spectral setup for dataset {self.basename}')

        return None

    def get_original_intent(self, intent: str) -> set[str]:
        """
        Get the original obs_modes that correspond to the given pipeline
        observing intent(s).

        Args:
            intent: Pipeline intent(s) to convert.

        Returns:
            Set of original CASA intent(s) (obs_modes) corresponding to given
            Pipeline intent(s).
        """
        obs_modes = [state.get_obs_mode_for_intent(intent)
                     for state in self.states]
        return set(itertools.chain(*obs_modes))

    def get_alma_cycle_number(self) -> int | None:
        """Get the ALMA cycle number from the observation start time.

        Returns:
            Cycle number or None if not found or not an ALMA dataset.
        """
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
        if self.antenna_array.name != 'ALMA':
            return None
        start_time = utils.get_epoch_as_datetime(self.start_time)
        for cycle, (start_str, end_str) in cycle_numbers.items():
            start = datetime.datetime.strptime(start_str, '%Y-%m-%d')
            end = datetime.datetime.strptime(end_str, '%Y-%m-%d')
            if start <= start_time <= end:
                return cycle
        return None  # No match

    @property
    def start_time(self) -> dict:
        """Return start time for this measurement set as CASA 'epoch' measure dictionary."""
        earliest, _ = min([(scan, utils.get_epoch_as_datetime(scan.start_time)) for scan in self.scans],
                          key=operator.itemgetter(1))
        return earliest.start_time

    @property
    def end_time(self) -> dict:
        """Return end time for this measurement set as CASA 'epoch' measure dictionary."""
        latest, _ = max([(scan, utils.get_epoch_as_datetime(scan.end_time)) for scan in self.scans],
                        key=operator.itemgetter(1))
        return latest.end_time

    def get_vla_corrstring(self) -> str:
        """Get correlation string for VLA.

        Returns:
            corrstring: string value of correlation
        """
        # Prep string listing of correlations from dictionary created by method buildscans
        # For now, only use the parallel hands.  Cross hands will be implemented later.

        corrstring_list = self.polarizations[self.data_descriptions[0].pol_id].corr_type_string \
            if len(self.polarizations) and len(self.data_descriptions) > 0 else []
        removal_list = ['RL', 'LR', 'XY', 'YX']
        corrstring_list = sorted(set(corrstring_list).difference(set(removal_list)))
        corrstring = ','.join(corrstring_list)

        return corrstring

    def get_vla_corrlist_from_spw(self, spw: str | None = None) -> list:
        """Get all VLA correlation labels as a list of string from selected spw(s).

        Args:
            spw: a spw selection string or None. Defaults to None.

        Returns:
            list: a list of correlation labels.
        """
        corrs = set()
        for dd in self.data_descriptions:
            if spw in ('', '*', None) or (isinstance(spw, str) and str(dd.spw.id) in spw.split(',')):
                corrs = corrs.union(self.polarizations[dd.pol_id].corr_type_string)

        return sorted(corrs)

    def get_alma_corrstring(self) -> str:
        """Get correlation string for ALMA for the science spectral windows.

        Returns:
            corrstring: string value of correlation
        """
        sci_spwlist = self.get_spectral_windows(science_windows_only=True)
        sci_spwids = [spw.id for spw in sci_spwlist]

        datadescs = [dd for dd in self.data_descriptions if dd.spw.id in sci_spwids]

        numpols = len(datadescs[0].polarizations)

        if numpols == 1:
            corrstring = 'XX'
        else:
            corrstring = 'XX,YY'

        return corrstring

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

    def get_times_on_source_per_field_id(self, field: str, intent: str) -> dict[int, np.float]:
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
    def reference_antenna(self) -> str:
        """
        Get the reference antenna list for this MS. The refant value is
        a comma-separated string.

        Example: 'DV01,DV02,DV03'
        """
        return self._reference_antenna

    @reference_antenna.setter
    def reference_antenna(self, value: str) -> None:
        """
        Set the reference antenna list for this MS.

        Args:
            value: Antenna names to set as reference antennas.

        Raises:
            AttributeError if the reference antenna list is in read-only mode,
            as set by the reference_antenna_locked property.

        Example: ms.reference_antenna = 'DV01,DV02,DV03'
        """
        if self.reference_antenna_locked:
            # AttributeError is raised for R/O properties, which seems
            # appropriate for this scenario
            raise AttributeError(f'Refant list for {self.basename} is locked')
        self._reference_antenna = value

    def update_reference_antennas(
            self,
            ants_to_demote: set[str] | None = None,
            ants_to_remove: set[str] | None = None,
            ) -> None:
        """Update the reference antenna list for this MS to demote/remove specified antennas.

        Args:
            ants_to_demote: Set of antenna names to demote.
            ants_to_remove: Set of antenna names to remove.
        """
        # Return early if no refants are registered (None, or empty string).
        if not (self.reference_antenna and self.reference_antenna.strip()):
            LOG.warning('No reference antennas registered set for MS {} ({}), '
                        'cannot update its reference antenna list.'.
                        format(self.basename, hex(id(self))))
            return

        previous_reference_antenna = self.reference_antenna

        # Create updated refant list.
        refants_to_keep = []
        refants_to_move = []
        for ant in self.reference_antenna.split(','):
            if not ants_to_remove or ant not in ants_to_remove:
                if ants_to_demote and ant in ants_to_demote:
                    refants_to_move.append(ant)
                else:
                    refants_to_keep.append(ant)
        refants_to_keep.extend(refants_to_move)

        # Update refant list.
        self.reference_antenna = ','.join(refants_to_keep)

        LOG.info('ms.update_reference_antennas for MS %s (%s): previous list=%s, removed=%s, demoted=%s, new list=%s',
                 self.basename, hex(id(self)), previous_reference_antenna,
                 ','.join(sorted(ants_to_remove)) if ants_to_remove else 'none',
                 ','.join(sorted(ants_to_demote)) if ants_to_demote else 'none',
                 self.reference_antenna)

    @property
    def session(self):
        """Return name of session associated with this measurement set."""
        return self._session

    @session.setter
    def session(self, value: str) -> None:
        """
        Set name of session associated with this measurement set.

        Args:
            value: Name of session.
        """
        if value is None:
            value = 'session_1'
        self._session = value

    def all_colnames(self) -> list[str]:
        """
        Return all available column names for this MS.
        """
        with casa_tools.TableReader(self.name) as table:
            colnames = table.colnames()
        return colnames

    def data_colnames(self) -> list[str]:
        """
        Return all data column names for this MS.
        """
        return [colname for colname in self.all_colnames() if colname in ('DATA', 'FLOAT_DATA', 'CORRECTED_DATA')]

    def set_data_type_dicts(self, data_type_per_column: dict, data_types_per_source_and_spw: dict) -> None:
        """
        Set the data type lookup dictionaries directly without writing new
        MS HISTORY entries as they would already exist when calling this
        method. Also do not auto-generate the per source and spw lookup
        dictionary from the per column information since it might have a
        sparse structure (e.g. selfcal use case).

        Args:
            data_type_per_column: Data type per column lookup dictionary
            data_types_per_source_and_spw: Data type per source and spw
                lookup dictionary.
        """
        self.data_column = data_type_per_column
        self.data_types_per_source_and_spw = data_types_per_source_and_spw

    def set_data_column(
            self,
            dtype: DataType,
            column: str, source: str | None = None,
            spw: str | None = None,
            overwrite: bool = False,
            save_to_ms: bool = True,
            ) -> None:
        """Assign a data type to a column in the MS domain object.

        Set data type and column to MS domain object and record the available
        data types per (source,spw) tuple. If source or spw are unset, they
        will be expanded to all available values.

        Args:
            dtype: data type to set
            column: name of column in MS associated with the data type
            source: source name selection string (comma separated names). If
                unset, all sources will be used.
            spw: real spectral window selection string (string of comma
                separated IDs). If unset, all real spw IDs will be used.
            overwrite: if True existing data colum is overwritten by the new
                column. If False and if type is already associated with other
                column, the function raises ValueError.
            save_to_ms (bool, optional): If True, persists the datatype-to-column mapping
                to the MS history subtable. Defaults to True.                

        Raises:
            ValueError: An error raised when the column does not exist
                or the type is already associated with a column or the
                column is already assigned to a type and would not
                be overwritten.
        """
        # Check existence of the column
        colnames = self.data_colnames()
        if column not in colnames:
            raise ValueError('Column {} does not exist in {}'.format(column, self.basename))

        # Check if data type is already associated with another column
        if not overwrite and dtype in self.data_column and self.get_data_column(dtype) != column:
            raise ValueError('Data type {} is already associated with column {} in {}'.format(
                dtype, self.get_data_column(dtype), self.basename))

        # Check if column is already assigned to another data type
        if not overwrite and column in self.data_column.values() and self.get_data_column(dtype) != column:
            raise ValueError('Column {} is already associated with data type {} in {}'.format(
                column, [k for k, v in self.data_column.items() if v == column][0], self.basename))

        source_name_list = self._source_select_to_list(source)
        spw_id_list = self._spw_select_to_list(spw)

        # Update data types per (source,spw) selection
        for source_name in source_name_list:
            for spw_id in spw_id_list:
                key = (source_name, spw_id)
                if key in self.data_types_per_source_and_spw:
                    if dtype not in self.data_types_per_source_and_spw[key]:
                        self.data_types_per_source_and_spw[key].append(dtype)
                else:
                    self.data_types_per_source_and_spw[key] = [dtype]

        # Check for existing column registration and remove it
        column_keys = [k for k, v in self.data_column.items() if v == column]
        if column_keys != []:
            for k in column_keys:
                del (self.data_column[k])

        # Update MS domain object
        if dtype not in self.data_column:
            self.data_column[dtype] = column
            LOG.info('Updated data column information of %s. Set %s to column %s', self.basename, dtype, column)

        # Write data type lookup dictionaries to MS history (PIPEREQ-195). This is a
        # minimum fallback implementation and should be replaced by a properly
        # structured solution with sub-tables or other kind of metadata (maybe only in MSv4).
        if save_to_ms:
            with casa_tools.MSReader(self.name) as ms:
                ms.writehistory(
                    f"data_type_per_column = {dict((k.name, v) for k, v in self.data_column.items())}",
                    origin="Datatype Handler",
                )
                ms.writehistory(
                    f"data_types_per_source_and_spw = {dict((k, [item.name for item in v]) for k, v in self.data_types_per_source_and_spw.items())}",
                    origin="Datatype Handler",
                )

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
        if dtype not in self.data_column.keys():
            return None

        if source is None and spw is None:
            return self.data_column[dtype]

        source_name_list = self._source_select_to_list(source)
        spw_id_list = self._spw_select_to_list(spw)

        # Check all (source,spw) combinations
        data_exists_for_all_source_spw_combinations = True
        for source_name in source_name_list:
            for spw_id in spw_id_list:
                key = (source_name, spw_id)
                if dtype not in self.data_types_per_source_and_spw.get(key, []):
                    data_exists_for_all_source_spw_combinations = False

        if data_exists_for_all_source_spw_combinations:
            return self.data_column[dtype]
        else:
            return None

    def get_data_type(self, column: str, source: str | None = None, spw: str | None = None) -> DataType | None:
        """
        Return the DataType associated with a column in an MS domain object for
        given source and spectral window.

        If ``source`` and ``spw`` are both unset, the method will just look at
        the MS data type and column information. If one or both parameters are
        set, it will require all (source,spw) combinations to have data of the
        requested data type.

        Args:
            column: Name of column in MS
            source: Source names (comma separated name selection string) to
                filter for. If unset, all sources will be used.
            spw: Spectral windows (comma separated real spw ID selection string)
                to filter for. If unset, all real spw IDs will be used.

        Returns:
            The DataType associated with the column name. Returns None
            if dtype is not defined in the MS or in the source/spw
            selection.
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
    def compute_az_el_to_field(self, field: Field | None = None, epoch: dict | None = None) -> list[float]:
        """Computes azimuth and elevation of a field at a given epoch.

        This method uses the CASA `measures` tool to convert the direction
        of a field to azimuth and elevation (AZELGEO frame) at the time
        specified by the epoch and location of the observatory.

        Args:
            field : Field domain object or None.
            epoch :  A dictionary representing the time epoch.

        Returns:
            list: A list containing azimuth (degrees) and elevation (degrees), in that order.
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

    def compute_az_el_for_ms(self, func: callable) -> tuple[float, float]:
        """Computes overall azimuth and elevation values across POINTING, SIDEBAND, ATMOSPHERE scans.

        Applies the given aggregation function (e.g. `min`, `max`, `mean`) to azimuth and elevation
        values computed at the start and end of each field in science scans.

        Args:
            func (callable): A function that takes a list of floats and returns a single float.
                Common examples include `min`, `max`, or `np.mean`.

        Returns:
            tuple[float, float]: A tuple containing the aggregated azimuth and elevation values.
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
