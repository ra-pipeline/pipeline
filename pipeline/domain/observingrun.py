"""Pydantic-based ObservingRun domain object prototype for Phase 5 modernization."""

from __future__ import annotations

import collections
import itertools
import os
from typing import TYPE_CHECKING, Any, Iterable

from pydantic import BaseModel, ConfigDict, Field as PydanticField

import pipeline.infrastructure as infrastructure
from pipeline.domain.datatype import TYPE_PRIORITY_ORDER
from pipeline.domain.spectralwindow import match_spw_basename
from pipeline.infrastructure import utils

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime

    from pipeline.domain import DataType, MeasurementSet
    from pipeline.infrastructure.utils.casa_types import DirectionDict, EpochDict

LOG = infrastructure.get_logger(__name__)


def sort_measurement_set(ms: MeasurementSet) -> tuple[int, datetime]:
    """Return sort key for measurement set object."""
    data_types = set(itertools.chain(*ms.data_types_per_source_and_spw.values()))
    if data_types:
        data_priority = max(TYPE_PRIORITY_ORDER.index(t) for t in data_types)
    else:
        data_priority = len(TYPE_PRIORITY_ORDER)
    observation_start_time = utils.get_epoch_as_datetime(ms.start_time)
    return data_priority, observation_start_time


class ObservingRun(BaseModel):
    """Observing run domain object."""

    measurement_sets: list[MeasurementSet] = PydanticField(default_factory=list)
    ms_datatable_name: str = PydanticField(default='')
    ms_reduction_group: dict[str, Any] = PydanticField(default_factory=dict)
    org_directions: dict[str, DirectionDict] = PydanticField(default_factory=dict)
    virtual_science_spw_ids: dict[int, str] = PydanticField(default_factory=dict)
    virtual_science_spw_names: dict[str, int] = PydanticField(default_factory=dict)

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_default=True,
    )

    def __hash__(self) -> int:
        return hash((self.__class__, tuple(sorted(ms.basename for ms in self.measurement_sets))))

    @property
    def virtual_science_spw_shortnames(self) -> dict[str, str]:
        """Generate SPW shortnames derived from full SPW names."""
        result: dict[str, str] = {}
        for full_name in self.virtual_science_spw_names:
            if 'ALMA' in full_name:
                result[full_name] = full_name.rpartition('#')[0]
            else:
                result[full_name] = full_name
        return result

    @property
    def project_ids(self) -> list[str]:
        """Return unique project IDs from all measurement sets."""
        return sorted({ms.project_id for ms in self.measurement_sets if ms.project_id})

    @property
    def schedblock_ids(self) -> list[str]:
        """Return unique schedblock IDs from all measurement sets."""
        return sorted({ms.schedblock_id for ms in self.measurement_sets if ms.schedblock_id})

    @property
    def execblock_ids(self) -> list[str]:
        """Return unique execblock IDs from all measurement sets."""
        return sorted({ms.execblock_id for ms in self.measurement_sets if ms.execblock_id})

    @property
    def observers(self) -> list[str]:
        """Return unique observer names from all measurement sets."""
        return sorted({ms.observer for ms in self.measurement_sets if ms.observer})

    @property
    def start_time(self) -> EpochDict | None:
        """Return start time for the observing run as CASA 'epoch' measure dictionary."""
        if not self.measurement_sets:
            return None
        earliest_ms = min(
            self.measurement_sets,
            key=lambda ms: utils.get_epoch_as_datetime(ms.start_time) if ms.start_time else utils.get_epoch_as_datetime({'m0': {'value': 0, 'unit': 's'}, 'refer': 'UTC', 'type': 'epoch'})
        )
        return earliest_ms.start_time

    @property
    def end_time(self) -> EpochDict | None:
        """Return end time for the observing run as CASA 'epoch' measure dictionary."""
        if not self.measurement_sets:
            return None
        latest_ms = max(
            self.measurement_sets,
            key=lambda ms: utils.get_epoch_as_datetime(ms.end_time) if ms.end_time else utils.get_epoch_as_datetime({'m0': {'value': 0, 'unit': 's'}, 'refer': 'UTC', 'type': 'epoch'})
        )
        return latest_ms.end_time

    @property
    def start_datetime(self) -> datetime | None:
        """Return start datetime for the observing run."""
        if not self.measurement_sets:
            return None
        start_epoch = self.start_time
        if start_epoch is None:
            return None
        return utils.get_epoch_as_datetime(start_epoch)

    @property
    def end_datetime(self) -> datetime | None:
        """Return end datetime for the observing run."""
        if not self.measurement_sets:
            return None
        end_epoch = self.end_time
        if end_epoch is None:
            return None
        return utils.get_epoch_as_datetime(end_epoch)

    @staticmethod
    def get_real_spw_id_by_name(spw_name: str | None, target_ms: MeasurementSet) -> int | None:
        """Translate a (science) spw name to the real spw ID for a given MS.

        Args:
            spw_name: The spectral window name to convert to ID.
            target_ms: The MS for which to map name to real spectral window ID.

        Returns:
            Real spectral window ID for given spectral window name in given MS,
            or None if name was not found in the given MS.
        """
        spw_id = None
        for spw in target_ms.get_spectral_windows(science_windows_only=True):
            if match_spw_basename(spw.name, spw_name):
                if spw_id is not None:
                    eb_name = os.path.basename(target_ms.name).replace('.ms', '')
                    msg = (
                        f'Found more than one match for SPW name "{spw_name}" in '
                        f'MS "{eb_name}". Virtual SPW ID mapping might be incorrect.'
                    )
                    LOG.warning(msg)
                spw_id = spw.id
        return spw_id

    def get_virtual_spw_id_by_name(self, spw_name: str) -> int | None:
        """Translate a (science) spw name to the virtual spw ID for this pipeline run.

        Args:
            spw_name: The spectral window name to convert.

        Returns:
            Virtual spectral window ID for given name, or None if no virtual
            spw was found with given name.
        """
        return self.virtual_science_spw_names.get(spw_name, None)

    def virtual2real_spw_id(self, spw_id: int | str, target_ms: MeasurementSet) -> int | None:
        """Translate a virtual (science) spw ID to the real one for a given MS.

        Args:
            spw_id: The virtual spectral window ID (as integer or string) to convert.
            target_ms: The MS for which to map virtual spw ID to real spw ID.

        Returns:
            Real spectral window ID matching given virtual spectral ID in given
            MS. Returns None if either the given virtual spw ID does not exist
            or the given virtual spw ID does not appear in given MS.
        """
        return self.get_real_spw_id_by_name(
            self.virtual_science_spw_ids.get(int(spw_id), None), target_ms
        )

    def real2virtual_spw_id(self, spw_id: int | str, target_ms: MeasurementSet) -> int | None:
        """Translate a real (science) spw ID of a given MS to the virtual one for this pipeline run.

        Args:
            spw_id: The real spectral window ID (as integer or string) to convert.
            target_ms: The MS for which to map its real spw ID to the virtual spw ID.

        Returns:
            Virtual spectral window ID in the observing run corresponding to the
            name of the given real spectral window ID in the given MS, or None
            if the spectral window name was not found.
        """
        return self.get_virtual_spw_id_by_name(target_ms.get_spectral_window(int(spw_id)).name)

    def real2real_spw_id(self, spw_id: int | str, source_ms: MeasurementSet, target_ms: MeasurementSet) -> int | None:
        """Translate a real spectral window ID from one MS to another.

        The translation is performed via the observing run's virtual SPW ID
        mapping.

        Args:
            spw_id: Real spectral window ID from the source MS.
            source_ms: Source MS for the given real spectral window ID.
            target_ms: Target MS for which to resolve the mapped real spectral window ID.

        Returns:
            Real spectral window ID in the target MS, or None if mapping cannot
            be performed.
        """
        virtual_spw_id = self.real2virtual_spw_id(spw_id, source_ms)

        if virtual_spw_id is not None:
            return self.virtual2real_spw_id(virtual_spw_id, target_ms)

        LOG.warning(
            'Cannot map real SPW ID %s from %s to %s via a virtual SPW ID; the virtual ID for the source SPW was not found.',
            spw_id,
            source_ms.name,
            target_ms.name,
        )
        return None

    def get_real_spwsel(self, spwsel: list[str], vis: list[str]) -> list[str | None]:
        """Translate virtual science SPW selections to per-MS real SPW selections.

        Args:
            spwsel: List of virtual SPW selection strings.
            vis: List of MS names corresponding to each SPW selection.

        Returns:
            List of real SPW selection strings. Entries are None when no valid
            real SPW mapping can be derived for the given input item.
        """
        real_spwsel: list[str | None] = []

        for spwsel_item, ms_name in zip(spwsel, vis):
            real_spwsel_items: list[str] = []
            target_ms = self.get_ms(ms_name)

            for spw_item in spwsel_item.split(','):
                if ':' not in spw_item:
                    real_spw_id = self.virtual2real_spw_id(int(spw_item), target_ms)
                    if real_spw_id is not None:
                        real_spwsel_items.append(str(real_spw_id))
                else:
                    virtual_spw_id, selection = spw_item.split(':', 1)
                    real_spw_id = self.virtual2real_spw_id(int(virtual_spw_id), target_ms)
                    if real_spw_id is not None:
                        real_spwsel_items.append(f'{real_spw_id}:{selection}')

            real_spwsel.append(','.join(real_spwsel_items) if real_spwsel_items else None)

        return real_spwsel

    def add_measurement_set(self, ms: MeasurementSet) -> None:
        """Add a MeasurementSet to the ObservingRun."""
        if ms.basename in [m.basename for m in self.measurement_sets]:
            msg = f'{ms.name} is already in the pipeline context.'
            LOG.error(msg)
            raise Exception(msg)

        eb_name = os.path.basename(ms.name).replace('.ms', '')

        for spw in ms.get_spectral_windows(science_windows_only=True):
            matches = [
                name
                for name in self.virtual_science_spw_ids.values()
                if match_spw_basename(spw.name, name)
            ]

            match_count = len(matches)

            if match_count == 1:
                matched_name = matches[0]
                if spw.name != matched_name:
                    self.virtual_science_spw_names[spw.name] = (
                        self.virtual_science_spw_names[matched_name]
                    )
                    msg = (
                        f'Virtual SPW mapping: Linked the science SPW name {spw.name} (ID {spw.id}) from EB {eb_name} '
                        'to an existing virtual-ID-to-name mapping: '
                        f'{self.virtual_science_spw_names[matched_name]} - {matched_name}.'
                    )
                    LOG.info(msg)
                else:
                    msg = (
                        f'Virtual SPW mapping: Identified the science SPW name {spw.name} (ID {spw.id}) from EB {eb_name} '
                        'to a unique existing virtual-ID-to-name mapping: '
                        f'{self.virtual_science_spw_names[matched_name]} - {matched_name}.'
                    )
                    LOG.info(msg)
            elif match_count > 1:
                msg = (
                    f'Virtual SPW mapping: Found multiple matches ({match_count}) for science SPW {spw.name} (ID {spw.id}) '
                    f'from EB {eb_name} in the virtual-ID-to-name mapping. '
                    'Virtual SPW ID mapping will not work.'
                )
                LOG.error(msg)
            else:
                if spw.id not in self.virtual_science_spw_ids:
                    new_virtual_spw_id = spw.id
                    msg = (
                        f'Virtual SPW Mapping: Created new mapping for science SPW {spw.name} (ID {spw.id}) from EB {eb_name}. '
                        f'Assigned new virtual-ID-to-name mapping: {new_virtual_spw_id} - {spw.name}'
                    )
                    LOG.info(msg)
                else:
                    new_virtual_spw_id = max(self.virtual_science_spw_ids) + 1
                    msg = (
                        f'Virtual SPW ID conflict: Created new mapping for science SPW {spw.name} (ID {spw.id}) from EB {eb_name}. '
                        f"Original virtual ID {spw.id} already mapped to '{self.virtual_science_spw_ids[spw.id]}'. "
                        f'Assigned new virtual-ID-to-name mapping: {new_virtual_spw_id} - {spw.name}'
                    )
                    LOG.warning(msg)

                self.virtual_science_spw_ids[new_virtual_spw_id] = spw.name
                self.virtual_science_spw_names[spw.name] = new_virtual_spw_id

        self.measurement_sets.append(ms)
        self.measurement_sets.sort(key=sort_measurement_set)

    def get_ms(self, name: str | None = None, intent: str | None = None) -> MeasurementSet:
        """Return the first measurement set matching the given identifier."""
        if name:
            for ms in self.measurement_sets:
                if name in (ms.name, ms.basename):
                    return ms

            for ms in self.measurement_sets:
                with_suffix = f'{name}.ms'
                if with_suffix in (ms.name, ms.basename):
                    return ms

            raise KeyError('No measurement set found with name {0}'.format(name))

        if intent:
            intent = intent.replace('*', '')
            for ms in self.measurement_sets:
                for field in ms.fields:
                    if intent in field.intents:
                        return ms
            raise KeyError('No measurement set found with intent {0}'.format(intent))

        raise KeyError('No measurement set found.')

    def get_measurement_sets(
        self,
        names: str | None = None,
        intents: Iterable | str | None = None,
        fields: Iterable | str | None = None,
    ) -> list[MeasurementSet]:
        """Return measurement sets matching the given arguments."""
        candidates = self.measurement_sets

        if names is not None:
            candidates = [ms for ms in candidates if ms.name in names]

        if intents is not None:
            if isinstance(intents, str):
                intents = utils.safe_split(intents)
            intents_set = set(intents)
            candidates = [ms for ms in candidates if intents_set.issubset(ms.intents)]

        if fields is not None:
            if isinstance(fields, str):
                fields = utils.safe_split(fields)
            fields_to_match = set(fields)
            candidates = [
                ms
                for ms in candidates
                if not fields_to_match.isdisjoint({field.name for field in ms.fields})
            ]

        return candidates

    def get_measurement_sets_of_type(
        self,
        dtypes: list[DataType],
        msonly: bool = True,
        source: str | None = None,
        spw: str | None = None,
        vis: list[str] | None = None,
    ) -> list[MeasurementSet] | tuple[collections.OrderedDict, DataType | None]:
        """Return measurement sets matching the given DataType list."""
        found: list[MeasurementSet] = []
        columns: list[str] = []

        for dtype in dtypes:
            for ms in self.measurement_sets:
                if isinstance(vis, list) and ms.name not in vis:
                    continue

                if spw is not None:
                    real_spw_ids = ','.join(
                        str(self.virtual2real_spw_id(spw_id, ms))
                        for spw_id in spw.split(',')
                        if self.virtual2real_spw_id(spw_id, ms) is not None
                    )
                    if not real_spw_ids:
                        real_spw_ids = None
                else:
                    real_spw_ids = None

                datacolumn = ms.get_data_column(dtype, source, real_spw_ids)
                if datacolumn is not None:
                    found.append(ms)
                    columns.append(datacolumn)

            if found:
                break

        if found:
            LOG.debug('Found %s MSes with type %s', len(found), dtype)
        else:
            LOG.debug('No MSes are found with types %s', dtypes)

        if msonly:
            return found

        if found:
            ms_dict: collections.OrderedDict[MeasurementSet, str] = collections.OrderedDict((ms, column) for ms, column in zip(found, columns))
            return ms_dict, dtype

        return collections.OrderedDict(), None
