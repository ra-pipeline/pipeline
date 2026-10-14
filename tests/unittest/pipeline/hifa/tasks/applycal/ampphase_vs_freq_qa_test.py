from pathlib import Path

import pytest

from pipeline.infrastructure import casa_tools
from pipeline.infrastructure.tablereader import MeasurementSetReader
from pipeline.hifa.tasks.applycal.ampphase_vs_freq_qa import score_all_scans

# # Tests that depend on the pipeline-testdata repository
TEST_DATA_PATH = casa_tools.utils.resolve('pl-unittest/casa_data')
# Skip tests if CASA cannot resolve to an absolute path
skip_data_tests = not TEST_DATA_PATH.startswith('/')
# Create decorator with reason to skip tests
skip_if_no_data_repo = pytest.mark.skipif(
    skip_data_tests,
    reason="The repo pipeline-testdata is not set up for the tests"
)


MS_NAME_DC = casa_tools.utils.resolve("pl-unittest/uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small_target.ms")
SCAN_ID = 10
SPW_ID = 0


@skip_if_no_data_repo
def test_score_all_scans():
    ms = MeasurementSetReader.get_measurement_set(MS_NAME_DC)
    score = score_all_scans(ms, 'TARGET', flag_all=False, memory_gb=2.0, buffer_path=Path('.'), export_mswrappers=False)
    assert score == []
