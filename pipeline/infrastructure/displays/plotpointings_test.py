from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

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


# case builders (return (ms, src, expected))
def case_same_id() -> tuple[MeasurementSet, Source, Field]:
    f0 = Field(0, "J0108+0135", 0, np.ndarray(1), {})
    f0.intents = {"ATMOSPHERE","PHASE","WVR"}
    f1 = Field(1, "helms30", 1, np.ndarray(1), {})
    f1.intents = {"ATMOSPHERE","TARGET"}
    ms = make_ms("test1.ms","7M",[
        make_source(0,"J0108+0135",[f0]),
        make_source(1,"helms30",[f1]),
    ])
    return ms, f1.source, f1


def case_same_name() -> tuple[MeasurementSet, Source, Field]:
    f0 = Field(0, "J1007-3333", 0, np.ndarray(1), {})
    f0.intents = {"ATMOSPHERE","PHASE","POINTING","WVR"}
    f1 = Field(1, "NGC_2997", 1, np.ndarray(1), {})
    f1.intents = {"ATMOSPHERE"}
    f2 = Field(2, "NGC_2997", 1, np.ndarray(1), {})
    f2.intents = {"TARGET"}
    ms = make_ms("test2.ms", "12M", [
        make_source(0, "J1007-3333", [f0]),
        make_source(1, "NGC_2997", [f1, f2]),
    ])
    return ms, f2.source, f1


def case_partial_name() -> tuple[MeasurementSet, Source, Field]:
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
    return ms, f1.source, f0


def case_no_valid_tsys_field() -> tuple[MeasurementSet, Source, Field | None]:
    f0 = Field(0, "J1007-3333", 0, np.ndarray(1), {})
    f0.intents = {"ATMOSPHERE", "PHASE", "POINTING", "WVR"}
    f1 = Field(1, "Jupiter", 1, np.ndarray(1), {})
    f1.intents = {"TARGET"}
    ms = make_ms("test4.ms", "12M", [
        make_source(0, "J1007-3333", [f0]),
        make_source(1, "Jupiter", [f1]),
    ])
    return ms, f1.source, None


def case_double_quote_name() -> tuple[MeasurementSet, Source, Field]:
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
    return ms, f2.source, f1


@pytest.fixture(
    params=[case_same_id, case_same_name, case_partial_name, case_no_valid_tsys_field, case_double_quote_name],
    ids=["same-id","same-name","partial-name","no-valid-tsys-field", "double-quote-name"],
)
def case(request) -> tuple[MeasurementSet, Source, Field | None]:
    return request.param()


def test_select_tsys_field(case: tuple[MeasurementSet, Source, Field | None]) -> None:
    """Test select_tsys_field for correct selections."""
    ms, source, expected = case
    if expected is None:
        with pytest.raises(LookupError):
            select_tsys_field(ms, source)
    else:
        assert select_tsys_field(ms, source) == expected
