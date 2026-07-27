from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest
from unittest.mock import patch

from pipeline.domain import Field, MeasurementSet, Source
from pipeline.infrastructure.displays.plotpointings import select_tsys_field

if TYPE_CHECKING:
    from collections.abc import Sequence


def make_source(id: int, name: str, fields: Sequence[Field]) -> Source:
    s = Source(source_id=id, name=name, direction={}, proper_motion={}, is_eph_obj=False, table_name="", avg_spacing="")
    s.fields = list(fields)
    for f in fields:
        f.source = s
    return s


def make_ms(name: str, array_name: str, sources: Sequence[Source]) -> MeasurementSet:
    all_fields = [f for s in sources for f in s.fields]
    ms = MeasurementSet(name=name)
    ms.array_name = array_name
    ms.fields = all_fields
    ms.sources = list(sources)
    return ms


# case builders (return (ms, src, gainfield_map, expected))
def case_same_id() -> tuple[MeasurementSet, Source, dict[str, str], Field]:
    f0 = Field(0, "J0108+0135", 0, np.ndarray(1), {})
    f0.intents = {"ATMOSPHERE", "PHASE", "WVR"}
    f1 = Field(1, "helms30", 1, np.ndarray(1), {})
    f1.intents = {"ATMOSPHERE", "TARGET"}
    ms = make_ms("test1.ms", "7M", [
        make_source(0, "J0108+0135", [f0]),
        make_source(1, "helms30", [f1]),
    ])
    return ms, f1.source, {"TARGET": "1"}, f1


def case_same_name() -> tuple[MeasurementSet, Source, dict[str, str], Field]:
    f0 = Field(0, "J1007-3333", 0, np.ndarray(1), {})
    f0.intents = {"ATMOSPHERE", "PHASE", "POINTING", "WVR"}
    f1 = Field(1, "NGC_2997", 1, np.ndarray(1), {})
    f1.intents = {"ATMOSPHERE"}
    f2 = Field(2, "NGC_2997", 1, np.ndarray(1), {})
    f2.intents = {"TARGET"}
    ms = make_ms("test2.ms", "12M", [
        make_source(0, "J1007-3333", [f0]),
        make_source(1, "NGC_2997", [f1, f2]),
    ])
    # Use field ID since both f1 and f2 share the same name; dict key would keep only the last
    return ms, f2.source, {"TARGET": "1"}, f1


def case_partial_name() -> tuple[MeasurementSet, Source, dict[str, str], Field]:
    f0 = Field(1, "24013+0488_OFF_0", 1, np.ndarray(1), {})
    f0.intents = {"ATMOSPHERE", "REFERENCE"}
    f1 = Field(2, "24013+0488", 2, np.ndarray(1), {})
    f1.intents = {"TARGET"}
    f2 = Field(3, "31946+0076_OFF_0", 3, np.ndarray(1), {})
    f2.intents = {"ATMOSPHERE", "REFERENCE"}
    f3 = Field(4, "31946+0076", 4, np.ndarray(1), {})
    f3.intents = {"TARGET"}
    ms = make_ms("test3.ms", "TP", [
        make_source(3, "24013+0488_OFF_0", [f0]),
        make_source(1, "24013+0488", [f1]),
        make_source(4, "31946+0076_OFF_0", [f2]),
        make_source(2, "31946+0076", [f3]),
    ])
    return ms, f1.source, {"TARGET": "24013+0488_OFF_0"}, f0


def case_no_valid_tsys_field() -> tuple[MeasurementSet, Source, dict[str, str], None]:
    f0 = Field(0, "J1007-3333", 0, np.ndarray(1), {})
    f0.intents = {"ATMOSPHERE", "PHASE", "POINTING", "WVR"}
    f1 = Field(1, "Jupiter", 1, np.ndarray(1), {})
    f1.intents = {"TARGET"}
    ms = make_ms("test4.ms", "12M", [
        make_source(0, "J1007-3333", [f0]),
        make_source(1, "Jupiter", [f1]),
    ])
    return ms, f1.source, {"TARGET": ""}, None


def case_double_quote_name() -> tuple[MeasurementSet, Source, dict[str, str], Field]:
    f0 = Field(0, '"J1007-3333"', 0, np.ndarray(1), {})
    f0.intents = {"ATMOSPHERE", "PHASE", "POINTING", "WVR"}
    f1 = Field(1, '"S Pav_OFF"', 1, np.ndarray(1), {})
    f1.intents = {"ATMOSPHERE"}
    f2 = Field(2, '"S Pav"', 1, np.ndarray(1), {})
    f2.intents = {"TARGET"}
    ms = make_ms("test5.ms", "12M", [
        make_source(0, '"J1007-3333"', [f0]),
        make_source(1, '"S Pav"', [f1, f2]),
    ])
    return ms, f2.source, {"TARGET": "1"}, f1


def _make_direction(ra: float, dec: float) -> dict:
    """Helper to build a minimal CASA direction dict."""
    return {"refer": "J2000", "m0": {"value": ra}, "m1": {"value": dec}}


def case_nearest_fallback() -> tuple[MeasurementSet, Source, dict[str, str], Field]:
    """No ID/name/partial match: function falls back to nearest Tsys field."""
    f_target = Field(0, "Jupiter", 0, np.ndarray(1), _make_direction(0.0, 0.0))
    f_target.intents = {"TARGET"}
    f_near = Field(1, "TsysNear", 1, np.ndarray(1), _make_direction(0.01, 0.0))
    f_near.intents = {"ATMOSPHERE"}
    f_far = Field(2, "TsysFar", 2, np.ndarray(1), _make_direction(0.5, 0.0))
    f_far.intents = {"ATMOSPHERE"}
    ms = make_ms("test6.ms", "12M", [
        make_source(0, "Jupiter", [f_target]),
        make_source(1, "TsysNear", [f_near]),
        make_source(2, "TsysFar", [f_far]),
    ])
    return ms, f_target.source, {"TARGET": "TsysNear,TsysFar"}, f_near


@pytest.fixture(
    params=[case_same_id, case_same_name, case_partial_name, case_no_valid_tsys_field, case_double_quote_name, case_nearest_fallback],
    ids=["same-id", "same-name", "partial-name", "no-valid-tsys-field", "double-quote-name", "nearest-fallback"],
)
def case(request) -> tuple[MeasurementSet, Source, dict[str, str], Field | None]:
    return request.param()


def test_select_tsys_field(case: tuple[MeasurementSet, Source, dict[str, str], Field | None]) -> None:
    """Test select_tsys_field for correct selections."""
    ms, source, gainfield_map, expected = case

    with patch("pipeline.infrastructure.displays.plotpointings.get_intent_to_tsysfield_map") as mock_map:
        mock_map.return_value = gainfield_map
        result = select_tsys_field(ms, source)
        assert result == expected
