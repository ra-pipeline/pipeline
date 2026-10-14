import numpy as np
import pytest

from pipeline.domain.datatype import DataType
from pipeline.h.heuristics.importdata import get_ms_data_types_from_history


@pytest.mark.parametrize("msgs, expected_dt_per_col, expected_dt_per_src_spw", [
    (
        np.array([
            "some irrelevant log",
            "data_type_per_column = {'RAW': 'DATA'}",
            "data_types_per_source_and_spw = {('2039540-005735', 0): ['RAW'], ('2039540-005735', 1): ['RAW']}",
            "some irrelevant log",
            "data_type_per_column = {'REGCAL_CONTLINE_SCIENCE': 'DATA', 'SELFCAL_CONTLINE_SCIENCE': 'CORRECTED_DATA'}",
            "data_types_per_source_and_spw = {('2039540-005735', 0): ['REGCAL_CONTLINE_SCIENCE', 'REGCAL_CONTLINE_SCIENCE'], ('2039540-005735', 1): ['REGCAL_CONTLINE_SCIENCE', 'SELFCAL_CONTLINE_SCIENCE']}",
            "some irrelevant log",
        ]),
        {
            DataType.REGCAL_CONTLINE_SCIENCE: 'DATA',
            DataType.SELFCAL_CONTLINE_SCIENCE: 'CORRECTED_DATA'
        },
        {
            ('2039540-005735', 0): [DataType.REGCAL_CONTLINE_SCIENCE, DataType.REGCAL_CONTLINE_SCIENCE],
            ('2039540-005735', 1): [DataType.REGCAL_CONTLINE_SCIENCE, DataType.SELFCAL_CONTLINE_SCIENCE]
        }
    ),

    (
        np.array([
            "some irrelevant log",
            "data_type_per_column = {'RAW': 'DATA'}",
            "data_types_per_source_and_spw = {('1331+305=3C286', 0): ['RAW'], ('J1407+2827', 0): ['RAW'], ('J1820-2528', 0): ['RAW'], ('J1819.3-2525', 0): ['RAW']}",
            "some irrelevant log",
            "data_type_per_column = {'RAW': 'DATA', 'REGCAL_CONTLINE_ALL': 'CORRECTED_DATA'}",
            "data_types_per_source_and_spw = {('1331+305=3C286', 0): ['RAW', 'REGCAL_CONTLINE_ALL'], ('J1407+2827', 0): ['RAW', 'REGCAL_CONTLINE_ALL'], ('J1820-2528', 0): ['RAW', 'REGCAL_CONTLINE_ALL'], ('J1819.3-2525', 0): ['RAW', 'REGCAL_CONTLINE_ALL']}",
            "some irrelevant log",
        ]),
        {
            DataType.RAW: 'DATA',
            DataType.REGCAL_CONTLINE_ALL: 'CORRECTED_DATA'
        },
        {
            ('1331+305=3C286', 0): [DataType.RAW, DataType.REGCAL_CONTLINE_ALL],
            ('J1407+2827', 0): [DataType.RAW, DataType.REGCAL_CONTLINE_ALL],
            ('J1820-2528', 0): [DataType.RAW, DataType.REGCAL_CONTLINE_ALL],
            ('J1819.3-2525', 0): [DataType.RAW, DataType.REGCAL_CONTLINE_ALL],
        }
    )
])
def test_get_ms_data_types_with_valid_history(msgs, expected_dt_per_col, expected_dt_per_src_spw):
    """Test retrieval of DataType info from MS HISTORY entries."""

    dt_per_col, dt_per_src_spw = get_ms_data_types_from_history(msgs)

    assert dt_per_col == expected_dt_per_col
    assert dt_per_src_spw == expected_dt_per_src_spw
