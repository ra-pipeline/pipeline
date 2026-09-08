from __future__ import annotations

import io
import numpy as np
import pytest
from unittest.mock import MagicMock, patch, mock_open

from pipeline.hsd.heuristics.baselineparamconfig import (
    BaselineFitParamConfig,
    BaselineParamKeys as BLP,
    as_maskstring,
    write_blparam,
    no_switching,
    do_switching
)
from pipeline.hsd.heuristics import fitorder


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


def test_write_blparam():
    fileobj = io.StringIO()
    param = {
        BLP.ROW: 1,
        BLP.POL: 0,
        BLP.MASK: "0~10",
        BLP.FUNC: "poly",
        BLP.ORDER: 1
    }
    write_blparam(fileobj, param)
    output = fileobj.getvalue().strip()
    # Values: 1, 0, 0~10, , , , , , , , poly, 1, ,
    parts = output.split(',')
    assert parts[0] == "1"
    assert parts[1] == "0"
    assert parts[2] == "0~10"
    assert parts[10] == "poly"
    assert parts[11] == "1"


def test_no_switching():
    engine = MagicMock()
    result = no_switching(engine, 100, (0, 0), 1, [])
    assert result == (fitorder.FittingFunction.CSPLINE.blfunc, 0)
    engine.assert_not_called()


def test_do_switching():
    engine = MagicMock(return_value=('poly', 1))
    result = do_switching(engine, 100, (0, 0), 1, [])
    assert result == ('poly', 1)
    engine.assert_called_once_with(100, (0, 0), 1, [])


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
        # 1 means flagged (invalid), 0 means valid.
        # Result should be list of ranges where value is 1.
        # row 0: [1, 3]
        # row 1: [0, 1], [3, 4]
        result = heuristic_poly._BaselineFitParamConfig__convert_flags_to_masklist(flags)
        assert result == [[[1, 2]], [[0, 0], [3, 3]]]

    def test_dummy_baseline_param(self, heuristic_poly):
        dummy = heuristic_poly._dummy_baseline_param(10, 1)
        assert dummy[BLP.ROW] == 10
        assert dummy[BLP.POL] == 1
        assert dummy[BLP.MASK] == ''
        assert dummy[BLP.FUNC] == 'poly'

    def test_get_fit_param_poly(self, heuristic_poly):
        edge = fitorder.EdgeChannels(0, 0)
        result = heuristic_poly._get_fit_param(polyorder=2, nchan=100, edge=edge, nchan_without_edge=100,
                                               nchan_masked=0, masklist=[])
        assert result[BLP.FUNC] == 'poly'
        assert result[BLP.ORDER] == 2

    def test_get_fit_param_cspline(self, heuristic_cspline):
        edge = fitorder.EdgeChannels(0, 0)
        result = heuristic_cspline._get_fit_param(polyorder=2, nchan=100, edge=edge, nchan_without_edge=100,
                                                  nchan_masked=0, masklist=[])
        assert result[BLP.FUNC] == 'cspline'
        assert result[BLP.NPIECE] == 2
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

        # Mock blparam file writing
        m_open = mock_open()

        with patch('pipeline.hsd.heuristics.baselineparamconfig.open', m_open):
            result = heuristic_poly.calculate(
                datatable=mock_datatable,
                ms=mock_ms,
                rowmap={0: 0, 1: 1},
                antenna_id=0,
                field_id=0,
                spw_id=0,
                fit_order='automatic',
                edge=(5, 5),
                deviation_mask=None,
                blparam='test.blparam'
            )

        assert result == 'test.blparam'
        m_open.assert_called_with('test.blparam', 'a')
        # Check that we wrote something to the file
        m_open().write.assert_called()
