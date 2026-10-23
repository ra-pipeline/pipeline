from __future__ import annotations

import io
import pathlib
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from pipeline.hsd.heuristics import fitorder
from pipeline.hsd.heuristics.baselineparamconfig import (
    BaselineFitParamConfig,
    BaselineParamKeys as BLP,
    as_maskstring,
    write_blparam,
    no_switching,
    do_switching
)


@pytest.fixture
def heuristic_poly():
    return BaselineFitParamConfig(fitfunc='poly', switchpoly=False)


@pytest.fixture
def heuristic_cspline():
    return BaselineFitParamConfig(fitfunc='cspline', switchpoly=True)


@pytest.mark.parametrize("masklist, expected", [
    ([[0, 10], [20, 30]], "0~10;20~30"),
    ([[5, 5]], "5~5"),
    ([], ""),
])
def test_as_maskstring(masklist, expected):
    assert as_maskstring(masklist) == expected

@pytest.mark.parametrize("func, npiece, nwave, expected", [
    ("poly","", "", ["1", "0", "0~10", "poly", "1", "", ""]),
    ("cspline", 3, "", ["1", "0", "0~10", "cspline", "1", "3", ""]),
    ("sinusoid","", [2,4,6], ["1", "0", "0~10", "sinusoid", "1", "", "[2,4,6]"]),
])
def test_write_blparam(func, npiece, nwave, expected):
    fileobj = io.StringIO()
    param = {
        BLP.ROW: 1,
        BLP.POL: 0,
        BLP.MASK: "0~10",
        BLP.FUNC: func,
        BLP.ORDER: 1,
        BLP.NPIECE: npiece,
        BLP.NWAVE: nwave
    }
    write_blparam(fileobj, param)
    output = fileobj.getvalue().strip()

    # Values: 1, 0, 0~10, , , , , , , , poly, 1, ,
    parts = output.split(',')
    assert parts[0] == "1"
    assert parts[1] == "0"
    assert parts[2] == "0~10"
    assert parts[10] == expected[3]
    assert parts[11] == "1"
    assert parts[12] == expected[5]

    if expected[6].__contains__("["):
        assert ",".join(parts[13:16]) == expected[6]

    else:
        assert parts[13] == expected[6]



def test_no_switching():
    engine = MagicMock()
    result = no_switching(engine, 100, (0, 0), 1, [])
    assert result == (fitorder.FittingFunction.CSPLINE.blfunc, 0)
    engine.assert_not_called()


class TestBaselineFitParamConfig:
    def test_init(self, heuristic_poly, heuristic_cspline):
        assert heuristic_poly.fitfunc == fitorder.FittingFunction.POLY
        assert heuristic_poly.switching_heuristic == no_switching

        assert heuristic_cspline.fitfunc == fitorder.FittingFunction.CSPLINE
        assert heuristic_cspline.switching_heuristic == do_switching

    @pytest.mark.parametrize("mask, end_offset, expected", [
        (np.ones(10, dtype=int), 0, [[0, 10]]),
        (np.ones(10, dtype=int), 1, [[0, 9]]),
        (np.zeros(10, dtype=int), 0, []),
        (np.array([0, 1, 1, 0, 0, 1, 1, 1, 0, 1], dtype=int), 0, [[1, 3], [5, 8], [9, 10]]),
        (np.array([0, 1, 1, 0, 0, 1, 1, 1, 0, 1], dtype=int), 1, [[1, 2], [5, 7], [9, 9]]),
        (np.array([1, 0, 1], dtype=int), 0, [[0, 1], [2, 3]]),
    ])
    def test_convert_mask_to_masklist(self, heuristic_poly, mask, end_offset, expected):
        # Accessing private method for testing
        result = heuristic_poly._BaselineFitParamConfig__convert_mask_to_masklist(mask, end_offset)
        assert result == expected

    def test_convert_flags_to_masklist(self, heuristic_poly):
        flags = np.array([
            [0, 1, 1, 0],
            [1, 0, 0, 1]
        ], dtype=int)
        # '1' means flagged (invalid), '0' means valid.
        # Result should be list of ranges where value is 1.
        # row 0: [1, 3]
        # row 1: [0, 1], [3, 4]
        result = heuristic_poly._BaselineFitParamConfig__convert_flags_to_masklist(flags)
        assert result == [[[1, 2]], [[0, 0], [3, 3]]]

    def test_get_fit_param_poly(self, heuristic_poly):
        edge = fitorder.EdgeChannels(0, 0)
        result = heuristic_poly._get_fit_param(polyorder=2, nchan=100, edge=edge, nchan_without_edge=100,
                                               nchan_masked=0, masklist=[])
        assert result[BLP.FUNC] == 'poly'
        assert result[BLP.ORDER] == 2

    def test_get_fit_param_cspline(self, heuristic_cspline):
        edge = fitorder.EdgeChannels(0, 0)
        result = heuristic_cspline._get_fit_param(polyorder=2, nchan=10, edge=edge, nchan_without_edge=5,
                                                  nchan_masked=0, masklist=[[0,1], [0,2], [5,6], [7,8], [3,4]])
        assert result[BLP.FUNC] == 'cspline'
        assert result[BLP.NPIECE] == 1
        assert result[BLP.ORDER] == 0

    def test_get_fit_param_sinusoid(self):
        config = BaselineFitParamConfig(fitfunc='sinusoid')
        config.wave_number = [1, 2, 3]
        edge = fitorder.EdgeChannels(0, 0)
        result = config._get_fit_param(polyorder=0, nchan=100, edge=edge, nchan_without_edge=100, nchan_masked=0,
                                       masklist=[])
        assert result[BLP.FUNC] == 'sinusoid'
        assert result[BLP.NWAVE] == [1, 2, 3]

    def test_configure_baseline_param(self, heuristic_poly):
        edge = fitorder.EdgeChannels(5, 5)
        mask = np.ones(100, dtype=int)
        mask_list = [[20, 30]]

        result = heuristic_poly._configure_baseline_param(row_idx=1, pol=0, polyorder=1, nchan=100, edge=edge,
                                                          mask=mask, mask_list=mask_list)

        assert result[BLP.ROW] == 1
        assert result[BLP.POL] == 0
        assert result[BLP.FUNC] == 'poly'
        # MASK should contain fit ranges: [0, 19] and [31, 99]
        assert result[BLP.MASK] == '0~19;31~99'

    @patch('pipeline.hsd.heuristics.baselineparamconfig.casa_tools.TableReader')
    @patch('pipeline.hsd.heuristics.baselineparamconfig.fitorder.FitOrderHeuristics')
    def test_calculate(self, mock_fitorder_heuristics, mock_table_reader, heuristic_poly):
        import hashlib

        # Mocks for MeasurementSet and its components
        mock_ms = MagicMock()
        mock_ms.name = 'test.ms'
        mock_ms.basename = 'test.ms'
        mock_ms.origin_ms = 'test.ms'

        mock_spw = MagicMock()
        mock_spw.num_channels = 100
        mock_ms.spectral_windows = {0: mock_spw}

        mock_dd = MagicMock()
        mock_dd.num_polarizations = 2
        # Maybe not
        mock_ms.get_data_description.return_value = mock_dd

        # Mock DataTable
        mock_datatable = MagicMock()

        # time_table format: [member_list, ...] where member_list is [origin_rows, datatable_row_idxs]
        member_list = [([0, 1], [10, 11])]
        mock_datatable.get_timetable.return_value = [member_list]
        mock_datatable.getcell.return_value = []  # for MASKLIST

        # Mock TableReader
        mock_tb = mock_table_reader.return_value.__enter__.return_value
        mock_tb.colnames.return_value = ['DATA', 'FLAG']
        mock_tb.getcell.side_effect = lambda col, row: np.zeros((2, 100)) if col == 'DATA' else np.zeros((2, 100),
                                                                                                         dtype=bool)

        # Mock FitOrderHeuristics
        mock_fo = mock_fitorder_heuristics.return_value
        mock_fo.calculate.return_value = 1

        if pathlib.Path.cwd().joinpath("test.blparam").exists():
            pathlib.Path("test.blparam").unlink(missing_ok=True)

        _ = heuristic_poly.calculate(
            datatable=mock_datatable,
            ms=mock_ms,
            rowmap={0: 0, 1: 1},
            antenna_id=0,
            field_id=0,
            spw_id=0,
            fit_order=2,
            edge=(5, 5),
            deviation_mask=None,
            blparam='test.blparam'
        )

        expected_contents = "db471c3de432288537df1187cd7c83e9b1e30c309958ecb4e30c3244e7d8a649"
        assert hashlib.sha256(open('test.blparam','rb').read()).hexdigest() == expected_contents

        # Clean up the file.
        pathlib.Path("test.blparam").unlink(missing_ok=True)
