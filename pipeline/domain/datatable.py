"""Pydantic-based DataTable implementation for Phase 5 modernization (full port)."""

from __future__ import annotations

import bisect
import collections
import os
import re
import time
from typing import Any, ClassVar

import numpy as np
from pydantic import BaseModel, ConfigDict, Field as PydanticField

import pipeline.infrastructure as infrastructure
from pipeline.infrastructure import casa_tools
from pipeline.infrastructure.utils import absolute_path, list_to_str

LOG = infrastructure.logging.get_logger(__name__)


def __coldesc(vtype: str, option: int, maxlen: int, ndim: int, comment: str, unit: str | None = None) -> dict:
    desc = {
        'dataManagerGroup': 'StandardStMan',
        'dataManagerType': 'StandardStMan',
        'valueType': vtype,
        'option': option,
        'maxlen': maxlen,
        'comment': comment,
    }
    if ndim > 0:
        desc['ndim'] = ndim
    if unit is not None:
        desc['keywords'] = {'UNIT': unit}
    return desc


# Description for data table columns as dictionary.
# Each value is a tuple containing:
#
#    (valueType,option,maxlen,ndim,comment[,unit])
#
# dataManagerGroup and dataManagerType is always 'StandardStMan'.
#
# 2018/07/31 HE : added SHIFT_RA, SHIFT_DEC for CAS-11674
# 2019/05/23 HE : added OFS_RA, OFS_DEC for PIPE-220
def __tabledescro() -> dict:
    td_desc_ro = [
        __coldesc('integer', 0, 0, -1, 'Row number'),
        __coldesc('integer', 0, 0, -1, 'Scan number'),
        __coldesc('integer', 0, 0, -1, 'IF number'),
        __coldesc('integer', 0, 0, -1, 'Number of Polarizations'),
        __coldesc('integer', 0, 0, -1, 'Beam number'),
        __coldesc('string', 0, 0, -1, 'Date'),
        __coldesc('double', 0, 0, -1, 'Time in MJD', 'd'),
        __coldesc('double', 0, 0, -1, 'Elapsed time since first scan' 'd'),
        __coldesc('double', 0, 0, -1, 'Exposure time', 's'),
        __coldesc('double', 0, 0, -1, 'Right Ascension', 'deg'),
        __coldesc('double', 0, 0, -1, 'Declination', 'deg'),
        __coldesc('double', 0, 0, -1, 'Shifted Right Ascension', 'deg'),
        __coldesc('double', 0, 0, -1, 'Shifted Declination', 'deg'),
        __coldesc('double', 0, 0, -1, 'Offset Right Ascension', 'deg'),
        __coldesc('double', 0, 0, -1, 'Offset Declination', 'deg'),
        __coldesc('double', 0, 0, -1, 'Azimuth', 'deg'),
        __coldesc('double', 0, 0, -1, 'Elevation', 'deg'),
        __coldesc('integer', 0, 0, -1, 'Number of channels'),
        __coldesc('double', 0, 0, 1, 'Tsys', 'K'),
        __coldesc('string', 0, 0, -1, 'Target name'),
        __coldesc('integer', 0, 0, -1, 'Antenna index'),
        __coldesc('integer', 0, 0, -1, 'Source type enum'),
        __coldesc('integer', 0, 0, -1, 'Field ID'),
    ]

    name = [
        'ROW',
        'SCAN',
        'IF',
        'NPOL',
        'BEAM',
        'DATE',
        'TIME',
        'ELAPSED',
        'EXPOSURE',
        'RA',
        'DEC',
        'SHIFT_RA',
        'SHIFT_DEC',
        'OFS_RA',
        'OFS_DEC',
        'AZ',
        'EL',
        'NCHAN',
        'TSYS',
        'TARGET',
        'ANTENNA',
        'SRCTYPE',
        'FIELD_ID',
    ]
    return dict(zip(name, td_desc_ro))


def __tabledescrw() -> dict:
    td_desc_rw = [
        __coldesc('double', 0, 0, 2, 'Statistics'),
        __coldesc('integer', 0, 0, 2, 'Flgas'),
        __coldesc('integer', 0, 0, 2, 'Permanent flags'),
        __coldesc('integer', 0, 0, 1, 'Actual flag'),
        __coldesc('integer', 0, 0, -1, 'Number of mask regions'),
        __coldesc('integer', 0, 0, 2, 'List of mask ranges'),
        __coldesc('integer', 0, 0, -1, 'Unchanged row or not'),
        __coldesc('integer', 0, 0, -1, 'Position group id'),
    ]

    name = [
        'STATISTICS',
        'FLAG',
        'FLAG_PERMANENT',
        'FLAG_SUMMARY',
        'NMASK',
        'MASKLIST',
        'NOCHANGE',
        'POSGRP',
    ]
    return dict(zip(name, td_desc_rw))


TABLEDESC_RO = __tabledescro()
TABLEDESC_RW = __tabledescrw()


def create_table(table: Any, name: str, desc: dict, memtype: str = 'plain', nrow: int = 0) -> None:
    ret = table.create(name, desc, memtype=memtype, nrow=nrow)
    assert ret is True
    for colname, coldesc in desc.items():
        if 'keywords' in coldesc:
            table.putcolkeywords(colname, coldesc['keywords'])


# FLAG_PERMANENT Layout
WeatherFlagIndex = 0
TsysFlagIndex = 1
UserFlagIndex = 2
OnlineFlagIndex = 3


def timetable_key(
    table_type: str,
    antenna: int,
    spw: int,
    polarization: int | None = None,
    ms: Any | None = None,
    field_id: int | None = None,
) -> str:
    key = 'TIMETABLE_%s' % table_type
    if ms is not None:
        key = '%s_%s' % (key, ms.replace('.', '_'))
    if field_id is not None:
        key = '%s_FIELD%s' % (key, field_id)
    key = '%s_ANT%s_SPW%s' % (key, antenna, spw)
    if polarization is not None:
        key = '%s_POL%s' % (key, polarization)
    return key


class DataTableIndexer(BaseModel):
    """Map between serial indices and per-MS row indices."""

    context: Any | None = PydanticField(default=None)
    origin_mses: list[Any] = PydanticField(default_factory=list, exclude=True)
    nrow_per_ms: list[int] = PydanticField(default_factory=list, exclude=True)
    num_mses: int = PydanticField(default=0, exclude=True)

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_default=True,
    )

    def __hash__(self) -> int:
        context_id = id(self.context) if self.context is not None else 0
        return hash((self.__class__, context_id))

    def model_post_init(self, __context: Any) -> None:
        if self.context is None:
            return
        origin_mses = [
            ms for ms in self.context.observing_run.measurement_sets if ms.name == ms.origin_ms
        ]
        nrow_per_ms: list[int] = []
        for origin_ms in origin_mses:
            ro_table_name = os.path.join(self.context.observing_run.ms_datatable_name, origin_ms.basename, 'RO')
            with casa_tools.TableReader(ro_table_name) as tb:
                nrow_per_ms.append(tb.nrows())
        object.__setattr__(self, 'origin_mses', origin_mses)
        object.__setattr__(self, 'nrow_per_ms', nrow_per_ms)
        object.__setattr__(self, 'num_mses', len(nrow_per_ms))


    def serial2perms(self, i: int) -> tuple[str, int]:
        """Return basename of origin MS and per-MS row id of a given serial index."""
        base = 0
        for j in range(self.num_mses):
            past_base = base
            base += self.nrow_per_ms[j]
            if i < base:
                return self.origin_mses[j].basename, i - past_base

        raise RuntimeError('Internal Consistency Error.')

    def perms2serial(self, vis: str, i: int) -> int:
        """Return serial index."""
        ms = self.context.observing_run.get_ms(vis)
        j = self.origin_mses.index(self.context.observing_run.get_ms(ms.origin_ms))
        assert j < self.num_mses
        assert i < self.nrow_per_ms[j]

        base = sum(self.nrow_per_ms[:j])
        return base + i

    def per_ms_index_list(self, ms: Any, index_list: np.ndarray) -> np.ndarray:
        origin_ms = self.context.observing_run.get_ms(ms.origin_ms)
        j = self.origin_mses.index(origin_ms)
        base = sum(self.nrow_per_ms[:j])
        length = self.nrow_per_ms[j]
        perms_list = np.where(np.logical_and(index_list >= base, index_list < base + length), index_list)
        return perms_list - base


class DataTableImpl(BaseModel):
    """DataTable is an object to hold meta data of scantable on memory."""

    datatable_name: str | None = PydanticField(default=None, alias='name')
    readonly: bool | None = PydanticField(default=None)
    memtable1: str = PydanticField(default='', exclude=True)
    memtable2: str = PydanticField(default='', exclude=True)
    plaintable: str = PydanticField(default='', exclude=True)
    cols: dict[str, Any] = PydanticField(default_factory=dict, exclude=True)
    tb1: Any = PydanticField(default=None, exclude=True)
    tb2: Any = PydanticField(default=None, exclude=True)
    isopened: bool = PydanticField(default=False, exclude=True)

    REFKEY: ClassVar[str] = 'DIRECTION_REF'

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_default=True,
        populate_by_name=True,
    )

    def __hash__(self) -> int:
        return hash((self.__class__, self.datatable_name or ''))

    def model_post_init(self, __context: Any) -> None:
        timestamp = ('%f' % (time.time())).replace('.', '')
        self.memtable1 = 'DataTableImplRO%s.MemoryTable' % timestamp
        self.memtable2 = 'DataTableImplRW%s.MemoryTable' % timestamp
        self.plaintable = ''
        self.cols = {}
        self.tb1 = casa_tools._logging_table_cls()
        self.tb2 = casa_tools._logging_table_cls()
        self.isopened = False


        if self.datatable_name is None or len(self.datatable_name) == 0:
            readonly = False if self.readonly is None else self.readonly
            self._create(readonly=readonly)
        elif not os.path.exists(self.datatable_name):
            readonly = False if self.readonly is None else self.readonly
            self._create(readonly=readonly)
            self.plaintable = absolute_path(self.datatable_name)
        else:
            readonly = True if self.readonly is None else self.readonly
            self.importdata2(name=self.datatable_name, minimal=False, readonly=readonly)

    def __del__(self) -> None:
        self.cols.clear()
        self._close()

    def __len__(self) -> int:
        return self.nrow

    @classmethod
    def get_rotable_name(cls, datatable_name: str) -> str:
        return os.path.join(datatable_name, 'RO')

    @classmethod
    def get_rwtable_name(cls, datatable_name: str) -> str:
        return os.path.join(datatable_name, 'RW')

    @property
    def nrow(self) -> int:
        if self.isopened:
            return self.tb1.nrows()
        return 0

    @property
    def name(self) -> str:
        return self.plaintable

    @property
    def position_group_id(self) -> int:
        key = 'POSGRP_REP'
        if self.haskeyword(key):
            return np.max(np.fromiter((int(x) for x in self.getkeyword(key)), dtype=np.int32)) + 1
        return 0

    @property
    def time_group_id_small(self) -> int:
        return self.__get_time_group_id(True)

    @property
    def time_group_id_large(self) -> int:
        return self.__get_time_group_id(False)

    @property
    def direction_ref(self) -> str | None:
        if self.REFKEY in self.tb1.keywordnames():
            return self.tb1.getkeyword(self.REFKEY)
        return None

    @direction_ref.setter
    def direction_ref(self, value: str) -> None:
        if not isinstance(value, str):
            return
        if self.REFKEY not in self.tb1.keywordnames():
            self.tb1.putkeyword(self.REFKEY, value)

    def __get_time_group_id(self, small: bool = True) -> int:
        subkey = 'SMALL' if small else 'LARGE'
        pattern = r'^TIMETABLE_%s_.*' % subkey
        if np.any(np.fromiter((re.match(pattern, x) is not None for x in self.keywordnames()), dtype=bool)):
            group_id = 0
            for key in self.tb2.keywordnames():
                if re.match(pattern, key) is not None:
                    max_id = np.max(np.fromiter((int(x) for x in self.getkeyword(key)), dtype=np.int32)) + 1
                    group_id = max(group_id, max_id)
            return group_id
        return 0

    def haskeyword(self, name: str) -> bool:
        return name in self.tb2.keywordnames()

    def addrows(self, nrow: int) -> None:
        self.tb1.addrows(nrow)
        self.tb2.addrows(nrow)
        self.plaintable == ''

    def colnames(self) -> list[str]:
        return list(self.cols.keys())

    def getcol(self, name: str, startrow: int = 0, nrow: int = -1, rowincr: int = 1) -> Any:
        return self.cols[name].getcol(startrow, nrow, rowincr)

    def putcol(self, name: str, val: Any, startrow: int = 0, nrow: int = -1, rowincr: int = 1) -> None:
        self.cols[name].putcol(val, startrow, nrow, rowincr)

    def getcell(self, name: str, idx: int) -> Any:
        return self.cols[name].getcell(idx)

    def putcell(self, name: str, idx: int, val: Any) -> None:
        self.cols[name].putcell(idx, val)

    def getcolslice(self, name: str, blc: Any, trc: Any, incr: Any, startrow: int = 0, nrow: int = -1,
                    rowincr: int = 1) -> Any:
        return self.cols[name].getcolslice(blc, trc, incr, startrow, nrow, rowincr)

    def putcolslice(self, name: str, value: Any, blc: Any, trc: Any, incr: Any, startrow: int = 0,
                    nrow: int = -1, rowincr: int = 1) -> Any:
        return self.cols[name].putcolslice(value, blc, trc, incr, startrow, nrow, rowincr)

    def getcellslice(self, name: str, rownr: int, blc: Any, trc: Any, incr: Any) -> Any:
        return self.cols[name].getcellslice(rownr, blc, trc, incr)

    def putcellslice(self, name: str, rownr: int, value: Any, blc: Any, trc: Any, incr: Any) -> Any:
        return self.cols[name].putcellslice(rownr, value, blc, trc, incr)

    def getcolkeyword(self, columnname: str, keyword: str) -> Any:
        if columnname in TABLEDESC_RO:
            return self.tb1.getcolkeyword(columnname, keyword)
        return self.tb2.getcolkeyword(columnname, keyword)

    def putkeyword(self, name: str, val: Any) -> None:
        if isinstance(val, str):
            store_val = '"%s"' % val
        else:
            store_val = str(val)
        self.tb2.putkeyword(name, store_val)

    def getkeyword(self, name: str) -> Any:
        store_val = self.tb2.getkeyword(name)
        return eval(store_val)

    def keywordnames(self) -> list[str]:
        return self.tb2.keywordnames()

    def importdata(self, name: str, minimal: bool = True, readonly: bool = True) -> None:
        LOG.debug('Importing DataTable from %s...', name)
        self._copyfrom(name, minimal)
        self.plaintable = absolute_path(name)
        self.__init_cols(readonly=readonly)

    def importdata2(self, name: str, minimal: bool = True, readonly: bool = True) -> None:
        LOG.debug('Importing DataTable from %s...', name)
        self._copyfrom2(name, minimal)
        self.plaintable = absolute_path(name)
        self.__init_cols(readonly=readonly)

    def sync(self, minimal: bool = True) -> None:
        self.importdata(name=self.plaintable, minimal=minimal)

    def exportdata(self, name: str | None = None, minimal: bool = True, overwrite: bool = False) -> None:
        if name is None or len(name) == 0:
            if len(self.plaintable) == 0:
                raise IOError('You have to specify name of export table')
            name = self.plaintable
            overwrite = True

        LOG.debug('Exporting DataTable to %s...', name)
        abspath = absolute_path(name)
        if not os.path.exists(abspath):
            os.makedirs(abspath)
        elif overwrite:
            LOG.debug('Overwrite existing DataTable %s...', name)
        else:
            raise IOError('The file %s exists.' % name)

        if not minimal or not os.path.exists(os.path.join(abspath, 'RO')):
            if os.path.exists(self.tb1.name()):
                pass
            else:
                tbloc = self.tb1.copy(os.path.join(abspath, 'RO'), deep=True, valuecopy=True, returnobject=True)
                tbloc.close()
        tbloc = self.tb2.copy(os.path.join(abspath, 'RW'), deep=True,
                              valuecopy=True, returnobject=True)
        tbloc.close()
        self.plaintable = abspath

    # FIXME: this unused method contains bugs to fix.
    def export_rwtable_exclusive(self, dirty_rows: Any = None, cols: Any = None) -> None:
        """
        Export "on-memory" RW table to the one on disk.

        To support parallel operation, the method will acquire a lock for RW table
        to ensure the operation in one process doesn't overwrite the changes made by
        other processes.

        dirty_rows -- list of row numbers that are updated. If None, everything
                      including unchanged rows will be flushed. Default is None.
        cols -- list of columns that are updated. If None, all rows will be flushed.
                default is None.
        """
        rwtable = self.get_rwtable_name(self.plaintable)
        ordinary_cols = {'STATISTICS', 'FLAG', 'FLAG_PERMANENT', 'FLAG_SUMMARY', 'NMASK', 'POSGRP'}
        intersects = ordinary_cols.intersection(cols)

        with_masklist = 'MASKLIST' in cols
        with_nochange = 'NOCHANGE' in cols

        with casa_tools.TableReader(rwtable, nomodify=False, lockoptions={'option': 'user'}) as tb:
            tb.lock()
            LOG.info('Process %s have acquired a lock for RW table', os.getpid())

            if dirty_rows is None:
                dirty_rows = range(tb.nrows())

            try:
                nrow_chunk = 2000
                nrow = dirty_rows.max() - dirty_rows.min() + 1
                nchunk = nrow // nrow_chunk
                mod = nrow % nrow_chunk
                chunks = [nrow_chunk] * nchunk + [mod]
                # for each column
                for col in intersects:
                    start_row = dirty_rows.min()
                    for size_chunk in chunks:
                        # read chunk
                        chunk_src = self.tb2.getcol(col, startrow=start_row, nrow=size_chunk)
                        chunk_dst = tb.getcol(col, startrow=start_row, nrow=size_chunk)

                        chunk_min = start_row
                        chunk_max = start_row + size_chunk - 1
                        target_rows = dirty_rows[np.logical_and(chunk_min <= dirty_rows, dirty_rows <= chunk_max)]
                        for row in target_rows:
                            chunk_index = row - start_row
                            chunk_dst[..., chunk_index] = chunk_src[..., chunk_index]

                        tb.putcol(col, chunk_dst, startrow=start_row, nrow=size_chunk)
                        start_row += size_chunk

                if with_masklist is True:
                    src = self.cols['MASKLIST']
                    dst = DataTableColumnMaskList(tb)
                    for index, row in enumerate(dirty_rows):
                        data = src.getcell(index)
                        dst.putcell(row, data)

                if with_nochange is True:
                    src = self.cols['NOCHANGE']
                    dst = DataTableColumnNoChange(tb)
                    for index, row in enumerate(dirty_rows):
                        data = src.getcell(index)
                        dst.putcell(row, data)

            finally:
                LOG.info('Process %s is going to release a lock for RW table', os.getpid())
                tb.unlock()

    def _create(self, readonly: bool = False) -> None:
        self._close()
        create_table(self.tb1, self.memtable1, TABLEDESC_RO, 'memory', self.nrow)
        create_table(self.tb2, self.memtable2, TABLEDESC_RW, 'memory', self.nrow)
        self.isopened = True
        self.__init_cols(readonly=readonly)

    def __init_cols(self, readonly: bool = True) -> None:
        self.cols.clear()
        if readonly:
            ro_column = RODataTableColumn
            rw_column = RWDataTableColumn
        else:
            ro_column = RWDataTableColumn
            rw_column = RWDataTableColumn
        type_map = {'integer': int, 'double': float, 'string': str}

        def datatype(desc: dict) -> Any:
            if 'ndim' in desc and desc['ndim'] > 0:
                return list
            return type_map[desc['valueType']]

        for key, val in TABLEDESC_RO.items():
            self.cols[key] = ro_column(self.tb1, key, datatype(val))
        for key, val in TABLEDESC_RW.items():
            if key == 'MASKLIST':
                self.cols[key] = DataTableColumnMaskList(self.tb2)
            elif key == 'NOCHANGE':
                self.cols[key] = DataTableColumnNoChange(self.tb2)
            else:
                self.cols[key] = rw_column(self.tb2, key, datatype(val))

    def _close(self) -> None:
        if self.isopened:
            self.tb1.close()
            self.tb2.close()
            self.isopened = False

    def _copyfrom(self, name: str, minimal: bool = True) -> None:
        self._close()
        abspath = absolute_path(name)
        if not minimal or abspath != self.plaintable:
            with casa_tools.TableReader(os.path.join(name, 'RO')) as tb:
                self.tb1 = tb.copy(self.memtable1, deep=True, valuecopy=True, memorytable=True, returnobject=True)
        with casa_tools.TableReader(os.path.join(name, 'RW')) as tb:
            self.tb2 = tb.copy(self.memtable2, deep=True, valuecopy=True, memorytable=True, returnobject=True)
        self.isopened = True

    def _copyfrom2(self, name: str, minimal: bool = True) -> None:
        self._close()
        abspath = absolute_path(name)
        if not minimal or abspath != self.plaintable:
            with casa_tools.TableReader(os.path.join(name, 'RO')) as tb:
                self.tb1 = tb.copy(self.memtable1, deep=True, valuecopy=True, memorytable=True, returnobject=True)
        with casa_tools.TableReader(os.path.join(name, 'RW')) as tb:
            self.tb2 = tb.copy(self.memtable2, deep=True, valuecopy=True, memorytable=True, returnobject=True)
        self.isopened = True

    def get_posdict(self, ant: int, spw: int, pol: int) -> dict:
        posgrp_list = self.getkeyword('POSGRP_LIST')
        try:
            mygrp = posgrp_list[str(ant)][str(spw)][str(pol)]
        except KeyError as exc:
            raise KeyError('ant %s spw %s pol %s not in reduction group list' % (ant, spw, pol)) from exc

        posgrp_rep = self.getkeyword('POSGRP_REP')
        rows = self.getcol('ROW')
        posgrp = self.getcol('POSGRP')
        posdict: dict = {}
        for key, val in posgrp_rep.items():
            if int(key) not in mygrp:
                continue
            row_key = rows[val]
            posdict[row_key] = [[], []]

        for idx in range(len(posgrp)):
            grp = posgrp[idx]
            if grp not in mygrp:
                continue
            row = rows[idx]
            rep = posgrp_rep[str(grp)]
            row_key = rows[rep]
            posdict[row_key][0].append(row)
            posdict[row_key][1].append(idx)
            if row != row_key:
                posdict[row] = [[-1, row_key], [rep]]

        return posdict

    def set_timetable(self, ant: int, spw: int, pol: int, mygrp: dict, timegrp_s: list, timegrp_l: list,
                      ms: Any | None = None, field_id: int | None = None) -> None:
        LOG.info('set_timetable start')
        start_time = time.time()

        mygrp_s = mygrp['small']
        mygrp_l = mygrp['large']
        rows = self.getcol('ROW')

        timedic_s = construct_timegroup(rows, set(mygrp_s), timegrp_s)
        timedic_l = construct_timegroup(rows, set(mygrp_l), timegrp_l)
        timetable_s = [timedic_s[idx] for idx in mygrp_s]
        timetable_l = [timedic_l[idx] for idx in mygrp_l]
        timetable = [timetable_s, timetable_l]
        end_time = time.time()
        LOG.info('construct timetable: Elapsed time %s sec', end_time - start_time)

        LOG.debug('timetable=%s', timetable)

        start_time2 = time.time()
        key_small = timetable_key('SMALL', ant, spw, pol, ms, field_id)
        key_large = timetable_key('LARGE', ant, spw, pol, ms, field_id)
        keys = self.tb2.keywordnames()
        LOG.debug('add time table: keys for small gap %s large gap %s', key_small, key_large)
        dictify = lambda x: dict([(str(i), t) for (i, t) in enumerate(x)])
        if key_small not in keys or key_large not in keys:
            self.putkeyword(key_small, dictify(timetable[0]))
            self.putkeyword(key_large, dictify(timetable[1]))

        end_time = time.time()
        LOG.info('put timetable: Elapsed time %s sec', end_time - start_time2)
        LOG.info('set get_timetable end: Elapsed time %s sec', end_time - start_time)

    def get_timetable(self, ant: int, spw: int, pol: int, ms: Any | None = None,
                      field_id: int | None = None) -> list:
        LOG.trace('new get_timetable start')
        start_time = time.time()
        key_small = timetable_key('SMALL', ant, spw, pol, ms, field_id)
        key_large = timetable_key('LARGE', ant, spw, pol, ms, field_id)
        keys = self.tb2.keywordnames()
        LOG.debug('get time table: keys for small gap %s large gap %s', key_small, key_large)
        if key_small in keys and key_large in keys:
            ttdict_small = self.getkeyword(key_small)
            ttdict_large = self.getkeyword(key_large)
            timetable_small = [ttdict_small[str(i)] for i in range(len(ttdict_small))]
            timetable_large = [ttdict_large[str(i)] for i in range(len(ttdict_large))]
            timetable = [timetable_small, timetable_large]
        else:
            raise RuntimeError(
                'time table for Antenna %s spw %s pol %s is not configured properly' % (ant, spw, pol)
            )
        end_time = time.time()
        LOG.trace('new get_timetable end: Elapsed time %s sec', end_time - start_time)

        return timetable

    def get_timegap(self, ant: int, spw: int, pol: int, asrow: bool = True, ms: Any | None = None,
                    field_id: int | None = None) -> list:
        timegap_s = self.getkeyword('TIMEGAP_S')
        timegap_l = self.getkeyword('TIMEGAP_L')
        if ms is None:
            try:
                mygap_s = timegap_s[ant][spw][pol]
                mygap_l = timegap_l[ant][spw][pol]
            except KeyError as exc:
                raise KeyError('ant %s spw %s pol %s not in reduction group list' % (ant, spw, pol)) from exc
        else:
            try:
                mygap_s = timegap_s[ms.basename.replace('.', '_')][ant][spw][field_id]
                mygap_l = timegap_l[ms.basename.replace('.', '_')][ant][spw][field_id]
            except KeyError as exc:
                raise KeyError(
                    'ms %s field %s ant %s spw %s not in reduction group list' % (ms.basename, field_id, ant, spw)
                ) from exc

        if asrow:
            rows = self.getcol('ROW')
            timegap = [[], []]
            for idx in mygap_s:
                timegap[0].append(rows[idx])
            for idx in mygap_l:
                timegap[1].append(rows[idx])
        else:
            timegap = [mygap_s, mygap_l]
        return timegap

    def _update_tsys(self, context: Any, infile: str, tsystable: str, spwmap: list,
                     to_fieldid: int, gainfield: str) -> None:
        start_time = time.time()

        msobj = context.observing_run.get_ms(infile)
        to_antids = [a.id for a in msobj.antennas]
        from_fields = []
        if gainfield.upper() == 'NEAREST':
            LOG.info('to_fieldid=%s', to_fieldid)
            to_field = msobj.get_fields(field_id=to_fieldid)[0]
            if 'ATMOSPHERE' in to_field.intents:
                from_fields = [to_fieldid]
            else:
                atm_fields = msobj.get_fields(intent='ATMOSPHERE')
                # absolute OFF
                test_prefix = '{}_OFF_'.format(to_field.clean_name)
                nearest_id = np.where([a.clean_name.startswith(test_prefix) for a in atm_fields])[0]
                if len(nearest_id) > 0:
                    from_fields = [atm_fields[i].id for i in nearest_id]
                else:
                    rmin = casa_tools.quanta.quantity(180.0, 'deg')
                    origin = to_field.mdirection
                    nearest_id = -1
                    for f in atm_fields:
                        r = casa_tools.measures.separation(origin, f.mdirection)
                        # quanta.le is equivalent to <=
                        if casa_tools.quanta.le(r, rmin):
                            rmin = r
                            nearest_id = f.id
                    if nearest_id != -1:
                        from_fields = [nearest_id]
                    else:
                        raise RuntimeError('No nearest field for Tsys update.')
        else:
            from_fields = [field.id for field in msobj.get_fields(gainfield)]
        LOG.info('from_fields = %s', from_fields)

        with casa_tools.TableReader(tsystable) as tb:
            tsel = tb.query('FIELD_ID IN %s' % list_to_str(from_fields))
            spws = tsel.getcol('SPECTRAL_WINDOW_ID')
            times = tsel.getcol('TIME')
            antids = tsel.getcol('ANTENNA1')
            tsys_masked: dict[int, Any] = {}
            for i in range(tsel.nrows()):
                tsys = tsel.getcell('FPARAM', i)
                flag = tsel.getcell('FLAG', i)
                tsys_masked[i] = np.ma.masked_array(tsys, mask=(flag == True))
            tsel.close()

        def map_spwchans(atm_spw: Any, science_spw: Any) -> tuple[int, int]:
            """
            Map the channel ID ranges of ATMCal spw that covers frequency range of a science spw
            Arguments: spw object of ATMCal and science spws
            """
            atm_freqs = np.array(atm_spw.channels.chan_freqs)
            min_chan = np.where(
                abs(atm_freqs - float(science_spw.min_frequency.value))
                == min(abs(atm_freqs - float(science_spw.min_frequency.value)))
            )[0][0]
            max_chan = np.where(
                abs(atm_freqs - float(science_spw.max_frequency.value))
                == min(abs(atm_freqs - float(science_spw.max_frequency.value)))
            )[0][-1]
            start_atmchan = min(min_chan, max_chan)
            end_atmchan = max(min_chan, max_chan)
            if end_atmchan == start_atmchan:
                end_atmchan = start_atmchan + 1
            return start_atmchan, end_atmchan

        dt_antenna = self.getcol('ANTENNA')
        dt_spw = self.getcol('IF')
        dt_field = self.getcol('FIELD_ID')
        field_sel = np.where(dt_field == to_fieldid)[0]
        dt_antenna = dt_antenna[field_sel]
        dt_spw = dt_spw[field_sel]
        atm_spws = set(spws)
        science_spws = [x.id for x in msobj.get_spectral_windows(science_windows_only=True)]
        for spw_to, spw_from in enumerate(spwmap):
            if spw_from not in atm_spws:
                continue
            if spw_to not in science_spws:
                continue

            atm_spw = msobj.get_spectral_window(spw_from)
            science_spw = msobj.get_spectral_window(spw_to)
            science_dd = msobj.get_data_description(spw=science_spw)
            corr_index = [science_dd.get_polarization_id(corr) for corr in science_dd.corr_axis]
            start_atmchan, end_atmchan = map_spwchans(atm_spw, science_spw)
            LOG.info(
                'Transfer Tsys from spw %s (chans: %s~%s) to %s',
                spw_from,
                start_atmchan,
                end_atmchan,
                spw_to,
            )
            for ant_to in to_antids:
                cal_idxs = np.where(np.logical_and(spws == spw_from, antids == ant_to))[0]
                if len(cal_idxs) == 0:
                    continue
                atsys = np.asarray([tsys_masked[i].take(corr_index, axis=0)[:, start_atmchan:end_atmchan+1].mean(axis=1).data
                                           for i in cal_idxs])
                dtrows = field_sel[np.where(np.logical_and(dt_antenna == ant_to, dt_spw == spw_to))[0]]
                time_sel = times.take(cal_idxs)  # in sec
                for dt_id in dtrows:
                    tref = self.getcell('TIME', dt_id) * 86400  # day->sec
                    if atsys.shape[0] == 1:  # only one Tsys measurement selected
                        self.putcell('TSYS', dt_id, atsys[0, :])
                    else:
                        itsys = _interpolate(atsys, time_sel, tref)
                        self.putcell('TSYS', dt_id, itsys)
        end_time = time.time()
        LOG.info('_update_tsys: elapsed %s sec', end_time - start_time)

    def _update_flag(self, infile: str) -> None:
        LOG.info('Updating online flag for %s', os.path.basename(infile))
        filename = self.getkeyword('FILENAME')
        assert os.path.basename(infile) == os.path.basename(filename)

        ms_rows = self.getcol('ROW')
        tmp_array = np.empty((4, 1), dtype=np.int32)
        with casa_tools.TableReader(infile) as tb:
            for dt_row, ms_row in enumerate(ms_rows):
                flag = tb.getcell('FLAG', ms_row)
                rowflag = tb.getcell('FLAG_ROW', ms_row)
                npol = flag.shape[0]
                online_flag = tmp_array[:npol, :]
                if rowflag is True:
                    online_flag[:] = 0
                else:
                    for ipol in range(npol):
                        online_flag[ipol, 0] = 0 if flag[ipol].all() else 1
                self.putcellslice(
                    'FLAG_PERMANENT',
                    int(dt_row),
                    online_flag,
                    blc=[0, OnlineFlagIndex],
                    trc=[npol - 1, OnlineFlagIndex],
                    incr=[1, 1],
                )
                flag_summary = self.getcell('FLAG_SUMMARY', int(dt_row))
                flag_summary *= online_flag[:npol, 0]
                self.putcell('FLAG_SUMMARY', int(dt_row), flag_summary)


class RODataTableColumn:
    def __init__(self, table: Any, name: str, dtype: Any) -> None:
        self.tb = table
        self.name = name
        self.caster_get = dtype

    def __repr__(self) -> str:
        return '%s("%s","%s")' % (self.__class__.__name__, self.name, self.caster_get)

    def getcell(self, idx: int) -> Any:
        return self.tb.getcell(self.name, idx)

    def getcol(self, startrow: int = 0, nrow: int = -1, rowincr: int = 1) -> Any:
        return self.tb.getcol(self.name, startrow, nrow, rowincr)

    def getcellslice(self, rownr: int, blc: Any, trc: Any, incr: Any) -> Any:
        return self.tb.getcellslice(self.name, rownr, blc, trc, incr)

    def getcolslice(self, blc: Any, trc: Any, incr: Any, startrow: int = 0, nrow: int = -1,
                    rowincr: int = 1) -> Any:
        return self.tb.getcolslice(self.name, blc, trc, incr, startrow, nrow, rowincr)

    def putcell(self, idx: int, val: Any) -> None:
        self.__raise()

    def putcol(self, val: Any, startrow: int = 0, nrow: int = -1, rowincr: int = 1) -> None:
        self.__raise()

    def putcellslice(self, rownr: int, value: Any, blc: Any, trc: Any, incr: Any) -> None:
        self.__raise()

    def putcolslice(self, value: Any, blc: Any, trc: Any, incr: Any, startrow: int = 0, nrow: int = -1,
                    rowincr: int = 1) -> None:
        self.__raise()

    def __raise(self) -> None:
        raise NotImplementedError('column %s is read-only' % self.name)


class RWDataTableColumn(RODataTableColumn):
    def __init__(self, table: Any, name: str, dtype: Any) -> None:
        super().__init__(table, name, dtype)
        if dtype == list:
            self.caster_put = np.asarray
        else:
            self.caster_put = dtype

    def putcell(self, idx: int, val: Any) -> None:
        self.tb.putcell(self.name, int(idx), self.caster_put(val))

    def putcol(self, val: Any, startrow: int = 0, nrow: int = -1, rowincr: int = 1) -> None:
        self.tb.putcol(self.name, np.asarray(val), int(startrow), int(nrow), int(rowincr))

    def putcellslice(self, rownr: int, value: Any, blc: Any, trc: Any, incr: Any) -> Any:
        return self.tb.putcellslice(self.name, rownr, value, blc, trc, incr)

    def putcolslice(self, value: Any, blc: Any, trc: Any, incr: Any, startrow: int = 0, nrow: int = -1,
                    rowincr: int = 1) -> Any:
        return self.tb.putcolslice(self.name, value, blc, trc, incr, startrow, nrow, rowincr)


class DataTableColumnNoChange(RWDataTableColumn):
    def __init__(self, table: Any) -> None:
        super().__init__(table, 'NOCHANGE', int)

    def putcell(self, idx: int, val: Any) -> None:
        if isinstance(val, bool):
            stored = -1
        else:
            stored = val
        self.tb.putcell(self.name, int(idx), int(stored))


class DataTableColumnMaskList(RWDataTableColumn):
    NoMask = np.zeros((1, 2), dtype=np.int32) - 1

    def __init__(self, table: Any) -> None:
        super().__init__(table, 'MASKLIST', list)

    def getcell(self, idx: int) -> Any:
        val = self.tb.getcell(self.name, int(idx))
        if sum(val[0]) < 0:
            return np.zeros(0, dtype=np.int32)
        return val

    def getcol(self, startrow: int = 0, nrow: int = -1, rowincr: int = 1) -> Any:
        if nrow < 0:
            nrow = self.tb.nrows()
        ret = collections.defaultdict(list)
        idx = 0
        for i in range(startrow, nrow, rowincr):
            masklist = self.getcell(i)
            if len(masklist) == 1 and masklist[0][0] == 0 and masklist[0][1] == 0:
                ret[idx] = masklist
            idx += 1
        return ret

    def putcell(self, idx: int, val: Any) -> None:
        stored = self.NoMask if len(val) == 0 else val
        self.tb.putcell(self.name, int(idx), np.asarray(stored))

    def putcol(self, val: Any, startrow: int = 0, nrow: int = -1, rowincr: int = 1) -> None:
        if nrow < 0:
            nrow = min(startrow + len(val) * rowincr, self.tb.nrows())
        idx = 0
        for i in range(startrow, nrow, rowincr):
            self.putcell(i, np.asarray(val[idx]))
            idx += 1


def _interpolate(v: Any, t: Any, tref: float) -> Any:
    idx = bisect.bisect_left(t, tref)
    if idx == 0:
        return v[0]
    if idx == len(t):
        return v[-1]
    t1 = t[idx] - tref
    t0 = tref - t[idx - 1]
    return (v[idx] * t0 + v[idx - 1] * t1) / (t[idx] - t[idx - 1])


def construct_timegroup(rows: Any, group_id_list: set, group_association_list: list) -> dict:
    timetable_dict = {x: [[], []] for x in group_id_list}
    for idx, group_id in enumerate(group_association_list):
        if group_id not in group_id_list:
            continue
        timetable_dict[group_id][0].append(rows[idx])
        timetable_dict[group_id][1].append(idx)
    return timetable_dict
