import os

import numpy as np
import pytest

import pipeline.hsd.heuristics.pointing_outlier as pointing_outlier
import pipeline.infrastructure.casa_tools as casa_tools

testdata_dir = casa_tools.utils.resolve("pl-unittest/sd-pointing-outlier")


@pytest.mark.parametrize(
    "testcase",
    [
        os.path.join(testdata_dir, x) for x in [
            "pointing_outlier_testcase_PRTSPR-59625.npz",
            "pointing_outlier_testcase_PRTSPR-60303.npz",
            "pointing_outlier_testcase_PRTSPR-64636.npz",
            "pointing_outlier_testcase_PRTSPR-70674.npz",
            "pointing_outlier_testcase_PRTSPR-77519.npz",
            "pointing_outlier_testcase_PRTSPR-77933.npz",
            "pointing_outlier_testcase_PRTSPR-79274.npz",
            "pointing_outlier_testcase_PRTSPR-80202.npz",
        ]
    ]
)
def test_pointing_outlier_heuristics(testcase):
    """Test pointing outlier heuristics."""
    with np.load(testcase) as data:
        x = data["x"]
        y = data["y"]
        expected_outliers = data["outliers"]

    heuristics = pointing_outlier.PointingOutlierHeuristics()

    # first process the data with outliers
    heuristics_result = heuristics('ICRS', x, y)
    outliers = np.where(np.logical_not(heuristics_result.mask))[0]
    assert len(outliers) == len(expected_outliers)
    assert np.all(outliers == expected_outliers)

    # then exclude outliers and re-process
    x2 = x[heuristics_result.mask]
    y2 = y[heuristics_result.mask]
    heuristics_result2 = heuristics('ICRS', x2, y2)
    # all data must be valid
    assert np.all(heuristics_result2.mask)
