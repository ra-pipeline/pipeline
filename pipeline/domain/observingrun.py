# Do not evaluate type annotations at definition time.
from __future__ import annotations

import collections
import itertools
import operator
import os
from typing import TYPE_CHECKING, Iterable

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.utils as utils

from .datatype import TYPE_PRIORITY_ORDER, DataType
from .spectralwindow import match_spw_basename

if TYPE_CHECKING:
    from datetime import datetime
    from . import MeasurementSet

LOG = infrastructure.get_logger(__name__)


def sort_measurement_set(ms: MeasurementSet) -> tuple[int, datetime]:
    """Return sort key for measurement set object.

    Sort key consists of data priority and observation start time.
    Data priority is determined from the data types of given
    measurement set. Sort order of the data types is defined in
    DATA_TYPE_PRIORITY list. If no DataType is set to the MS,
    the lowest priority is assigned to the MS.

    Returns:
        Data priority and observation start time
    """
    data_types = set(itertools.chain(*ms.data_types_per_source_and_spw.values()))
    assert all([t in TYPE_PRIORITY_ORDER for t in data_types])
    if len(data_types) > 0:
        data_priority = max([TYPE_PRIORITY_ORDER.index(t) for t in data_types])
    else:
        # no data type assignments, assign lowest priority (largest value)
        data_priority = len(TYPE_PRIORITY_ORDER)
    observation_start_time = utils.get_epoch_as_datetime(ms.start_time)
    return data_priority, observation_start_time


class ObservingRun(object):
    """A logical representation of an observing run.

    Attributes:
        measurement_sets: List of measurementSet objects associated with run.
        ms_datatable_name: Path to directory that stores DataTable of each
            MeasurementSet (Single-Dish only).
        ms_reduction_group: Dictionary of reduction groups (Single-Dish only).
        org_directions: Dictionary with Direction objects of the origin
            (Single-Dish only).
        virtual_science_spw_ids: Dictionary mapping each virtual science
            spectral window ID (key) to corresponding science spectral window
            name (value) that first appears in the imported measurement sets.
        virtual_science_spw_names: Dictionary mapping each science spectral
            window name (key) to corresponding virtual spectral window ID (value).
            Multiple SPW names may map to the same virtual spw ID.
        virtual_science_spw_shortnames: Property returning a dictionary mapping
            each science spectral window name to its shortened version.
    """

    def __init__(self) -> None:
        """Initialize an ObservingRun object."""
        self.measurement_sets: list[MeasurementSet] = []
        self.ms_datatable_name = ''
        self.ms_reduction_group = {}
        self.org_directions = {}
        self.virtual_science_spw_ids: dict[int, str] = {}  # PIPE-59/PIPE-123
        self.virtual_science_spw_names: dict[str, int] = {}  # PIPE-59/PIPE-123

    @property
    def virtual_science_spw_shortnames(self) -> dict[str, str]:
        """Generate SPW shortnames derived from full SPW names.

        If the name contains 'ALMA', it attempts to remove any suffix starting
        from the last '#' character. Otherwise, the name is returned unchanged.
        This was originally implemented from PIPE-59/PIPE-123.

        Returns:
            Dictionary mapping full SPW names to their shortened versions.
        """
        result = {}
        for full_name in self.virtual_science_spw_names:
            if 'ALMA' in full_name:
                result[full_name] = full_name.rpartition('#')[0]
            else:
                result[full_name] = full_name
        return result

    def add_measurement_set(self, ms: MeasurementSet) -> None:
        """Add a MeasurementSet to the ObservingRun."""
        if ms.basename in [m.basename for m in self.measurement_sets]:
            msg = f'{ms.name} is already in the pipeline context.'
            LOG.error(msg)
            raise Exception(msg)

        eb_name = os.path.basename(ms.name).replace('.ms', '')

        for s in ms.get_spectral_windows(science_windows_only=True):
            # Find all close-matching SPW names from the virtual-id->spw-name mapping table
            # PIPE-2616: match shared ending substrings to accommodate SPW naming convention
            # changes introduced in ALMA Cycle-12 with additional group ID tags.
            matches = [name for name in self.virtual_science_spw_ids.values() if match_spw_basename(s.name, name)]

            match_count = len(matches)

            if match_count == 1:
                # Exactly one close match found
                matched_name = matches[0]
                if s.name != matched_name:
                    # conditionally Link another new spw name to a pre-existing virtual spw ID, in cases SPW name
                    # slightly changed, e.g. cycle2->3 or cycle11->13 naming convention changes.
                    self.virtual_science_spw_names[s.name] = self.virtual_science_spw_names[matched_name]
                    msg = (
                        f'Virtual SPW mapping: Linked the science SPW name {s.name} (ID {s.id}) from EB {eb_name} to '
                        f'an existing virtual-ID-to-name mapping: {self.virtual_science_spw_names[matched_name]} - {matched_name}.'
                    )
                    LOG.info(msg)
                else:
                    msg = (
                        f'Virtual SPW mapping: Identified the science SPW name {s.name} (ID {s.id}) from EB {eb_name} to '
                        f'a unique existing virtual-ID-to-name mapping: {self.virtual_science_spw_names[matched_name]} - {matched_name}.'
                    )
                    LOG.info(msg)
            elif match_count > 1:
                # Multiple matches found - unlikely situation - log error
                msg = (
                    f'Virtual SPW mapping: Found multiple matches ({match_count}) for science SPW {s.name} (ID {s.id}) from EB {eb_name} '
                    'in the virtual-ID-to-name mapping. Virtual SPW ID mapping will not work.'
                )
                LOG.error(msg)
            else:
                # No match found
                if s.id not in self.virtual_science_spw_ids:
                    # No ID conflict - safe to add the virtual spw entry using real ID / spw name
                    new_virtual_spw_id = s.id
                    msg = (
                        f'Virtual SPW Mapping: Created new mapping for science SPW {s.name} (ID {s.id}) from EB {eb_name}. '
                        f'Assigned new virtual-ID-to-name mapping: {new_virtual_spw_id} - {s.name}'
                    )
                    LOG.info(msg)
                else:
                    # ID conflict - log warning / apply spw id offset - proceed with cautions
                    new_virtual_spw_id = max(self.virtual_science_spw_ids) + 1
                    msg = (
                        f'Virtual SPW ID conflict: Created new mapping for science SPW {s.name} (ID {s.id}) from EB {eb_name}. '
                        f"Original virtual ID {s.id} already mapped to '{self.virtual_science_spw_ids[s.id]}'. "
                        f'Assigned new virtual-ID-to-name mapping: {new_virtual_spw_id} - {s.name}'
                    )
                    LOG.warning(msg)
                # Create new virtual SPW entry
                self.virtual_science_spw_ids[new_virtual_spw_id] = s.name
                self.virtual_science_spw_names[s.name] = new_virtual_spw_id

        self.measurement_sets.append(ms)
        self.measurement_sets.sort(key=sort_measurement_set)

    def get_ms(self, name: str = None, intent: str = None) -> MeasurementSet:
        """Returns the first measurement set matching the given identifier.

        Identifier precedence is name then intent.

        Args:
            name: Name to find matching measurement set for.
            intent: Intent to find matching measurement set for.

        Returns:
            MeasurementSet object for first match found.

        Raises:
            KeyError, if no measurement set is found for given name or intent.
        """
        if name:
            for ms in self.measurement_sets:
                if name in (ms.name, ms.basename):
                    return ms

            for ms in self.measurement_sets:
                # single dish data are registered without the MS suffix
                with_suffix = '%s.ms' % name
                if with_suffix in (ms.name, ms.basename):
                    return ms

            raise KeyError('No measurement set found with name {0}'.format(name))

        if intent:
            # Remove any extraneous characters, as intent could be specified
            # as *BANDPASS* for example
            intent = intent.replace('*', '')
            for ms in self.measurement_sets:
                for field in ms.fields:
                    if intent in field.intents:
                        return ms
            raise KeyError('No measurement set found with intent {0}'.format(intent))

    def get_measurement_sets(self, names: str | None = None, intents: Iterable | str | None = None,
                             fields: Iterable | str | None = None) -> list[MeasurementSet]:
        """Returns measurement sets matching the given arguments.

        Args:
            names: Name(s) to find matching measurement set(s) for.
            intents: Intent(s) to find matching measurement set(s) for.
            fields: Field name(s) to find matching measurement set(s) for.

        Returns:
            List of MeasurementSet objects for measurement sets matching given
            arguments.
        """
        candidates = self.measurement_sets

        # filter out MeasurementSets with no vis hits
        if names is not None:
            candidates = [ms for ms in candidates
                          if ms.name in names]

        # filter out MeasurementSets with no intent hits
        if intents is not None:
            if isinstance(intents, str):
                intents = utils.safe_split(intents)
            intents = set(intents)

            candidates = [ms for ms in candidates
                          if intents.issubset(ms.intents)]

        # filter out MeasurementSets with no field name hits
        if fields is not None:
            if isinstance(fields, str):
                fields = utils.safe_split(fields)
            fields_to_match = set(fields)

            candidates = [ms for ms in candidates
                          if not fields_to_match.isdisjoint({field.name for field in ms.fields})]

        return candidates

    def get_measurement_sets_of_type(self, dtypes: list[DataType], msonly: bool = True, source: str | None = None,
                                     spw: str | None = None, vis: list[str] | None = None) \
            -> list[MeasurementSet] | tuple[collections.OrderedDict, DataType | None]:
        """Return a list of MeasurementSet domain object with matching DataType.

        The method returns a list of MSes of the first matching DataType in the
        list of dtypes.

        Args:
            dtypes: Search order of DataType. The search starts with the
                first DataType in the list and fallbacks to another DataType
                in the list only if no MS is found with the searched DataType.
                The search order of DataType is in the order of elements in
                list. Search stops at the first DataType with which at least
                one MS is found.
            msonly: If True, return a list of MS domain object only.
            source: Filter for particular source name selection (comma
                separated list of names).
            spw: Filter for particular virtual spw specification (comma
                separated list of virtual IDs).
            vis: Filter for list of MS names (list of strings)

        Returns:
            When msonly is True, a list of MeasurementSet domain objects of
            a matching DataType (and optionally sources and spws) is returned.
            Otherwise, a tuple of an ordered dictionary and a matched DataType
            (and optionally sources and spws) is returned. The ordered
            dictionary stores matching MS domain objects as keys and matching
            data column names as values. The order of elements is that appears
            in measurement_sets list attribute.
        """
        found = []
        column = []
        for dtype in dtypes:
            for ms in self.measurement_sets:
                # Filter for vis list
                if isinstance(vis, list):
                    if ms.name not in vis:
                        continue
                if spw is not None:
                    real_spw_ids = ','.join(str(self.virtual2real_spw_id(spw_id, ms)) for spw_id in spw.split(',') if self.virtual2real_spw_id(spw_id, ms) is not None)
                    if not real_spw_ids:
                        real_spw_ids = None
                else:
                    real_spw_ids = None
                dcol = ms.get_data_column(dtype, source, real_spw_ids)
                if dcol is not None:
                    found.append(ms)
                    column.append(dcol)
            if len(found) > 0:
                break
        if len(found) > 0:
            LOG.debug('Found {} MSes with type {}'.format(len(found), dtype))
        else:
            LOG.debug('No MSes are found with types {}'.format(dtypes))
        if msonly:
            return found
        else:
            if len(found) > 0:
                ms_dict = collections.OrderedDict( (m, c) for m, c in zip(found, column))
                return ms_dict, dtype
            else:
                return collections.OrderedDict(), None

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
        spw_name = self.virtual_science_spw_ids.get(int(spw_id), None)
        if spw_name:
            return self.get_real_spw_id_by_name(spw_name, target_ms)
        else:
            LOG.warning('Virtual SPW ID %s not found in the virtual SPW mapping table.', spw_id)
            return None

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
        """Translates a real spectral window (SPW) ID from one MS to another.

        The translation is done via via the pipeline's virtual SPW ID mapping.

        Args:
            spw_id: The real spectral window ID to translate. Can be an integer or a string.
            source_ms: The source MeasurementSet from which the SPW ID originates.
            target_ms: The target MeasurementSet to which the SPW ID should be mapped.

        Returns:
            The corresponding real SPW ID in the target MS, or None if the mapping
            could not be performed (e.g., if the virtual SPW ID was not found for the source SPW).
        """
        # Obtain the virtual SPW ID from the source MeasurementSet
        virtual_spw_id = self.real2virtual_spw_id(spw_id, source_ms)

        # If a virtual SPW ID was successfully found, map it to the target MS
        if virtual_spw_id is not None:
            return self.virtual2real_spw_id(virtual_spw_id, target_ms)
        else:
            LOG.warning(
                'Cannot map real SPW ID %s from %s to %s via a virtual SPW ID; '
                'the virtual ID for the source SPW was not found.',
                spw_id,
                source_ms.name,
                target_ms.name,
            )
            return None

    def get_real_spwsel(self, spwsel: list[str], vis: list[str]) -> list[str | None]:
        """Translate a virtual (science) spw selection to the real one for a given MS.

        Args:
            spwsel: The list of spw selections to convert.
            vis: The list of MS names for which to convert the virtual spw selection to a real spw selection.

        Returns:
            List of real spw selections for given virtual spw selections and MS names. Returns None for 
            entries where no valid real spw mappings are found.
        """
        real_spwsel: list[str | None] = []

        for spwsel_item, ms_name in zip(spwsel, vis):
            real_spwsel_items: list[str] = []

            for spw_item in spwsel_item.split(','):
                if ':' not in spw_item:
                    # Handle simple spw ID without channel selection
                    real_spw_id = self.virtual2real_spw_id(int(spw_item), self.get_ms(ms_name))
                    if real_spw_id is not None:
                        real_spwsel_items.append(str(real_spw_id))
                else:
                    # Handle spw ID with channel selection (format: spw:channels)
                    virtual_spw_id, selection = spw_item.split(':', 1)
                    real_spw_id = self.virtual2real_spw_id(int(virtual_spw_id), self.get_ms(ms_name))
                    if real_spw_id is not None:
                        real_spwsel_items.append(f'{real_spw_id}:{selection}')

            # Add comma-separated real spw selection or None if no valid mappings found
            real_spwsel.append(','.join(real_spwsel_items) if real_spwsel_items else None)

        return real_spwsel

    @property
    def start_time(self) -> dict | None:
        """Return start time of earliest measurement set in this observing run.

        Returns earliest MS start time as a CASA 'epoch' measure dictionary, or
        None if there are no measurement sets registered in this observing run.
        """
        if not self.measurement_sets:
            return None
        earliest, _ = min([(ms, utils.get_epoch_as_datetime(ms.start_time)) for ms in self.measurement_sets],
                          key=operator.itemgetter(1))
        return earliest.start_time

    @property
    def start_datetime(self) -> datetime | None:
        """Return start date and time of earliest measurement set in this observing run.

        Returns earliest MS start time as a datetime object, or None if there
        are no measurement sets registered in this observing run.
        """
        if not self.start_time:
            return None
        return utils.get_epoch_as_datetime(self.start_time)

    @property
    def end_time(self) -> dict | None:
        """Return end time of latest measurement set in this observing run.

        Returns latest MS end time as a CASA 'epoch' measure dictionary, or
        None if there are no measurement sets registered in this observing run.
        """
        if not self.measurement_sets:
            return None
        latest, _ = max([(ms, utils.get_epoch_as_datetime(ms.end_time)) for ms in self.measurement_sets],
                        key=operator.itemgetter(1))
        return latest.end_time

    @property
    def end_datetime(self) -> datetime | None:
        """Return end date and time of latest measurement set in this observing run.

        Returns latest MS end time as a datetime object, or None if there
        are no measurement sets registered in this observing run.
        """
        if not self.end_time:
            return None
        return utils.get_epoch_as_datetime(self.end_time)

    @property
    def project_ids(self) -> set[str]:
        """Return unique project ID(s) associated with the MSes in this observing run."""
        return {ms.project_id for ms in self.measurement_sets}

    @property
    def schedblock_ids(self) -> set[str]:
        """Return unique scheduling block ID(s) associated with the MSes in this observing run."""
        return {ms.schedblock_id for ms in self.measurement_sets}

    @property
    def execblock_ids(self) -> set[str]:
        """Return unique execution block ID(s) associated with the MSes in this observing run."""
        return {ms.execblock_id for ms in self.measurement_sets}

    @property
    def observers(self) -> set[str]:
        """Return unique observer(s) associated with the MSes in this observing run."""
        return {ms.observer for ms in self.measurement_sets}
