"""Pydantic-based single-dish domain objects."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field as PydanticField

from pipeline import infrastructure
from pipeline.domain.spectralwindow import match_spw_basename


LOG = infrastructure.logging.get_logger(__name__)


class MSReductionGroupMember(BaseModel):
    """Pydantic model for single-dish measurement set reduction group member.

    Represents a single member of a reduction group, identified by measurement
    set, antenna, spectral window, and field.
    """

    ms: Any = PydanticField(..., description='MeasurementSet object')
    antenna_id: int = PydanticField(..., description='Antenna ID')
    spw_id: int = PydanticField(..., description='Spectral window ID')
    field_id: int = PydanticField(default=-1, description='Field ID (default -1 if unspecified)')
    iteration: int = PydanticField(default=0, description='Iteration counter')
    linelist: list[Any] = PydanticField(default_factory=list, description='Line list')
    channelmap_range: list[Any] = PydanticField(default_factory=list, description='Channel map range')

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_default=True)

    def __hash__(self) -> int:
        return hash((self.__class__, id(self.ms), self.antenna_id, self.spw_id, self.field_id))

    @property
    def npol(self) -> int:
        """Return the number of polarizations (always 1 for single-dish)."""
        return 1

    @property
    def spw(self) -> Any:
        """Return the spectral window object."""
        return self.ms.spectral_windows[self.spw_id]

    @property
    def antenna(self) -> Any:
        """Return the antenna object."""
        return self.ms.antennas[self.antenna_id]

    @property
    def antenna_name(self) -> str:
        """Return the antenna name."""
        return self.antenna.name

    @property
    def field(self) -> Any:
        """Return the field object."""
        return self.ms.fields[self.field_id]

    @property
    def field_name(self) -> str:
        """Return the field name."""
        return self.field.name

    def iter_countup(self) -> None:
        """Increment the iteration counter."""
        self.iteration += 1

    def iter_reset(self) -> None:
        """Reset the iteration counter to zero."""
        self.iteration = 0

    def add_linelist(self, linelist: list[Any], pols: list[Any] | None = None,
                     channelmap_range: list[Any] | None = None) -> None:
        """Add a line list to this member.

        Args:
            linelist: Line list to add.
            pols: Polarizations (unused in current implementation).
            channelmap_range: Channel map range. If None, uses linelist.
        """
        self.linelist = linelist
        if channelmap_range is not None:
            self.channelmap_range = channelmap_range
        else:
            self.channelmap_range = linelist

    def __repr__(self) -> str:
        """Return string representation of this member."""
        return (
            f'MSReductionGroupMember(ms=\'{self.ms.basename}\', antenna={self.antenna_id}, '
            f'spw={self.spw_id}, field_id={self.field_id})'
        )

    def __eq__(self, other: object) -> bool:
        """Check equality based on MS name and component IDs."""
        if not isinstance(other, MSReductionGroupMember):
            return False
        return (
            other.ms.name == self.ms.name
            and other.antenna_id == self.antenna_id
            and other.spw_id == self.spw_id
            and other.field_id == self.field_id
        )

    def __ne__(self, other: object) -> bool:
        """Check inequality based on MS name and component IDs."""
        if not isinstance(other, MSReductionGroupMember):
            return True
        return not self.__eq__(other)

    def __hash__(self) -> int:
        """Return hash for use in sets/dicts."""
        return hash((self.ms.name, self.antenna_id, self.spw_id, self.field_id))


class MSReductionGroupDesc(BaseModel):
    """Pydantic model for single-dish measurement set reduction group descriptor.

    Organizes reduction group members with spectral window and field metadata.
    Provides list-like operations for managing members.
    """

    spw_name: str | None = PydanticField(default=None, description='Spectral window name')
    min_frequency: float | None = PydanticField(default=None, description='Minimum frequency')
    max_frequency: float | None = PydanticField(default=None, description='Maximum frequency')
    nchan: int | None = PydanticField(default=None, description='Number of channels')
    field: Any = PydanticField(default=None, description='Field object')
    members: list[MSReductionGroupMember] = PydanticField(
        default_factory=list, description='List of reduction group members'
    )

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_default=True)

    def __hash__(self) -> int:
        field_id = self.field.id if self.field is not None else 0
        return hash((self.__class__, self.spw_name or '', field_id))

    @property
    def frequency_range(self) -> list[float | None]:
        """Return the frequency range as [min_frequency, max_frequency]."""
        return [self.min_frequency, self.max_frequency]

    @property
    def field_name(self) -> str | None:
        """Return the field name (stripped of quotes)."""
        if self.field is None:
            return None
        field_name = self.field.name
        if isinstance(field_name, str):
            return field_name.strip('"')
        return None

    def merge(self, other: MSReductionGroupDesc) -> None:
        """Merge another reduction group into this one.

        Args:
            other: Another MSReductionGroupDesc to merge.

        Raises:
            AssertionError if the groups are not equal.
        """
        assert self == other
        for member in other.members:
            LOG.trace(
                'ms.name="%s" antenna=%s spw=%s, field_id=%s',
                member.ms.name,
                member.antenna_id,
                member.spw_id,
                member.field_id,
            )
            if member not in self.members:
                LOG.debug(
                    'Adding (%s, %s, %s, %s)',
                    member.ms.name,
                    member.antenna_id,
                    member.spw_id,
                    member.field_id,
                )
                self.members.append(member)

    def add_member(self, ms: Any, antenna_id: int, spw_id: int,
                   field_id: int | None = None) -> None:
        """Add a new member to this reduction group.

        Args:
            ms: MeasurementSet object.
            antenna_id: Antenna ID.
            spw_id: Spectral window ID.
            field_id: Field ID (default None, which becomes -1).
        """
        new_member = MSReductionGroupMember(
            ms=ms, antenna_id=antenna_id, spw_id=spw_id, field_id=field_id
        )
        if new_member not in self.members:
            self.members.append(new_member)

    def get_iteration(self, ms: Any, antenna_id: int, spw_id: int,
                      field_id: int | None = None) -> int:
        """Get the iteration count for a specific member.

        Args:
            ms: MeasurementSet object.
            antenna_id: Antenna ID.
            spw_id: Spectral window ID.
            field_id: Field ID.

        Returns:
            Iteration count for the member.
        """
        member = self.members[self._search_member(ms, antenna_id, spw_id, field_id)]
        return member.iteration

    def iter_countup(self, ms: Any, antenna_id: int, spw_id: int,
                     field_id: int | None = None) -> None:
        """Increment iteration counter for a specific member.

        Args:
            ms: MeasurementSet object.
            antenna_id: Antenna ID.
            spw_id: Spectral window ID.
            field_id: Field ID.
        """
        member = self.members[self._search_member(ms, antenna_id, spw_id, field_id)]
        member.iter_countup()

    def add_linelist(self, linelist: list[Any], ms: Any, antenna_id: int, spw_id: int,
                     field_id: int | None = None, channelmap_range: list[Any] | None = None) -> None:
        """Add a line list to a specific member.

        Args:
            linelist: Line list to add.
            ms: MeasurementSet object.
            antenna_id: Antenna ID.
            spw_id: Spectral window ID.
            field_id: Field ID.
            channelmap_range: Channel map range (optional).
        """
        member = self.members[self._search_member(ms, antenna_id, spw_id, field_id)]
        member.add_linelist(linelist, channelmap_range=channelmap_range)

    def _search_member(self, ms: Any, antenna_id: int, spw_id: int,
                       field_id: int | None = None) -> int:
        """Search for a member by MS and component IDs.

        Args:
            ms: MeasurementSet object.
            antenna_id: Antenna ID.
            spw_id: Spectral window ID.
            field_id: Field ID (default -1 if None).

        Returns:
            Index of the member in the members list.
        """
        if field_id is None:
            field_id = -1
        for indx, member in enumerate(self.members):
            if (
                member.ms.name == ms.name
                and member.antenna_id == antenna_id
                and member.spw_id == spw_id
                and member.field_id == field_id
            ):
                return indx
        raise ValueError(
            f'Member not found: ms={ms.name}, antenna={antenna_id}, '
            f'spw={spw_id}, field={field_id}'
        )

    def __eq__(self, other: object) -> bool:
        """Check equality based on frequency/field or spw_name/field.

        If both have valid spw_names, compare using spw_name matching.
        Otherwise, compare using frequency and field properties.
        """
        if not isinstance(other, MSReductionGroupDesc):
            return False

        # Check if both have valid spw_names
        self_has_spw = isinstance(self.spw_name, str) and len(self.spw_name) > 0
        other_has_spw = isinstance(other.spw_name, str) and len(other.spw_name) > 0

        if self_has_spw and other_has_spw:
            # Both have valid spw_names, use spw_name matching
            return (
                match_spw_basename(self.spw_name, other.spw_name)
                and self.field_name == other.field_name
            )
        else:
            # One or both don't have spw_names, use frequency-based comparison
            return (
                self.max_frequency == other.max_frequency
                and self.min_frequency == other.min_frequency
                and self.nchan == other.nchan
                and self.field_name == other.field_name
            )

    def __ne__(self, other: object) -> bool:
        """Check inequality."""
        if not isinstance(other, MSReductionGroupDesc):
            return True
        return not self.__eq__(other)

    def __repr__(self) -> str:
        """Return string representation."""
        if (not isinstance(self.spw_name, str)) or len(self.spw_name or '') == 0:
            return (
                f'MSReductionGroupDesc(frequency_range={self.frequency_range}, '
                f'nchan={self.nchan}, field=\'{self.field_name}\', '
                f'member={self.members})'
            )
        else:
            return (
                f'MSReductionGroupDesc(spw_name={self.spw_name}, '
                f'frequency_range={self.frequency_range}, nchan={self.nchan}, '
                f'field=\'{self.field_name}\', member={self.members})'
            )

    # List-like operations for backward compatibility
    def __getitem__(self, index: int) -> MSReductionGroupMember:
        """Get a member by index."""
        return self.members[index]

    def __setitem__(self, index: int, value: MSReductionGroupMember) -> None:
        """Set a member by index."""
        self.members[index] = value

    def __len__(self) -> int:
        """Return the number of members."""
        return len(self.members)

    def __iter__(self) -> Any:
        """Iterate over members."""
        return iter(self.members)

    def __contains__(self, item: MSReductionGroupMember) -> bool:
        """Check if a member is in the list."""
        return item in self.members

    def append(self, item: MSReductionGroupMember) -> None:
        """Append a member to the list."""
        self.members.append(item)
