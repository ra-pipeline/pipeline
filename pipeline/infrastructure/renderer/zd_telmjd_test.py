"""Regression test for compute_zd_telmjd_for_ms.

Records exact output values from main at commit c79f0ba71 to guard against
regressions when optimising the CASA measures-based implementation.

Updated for PIPE-3189: timestamps are now decimated to ~1s resolution to
avoid the unnecessarily dense SQLD sampling grid.
"""
import datetime

import pytest

from pipeline.infrastructure import casa_tools
from pipeline.infrastructure.tablereader import MeasurementSetReader
from pipeline.infrastructure.renderer.htmlrenderer import compute_zd_telmjd_for_ms

MS_NAME = casa_tools.utils.resolve(
    "pl-unittest/uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.ms"
)

# Expected zenith-distance values (degrees) after 1s decimation (PIPE-3189).
# fmt: off
_ZDS = [
    22.674321246538103,
    22.674773638800218,
    22.675226987505773,
    22.675681291610363,
    22.67613655154938,
    22.677393444930132,
    22.677852288984226,
    22.678312088097567,
    22.678772843463832,
    22.67923455377173,
    22.680509183393994,
    22.68097447659696,
    22.681440724457733,
    22.68190792767756,
    22.68237608594386,
    22.68825856682092,
    22.68867934176151,
    22.689100848825053,
    22.689523084824845,
    22.689946052608132,
    22.690369749239522,
    22.690794177840203,
    22.691219335995385,
    22.691645224455133,
    22.6920718434438,
    22.69249919292144,
    22.69292727124929,
    22.693356081582145,
    22.693785620144723,
    22.694215890099983,
    22.69464688980339,
    22.695078619480597,
    22.695511079089847,
    22.695944268858895,
    22.69637818712668,
    22.69681283709108,
    22.697248215196414,
    22.697684324107087,
    22.698121161611056,
    22.69855872983959,
    22.698997026846037,
    22.699436054223632,
    22.699875810565366,
    22.70031629664852,
    22.700757511608074,
    22.701199457324204,
    22.701642130454502,
    22.70208553425867,
    22.702529667041908,
    22.70297452875998,
    22.703420119923308,
    22.703866439934547,
    22.70431348874919,
    22.704761267995085,
    22.70520977428568,
]
# fmt: on

_TELMJDS = [
    "2017-09-11T06:22:06.192000+00:00",
    "2017-09-11T06:22:07.344000+00:00",
    "2017-09-11T06:22:08.496000+00:00",
    "2017-09-11T06:22:09.648000+00:00",
    "2017-09-11T06:22:10.800000+00:00",
    "2017-09-11T06:22:13.968000+00:00",
    "2017-09-11T06:22:15.120000+00:00",
    "2017-09-11T06:22:16.271999+00:00",
    "2017-09-11T06:22:17.424000+00:00",
    "2017-09-11T06:22:18.576000+00:00",
    "2017-09-11T06:22:21.743999+00:00",
    "2017-09-11T06:22:22.896000+00:00",
    "2017-09-11T06:22:24.048000+00:00",
    "2017-09-11T06:22:25.200000+00:00",
    "2017-09-11T06:22:26.352000+00:00",
    "2017-09-11T06:22:40.632001+00:00",
    "2017-09-11T06:22:41.639999+00:00",
    "2017-09-11T06:22:42.648001+00:00",
    "2017-09-11T06:22:43.655999+00:00",
    "2017-09-11T06:22:44.664001+00:00",
    "2017-09-11T06:22:45.671999+00:00",
    "2017-09-11T06:22:46.680000+00:00",
    "2017-09-11T06:22:47.688000+00:00",
    "2017-09-11T06:22:48.696000+00:00",
    "2017-09-11T06:22:49.704000+00:00",
    "2017-09-11T06:22:50.712001+00:00",
    "2017-09-11T06:22:51.719999+00:00",
    "2017-09-11T06:22:52.728001+00:00",
    "2017-09-11T06:22:53.735999+00:00",
    "2017-09-11T06:22:54.744000+00:00",
    "2017-09-11T06:22:55.752000+00:00",
    "2017-09-11T06:22:56.760000+00:00",
    "2017-09-11T06:22:57.768000+00:00",
    "2017-09-11T06:22:58.776001+00:00",
    "2017-09-11T06:22:59.783999+00:00",
    "2017-09-11T06:23:00.792001+00:00",
    "2017-09-11T06:23:01.800000+00:00",
    "2017-09-11T06:23:02.808001+00:00",
    "2017-09-11T06:23:03.815999+00:00",
    "2017-09-11T06:23:04.824000+00:00",
    "2017-09-11T06:23:05.831999+00:00",
    "2017-09-11T06:23:06.840000+00:00",
    "2017-09-11T06:23:07.848000+00:00",
    "2017-09-11T06:23:08.856000+00:00",
    "2017-09-11T06:23:09.863999+00:00",
    "2017-09-11T06:23:10.872001+00:00",
    "2017-09-11T06:23:11.879999+00:00",
    "2017-09-11T06:23:12.888000+00:00",
    "2017-09-11T06:23:13.896000+00:00",
    "2017-09-11T06:23:14.904000+00:00",
    "2017-09-11T06:23:15.912000+00:00",
    "2017-09-11T06:23:16.920000+00:00",
    "2017-09-11T06:23:17.927999+00:00",
    "2017-09-11T06:23:18.936001+00:00",
    "2017-09-11T06:23:19.943999+00:00",
]


@pytest.fixture(scope='module')
def ms():
    return MeasurementSetReader.get_measurement_set(MS_NAME)


@pytest.mark.unit
class TestZdTelmjd:
    """Verify that compute_zd_telmjd_for_ms produces expected values."""

    def test_zd_values(self, ms):
        result = compute_zd_telmjd_for_ms(ms)
        field = result[3]
        # Tolerance absorbs CASA measures-data refreshes: the shared measurespath
        # geodetic tables were updated on 2026-10-05 and shifted every ZD by a
        # constant ~2.1e-08 deg (this test also fails on unmodified main then).
        # rel=1e-5 is ~10,000x that drift yet still 17x tighter than the ~4e-3 deg
        # that a one-second timestamp error would produce, so it keeps catching
        # real regressions. Timestamps themselves are asserted exactly in
        # test_telmjd_exact, which measures data cannot perturb.
        for i, (actual, expected) in enumerate(zip(field['zd'], _ZDS)):
            assert actual == pytest.approx(expected, rel=1e-5), (
                f"zd[{i}] mismatch: {actual:.16f} != {expected:.16f}, "
                f"diff={abs(actual-expected):.2e}"
            )

    def test_field_count(self, ms):
        result = compute_zd_telmjd_for_ms(ms)
        assert len(result) == 1

    def test_timestamp_count(self, ms):
        result = compute_zd_telmjd_for_ms(ms)
        assert len(result[3]['zd']) == 55
        assert len(result[3]['telmjd']) == 55

    def test_telmjd_exact(self, ms):
        result = compute_zd_telmjd_for_ms(ms)
        field = result[3]
        expected_dts = [
            datetime.datetime.fromisoformat(s)
            for s in _TELMJDS
        ]
        for i, (actual, expected) in enumerate(zip(field['telmjd'], expected_dts)):
            assert actual == expected, (
                f"telmjd[{i}] exact mismatch: {actual!r} != {expected!r}"
            )
