from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING, Any, Sequence

from pipeline.domain import measures
from pipeline.domain.datatype import DataType
from pipeline.infrastructure import utils

if TYPE_CHECKING:
    from pipeline.domain.field import Field
    from pipeline.domain.measurementset import MeasurementSet
    from pipeline.domain.spectralwindow import SpectralWindow


class SubMS:
    """Represents an atomic on-disk MeasurementSet slice/partition of a parent MeasurementSet.

    A SubMS encapsulates a data slice resulting from mstransform (e.g. per-source and/or
    per-spectral-window split). It acts as a lightweight domain object tracking slice-specific
    attributes (path, source, spectral window, DataType, frequency grid) while delegating
    common execution-block-level metadata (antennas, session, weather, scans, etc.) to the
    parent MeasurementSet.
    """

    def __init__(
        self,
        name: str,
        parent_ms: MeasurementSet,
        source_name: str | None = None,
        real_spw_id: int | None = None,
        virtual_spw_id: int | None = None,
        field_ids: Sequence[int] | None = None,
        data_type: DataType = DataType.IM_LINE_SCIENCE,
        data_column: str = 'DATA',
        freq_config: dict[str, Any] | None = None,
        base_outputvis: str | None = None,
    ) -> None:
        self.name: str = os.path.abspath(name)
        self.parent_ms: MeasurementSet = getattr(parent_ms, 'parent_ms', parent_ms)
        self.source_name: str | None = source_name
        self.real_spw_id: int | None = real_spw_id
        self.virtual_spw_id: int | None = virtual_spw_id
        self.field_ids: list[int] = list(field_ids) if field_ids is not None else []
        self.data_type: DataType = data_type
        self.data_column: dict[DataType, str] = {data_type: data_column}
        self.freq_config: dict[str, Any] = freq_config or {}
        self.base_outputvis: str | None = os.path.abspath(base_outputvis) if base_outputvis else None

    @property
    def basename(self) -> str:
        """Return the base filename of the sub-MS."""
        return os.path.basename(self.name)

    @property
    def session(self) -> str | None:
        """Delegate session name to parent MS."""
        return self.parent_ms.session

    @property
    def origin_ms(self) -> str:
        """Delegate first-generation MS name to parent MS."""
        return self.parent_ms.origin_ms

    @property
    def antennas(self) -> list[Any]:
        """Delegate antennas to parent MS."""
        return self.parent_ms.antennas

    @property
    def antenna_array(self) -> Any:
        """Delegate antenna array to parent MS."""
        return self.parent_ms.antenna_array

    @property
    def acs_software_version(self) -> str | None:
        """Delegate ACS software version to parent MS."""
        return getattr(self.parent_ms, 'acs_software_version', None)

    @property
    def acs_software_build_version(self) -> str | None:
        """Delegate ACS software build version to parent MS."""
        return getattr(self.parent_ms, 'acs_software_build_version', None)

    @property
    def filesize(self) -> measures.FileSize:
        """Calculate on-disk size of this sub-MS."""
        total_bytes = 0
        if os.path.exists(self.name):
            for dirpath, _, filenames in os.walk(self.name):
                for f in filenames:
                    total_bytes += os.path.getsize(os.path.join(dirpath, f))
        return measures.FileSize(total_bytes, measures.FileSizeUnits.BYTES)

    def get_fields(
        self,
        task_arg: int | str | None = None,
        field_id: int | Sequence[int] | None = None,
        name: str | Sequence[str] | None = None,
        intent: str | Sequence[str] | None = None,
        **kwargs: Any,
    ) -> list[Field]:
        """Return matching fields in this sub-MS slice.

        Filters parent MS fields using the slice's field_ids and source_name.
        """
        parent_fields = self.parent_ms.get_fields(task_arg=task_arg, field_id=field_id, name=name, intent=intent, **kwargs)
        if self.field_ids:
            return [f for f in parent_fields if f.id in self.field_ids]
        if self.source_name:
            return [f for f in parent_fields if getattr(f, 'source', None) and f.source.name == self.source_name]
        return parent_fields

    def get_spectral_windows(
        self,
        task_arg: int | str = '',
        with_channels: bool = False,
        num_channels: list | None = None,
        science_windows_only: bool = True,
        spectralspecs: list | None = None,
        intent: str | None = None,
        **kwargs: Any,
    ) -> list[SpectralWindow]:
        """Return spectral windows corresponding to this sub-MS slice."""
        parent_spws = self.parent_ms.get_spectral_windows(
            task_arg=task_arg,
            with_channels=with_channels,
            num_channels=num_channels,
            science_windows_only=science_windows_only,
            spectralspecs=spectralspecs,
            intent=intent,
            **kwargs,
        )
        if self.real_spw_id is not None:
            return [s for s in parent_spws if s.id == self.real_spw_id]
        return parent_spws

    @property
    def spectral_windows(self) -> list[SpectralWindow]:
        """Return spectral windows corresponding to this sub-MS slice."""
        if self.real_spw_id is not None:
            return [s for s in self.parent_ms.spectral_windows if s.id == self.real_spw_id]
        return self.parent_ms.spectral_windows

    def get_spectral_window(self, spw_id: int | str | None) -> SpectralWindow | None:
        """Return spectral window matching ID if it belongs to this slice."""
        if spw_id is None:
            return None
        try:
            spw_id_int = int(spw_id)
        except (ValueError, TypeError):
            raise KeyError(f"Invalid spectral window ID '{spw_id}' in {self.basename}")
        if self.real_spw_id is not None and spw_id_int != self.real_spw_id:
            raise KeyError(f"No spectral window with ID '{spw_id}' found in {self.basename}")
        return self.parent_ms.get_spectral_window(spw_id_int)

    def get_data_column(self, dtype: DataType, source: str | None = None, spw: str | None = None) -> str | None:
        """Return data column name for given DataType."""
        if source is not None and self.source_name is not None and source != self.source_name:
            return None
        if spw is not None and self.real_spw_id is not None:
            try:
                spw_ids = set(utils.range_to_list(str(spw)))
            except Exception:
                spw_ids = {int(s) for s in str(spw).split(',') if s.strip().isdigit()}
            if self.real_spw_id not in spw_ids:
                return None
        return self.data_column.get(dtype)

    def get_data_type(self, column: str, source: str | None = None, spw: str | None = None) -> DataType | None:
        """Return DataType associated with column name."""
        if source is not None and self.source_name is not None and source != self.source_name:
            return None
        if spw is not None and self.real_spw_id is not None:
            try:
                spw_ids = set(utils.range_to_list(str(spw)))
            except Exception:
                spw_ids = {int(s) for s in str(spw).split(',') if s.strip().isdigit()}
            if self.real_spw_id not in spw_ids:
                return None
        for dt, col in self.data_column.items():
            if col == column:
                return dt
        return None

    def set_data_column(self, dtype: DataType, column: str) -> None:
        """Update data column mapping."""
        self.data_type = dtype
        self.data_column[dtype] = column

    def get_vis(self, *args: Any, **kwargs: Any) -> str:
        """Return on-disk path to this sub-MS."""
        return self.name

    def get_subms_path(self, *args: Any, **kwargs: Any) -> str:
        """Return on-disk path to this sub-MS."""
        return self.name

    def get_subms_paths(self, *args: Any, **kwargs: Any) -> list[str]:
        """Return list containing this sub-MS path."""
        return [self.name]

    def has_subms(self, *args: Any, **kwargs: Any) -> bool:
        """A SubMS is an atomic slice and contains no child SubMSes."""
        return False

    def get_subms(self, *args: Any, **kwargs: Any) -> list[SubMS]:
        """Return self as the matching SubMS slice."""
        return [self]

    def matches_field(self, field: int | str) -> bool:
        """Check if a given field ID or field/source name matches this slice.

        Args:
            field: Field ID (as int or str) or field/source name string.

        Returns:
            True if the field belongs to this slice.
        """
        f_str = str(field).strip()
        if self.source_name and f_str == self.source_name:
            return True
        if self.field_ids and f_str.isdigit() and int(f_str) in self.field_ids:
            return True
        if hasattr(self, 'get_fields'):
            try:
                for f in self.get_fields():
                    if str(f.id) == f_str or f.name == f_str:
                        return True
            except Exception:
                pass
        return False

    def matches_spw(self, spw: int | str) -> bool:
        """Check if a given real or virtual SPW ID matches this slice.

        Args:
            spw: SPW ID (as int or str).

        Returns:
            True if the SPW ID corresponds to this slice.
        """
        if self.real_spw_id is None and self.virtual_spw_id is None:
            return True
        s_str = str(spw).strip()
        if not s_str.isdigit():
            return False
        s_int = int(s_str)
        matched_ids = {s for s in (self.real_spw_id, self.virtual_spw_id) if s is not None}
        return s_int in matched_ids

    def to_local_spw(self, spw: int | str | None = None) -> str:
        """Convert a parent real or virtual SPW ID to the local on-disk SPW ID in this slice.

        Since mstransform operates with reindex=False, the on-disk SPW ID in the
        SubMS slice preserves the original real_spw_id.

        Args:
            spw: Optional parent SPW ID (real or virtual).

        Returns:
            Local on-disk SPW ID string (str(self.real_spw_id) if set, else str(spw)).
        """
        if self.real_spw_id is not None:
            return str(self.real_spw_id)
        return '' if spw is None else str(spw)

    def derive_outputvis(self, suffix: str = '_line') -> str:
        """Derive an output SubMS path by inserting suffix before partition tokens.

        For example:
            'uid___A002_X123_targets.helms30.spw0.ms' with suffix '_line' ->
            'uid___A002_X123_targets_line.helms30.spw0.ms'

        Args:
            suffix: Suffix to insert (e.g. '_line', '_selfcal').

        Returns:
            Modified SubMS path string.
        """
        norm_suffix = suffix if suffix.startswith('_') else f'_{suffix}'
        name = self.name
        if '_targets' in name:
            return name.replace('_targets', f'_targets{norm_suffix}', 1)
        elif '_imaging' in name:
            return name.replace('_imaging', f'_imaging{norm_suffix}', 1)
        elif norm_suffix in name:
            return name
        else:
            m = re.search(r'(\.[^.]+\.spw\d+\.ms|\.spw\d+\.ms|\.[^.]+\.ms|\.ms)$', name)
            if m:
                idx = m.start(1)
                return f'{name[:idx]}{norm_suffix}{name[idx:]}'
            return f'{name.split(".ms")[0]}{norm_suffix}.ms'

    def __getattr__(self, name: str) -> Any:
        """Delegate unhandled attribute lookups to parent MeasurementSet."""
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        if 'parent_ms' not in self.__dict__:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        parent = self.__dict__['parent_ms']
        if parent is None or parent is self:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        return getattr(parent, name)

    def __getstate__(self) -> dict[str, Any]:
        """Support pickle serialization."""
        return self.__dict__

    def __setstate__(self, state: dict[str, Any]) -> None:
        """Support pickle deserialization."""
        self.__dict__.update(state)

    def __str__(self) -> str:
        parent_name = getattr(self.parent_ms, 'basename', str(self.parent_ms))
        return f"SubMS({self.basename}, parent={parent_name}, source={self.source_name}, spw={self.real_spw_id})"

    def __repr__(self) -> str:
        parent_name = getattr(self.parent_ms, 'basename', str(self.parent_ms))
        return f"SubMS(name='{self.name}', parent='{parent_name}', source='{self.source_name}', spw={self.real_spw_id})"

