"""Unit tests for DataTable implementation (Phase 5 full port)."""

from __future__ import annotations

import unittest
from unittest import mock

import pipeline.domain.datatable as datatable


class DummyMs:
    def __init__(self, name: str, origin_ms: str | None = None) -> None:
        self.name = name
        self.origin_ms = origin_ms or name
        self.basename = name.replace('.ms', '')


class DummyObservingRun:
    def __init__(self, measurement_sets: list[DummyMs]) -> None:
        self.measurement_sets = measurement_sets
        self.ms_datatable_name = '/tmp/datatable'

    def get_ms(self, vis: str) -> DummyMs:
        for ms in self.measurement_sets:
            if ms.name == vis:
                return ms
        raise KeyError(vis)


class DummyContext:
    def __init__(self, measurement_sets: list[DummyMs]) -> None:
        self.observing_run = DummyObservingRun(measurement_sets)


class DummyTableReader:
    def __init__(self, path: str, *args: object, **kwargs: object) -> None:
        self.path = path
        self._nrows = 3

    def __enter__(self) -> DummyTableReader:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False

    def nrows(self) -> int:
        return self._nrows


class DummyCASATable:
    def __init__(self) -> None:
        self._nrows = 0
        self._name = ''

    def create(self, name: str, desc: dict, memtype: str = 'plain', nrow: int = 0) -> bool:
        self._name = name
        self._nrows = nrow
        return True

    def putcolkeywords(self, colname: str, keywords: dict) -> None:
        return None

    def addrows(self, nrow: int) -> None:
        self._nrows += nrow

    def nrows(self) -> int:
        return self._nrows

    def close(self) -> None:
        return None

    def name(self) -> str:
        return self._name

    def keywordnames(self) -> list[str]:
        return []

    def getcolkeyword(self, columnname: str, keyword: str) -> None:
        return None

    def getkeyword(self, name: str) -> None:
        return None

    def putkeyword(self, name: str, val: str) -> None:
        return None


class DummyColumnTable:
    def __init__(self, data: dict[str, dict[int, int]]) -> None:
        self.data = data

    def getcell(self, name: str, idx: int) -> int:
        return self.data[name][idx]

    def getcol(self, name: str, startrow: int = 0, nrow: int = -1, rowincr: int = 1) -> list[int]:
        if nrow < 0:
            nrow = len(self.data[name])
        return [self.data[name][i] for i in range(startrow, startrow + nrow, rowincr)]

    def getcellslice(self, name: str, rownr: int, blc: object, trc: object, incr: object) -> int:
        return self.getcell(name, rownr)

    def getcolslice(self, name: str, blc: object, trc: object, incr: object, startrow: int = 0, nrow: int = -1,
                    rowincr: int = 1) -> list[int]:
        return self.getcol(name, startrow, nrow, rowincr)

    def putcell(self, name: str, idx: int, val: int) -> None:
        self.data.setdefault(name, {})[idx] = val

    def putcol(self, name: str, val: list[int], startrow: int = 0, nrow: int = -1, rowincr: int = 1) -> None:
        for offset, v in enumerate(val):
            self.putcell(name, startrow + offset * rowincr, v)

    def putcellslice(self, name: str, rownr: int, value: int, blc: object, trc: object, incr: object) -> None:
        self.putcell(name, rownr, value)

    def putcolslice(self, name: str, value: list[int], blc: object, trc: object, incr: object,
                    startrow: int = 0, nrow: int = -1, rowincr: int = 1) -> None:
        self.putcol(name, value, startrow, nrow, rowincr)


class TestDataTable(unittest.TestCase):
    """Test DataTable implementation."""

    def test_indexer_mapping(self) -> None:
        measurement_sets = [DummyMs('a.ms'), DummyMs('b.ms')]
        context = DummyContext(measurement_sets)
        with mock.patch('pipeline.domain.datatable.casa_tools.TableReader', DummyTableReader):
            indexer = datatable.DataTableIndexer(context=context)

        self.assertEqual(indexer.num_mses, 2)
        self.assertEqual(indexer.serial2perms(4), ('b', 1))
        self.assertEqual(indexer.perms2serial('b.ms', 1), 4)

    def test_indexer_positional_constructor(self) -> None:
        measurement_sets = [DummyMs('a.ms'), DummyMs('b.ms')]
        context = DummyContext(measurement_sets)
        with mock.patch('pipeline.domain.datatable.casa_tools.TableReader', DummyTableReader):
            indexer = datatable.DataTableIndexer(context)

        self.assertIs(indexer.context, context)
        self.assertEqual(indexer.num_mses, 2)

    def test_table_init_and_cols(self) -> None:
        with mock.patch('pipeline.domain.datatable.casa_tools._logging_table_cls', DummyCASATable):
            table = datatable.DataTableImpl()

        self.assertEqual(table.nrow, 0)
        self.assertIn('ROW', table.colnames())
        table.addrows(2)
        self.assertEqual(table.nrow, 2)

    def test_table_positional_constructor(self) -> None:
        with (
            mock.patch('pipeline.domain.datatable.casa_tools._logging_table_cls', DummyCASATable),
            mock.patch('pipeline.domain.datatable.os.path.exists', return_value=False),
            mock.patch('pipeline.domain.datatable.absolute_path', side_effect=lambda p: p),
            mock.patch.object(datatable.DataTableImpl, '_create', return_value=None),
        ):
            table = datatable.DataTableImpl('/tmp/some-datatable')

        self.assertEqual(table.datatable_name, '/tmp/some-datatable')

    def test_ro_column_readonly(self) -> None:
        table = DummyColumnTable({'ROW': {0: 5}})
        col = datatable.RODataTableColumn(table, 'ROW', int)

        self.assertEqual(col.getcell(0), 5)
        with self.assertRaises(NotImplementedError):
            col.putcell(0, 1)
