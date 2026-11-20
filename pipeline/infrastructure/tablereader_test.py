from unittest import mock

import numpy as np

from pipeline.infrastructure.tablereader import FieldTable


def _make_msmd(nspw=4, sqld_spws=(0, 1), times_by_spw=None, times_by_field=None):
    msmd = mock.MagicMock()
    msmd.name.return_value = 'fake.ms'
    msmd.nspw.return_value = nspw
    msmd.almaspws.return_value = list(sqld_spws)
    msmd.timesforspws.return_value = times_by_spw if times_by_spw is not None else {}
    msmd.nfields.return_value = len(times_by_field or {})
    msmd.namesforfields.return_value = [f'field_{i}' for i in range(len(times_by_field or {}))]
    msmd.scansforfield.return_value = [1]
    msmd.sourceidforfield.return_value = 0
    msmd.phasecenter.return_value = {'m0': {'value': 0.0, 'unit': 'rad'}}
    msmd.timesforfield.side_effect = lambda fid: np.array(times_by_field[fid], dtype=float)
    return msmd


def test_get_non_sqld_times_returns_none_without_sqld_spws():
    msmd = _make_msmd(nspw=2, sqld_spws=())
    assert FieldTable._get_non_sqld_times(msmd) is None
    msmd.timesforspws.assert_not_called()


def test_get_non_sqld_times_returns_none_when_all_spws_are_sqld():
    msmd = _make_msmd(nspw=2, sqld_spws=(0, 1))
    assert FieldTable._get_non_sqld_times(msmd) is None
    msmd.timesforspws.assert_not_called()


def test_get_non_sqld_times_returns_none_when_timesforspws_empty():
    msmd = _make_msmd(nspw=4, sqld_spws=(0, 1), times_by_spw={})
    assert FieldTable._get_non_sqld_times(msmd) is None


def test_get_non_sqld_times_returns_unique_sorted_timestamps():
    msmd = _make_msmd(
        nspw=4,
        sqld_spws=(0, 1),
        times_by_spw={
            2: np.array([30.0, 10.0, 20.0]),
            3: np.array([20.0, 40.0]),
        },
    )
    np.testing.assert_array_equal(FieldTable._get_non_sqld_times(msmd), np.array([10.0, 20.0, 30.0, 40.0]))


def test_field_table_strips_sqld_only_timestamps_with_fallback(monkeypatch):
    msmd = _make_msmd(
        nspw=4,
        sqld_spws=(0, 1),
        times_by_spw={2: np.array([10.0, 20.0])},
        times_by_field={
            0: [5.0, 10.0, 15.0, 20.0, 25.0],
            1: [5.0, 25.0],  # no non-SQLD overlap -> falls back to full times
        },
    )

    table_mock = mock.MagicMock()
    table_mock.__enter__.return_value = table_mock
    table_mock.colnames.return_value = []
    monkeypatch.setattr('pipeline.infrastructure.tablereader.casa_tools.TableReader', lambda _path: table_mock)

    rows = FieldTable._read_table(msmd)
    assert len(rows) == 2
    np.testing.assert_array_equal(rows[0][3], np.array([10.0, 20.0]))
    np.testing.assert_array_equal(rows[1][3], np.array([5.0, 25.0]))
