import pytest
from pipeline.hsd.tasks.baseline.worker import (
    SerialBaselineSubtractionWorker as worker,
    BaselineFitParamConfig,

)


SPWS = [17, 19, 23]
DEF = "cspline"
AUTO = "automatic"

# Tests for build_fitting_configuration
@pytest.mark.parametrize(
    "inp, expected, should_raise",
    [
        # valid inputs
        (
                {17: DEF,      19: DEF,      23: DEF},
                {17: "cspline", 19: "cspline", 23: "cspline"},
                False
        ),
        (
                {17: "poly",   19: "poly",   23: "poly"},
                {17: "poly",   19: "poly",   23: "poly"},
                False
        ),
        (
                {17: DEF,       19: DEF,       23: "poly"},
                {17: "cspline", 19: "cspline", 23: "poly"},
                False
        ),
        (
                {17: "poly",  19: "cspline",  23: "poly"},
                {17: "poly",  19: "cspline",  23: "poly"},
                False
        ),
(
                {17: "poly",  19: "cspline",  23: "sinusoid"},
                {17: "poly",  19: "cspline",  23: "sinusoid"},
                False
        ),
        # error inputs
        (
                "badfunc",
                ValueError,
                True
        ),
        (
                {19: "invalid"},
                ValueError,
                True
        ),
    ],
)
def test_build_fitting_configuration(inp, expected, should_raise):
    if should_raise:
        with pytest.raises(expected):
            worker.build_fitting_configuration(real_spw_id_list=SPWS, fit_function=inp)
        return
    cfg = worker.build_fitting_configuration(real_spw_id_list=SPWS, fit_function=inp)
    assert isinstance(cfg, dict) and set(cfg.keys()) == set(SPWS)
    assert all(isinstance(v, BaselineFitParamConfig) for v in cfg.values())
    plain = {k: v.fitfunc.blfunc for k, v in cfg.items()}
    assert plain == expected


# Tests for get_fit_order_dict
@pytest.mark.parametrize(
    "inp, expected, should_raise",
    [
        # valid inputs
        (None,             {17: AUTO, 19: AUTO, 23: AUTO},   False),
        (2,                {17: 2,    19: 2,    23: 2},      False),
        (-1,               {17: AUTO, 19: AUTO, 23: AUTO},   False),
        ({},               {17: AUTO, 19: AUTO, 23: AUTO},   False),
        ("automatic",      {17: AUTO, 19: AUTO, 23: AUTO},   False),
        ({"19": -1},       {17: AUTO, 19: AUTO, 23: AUTO},   False),
        ({17: 2, 19: -1},
                          {17: 2,     19: AUTO, 23: AUTO},   False),
        ({17: 0, 19: 3, 23: 5},
                          {17: 0,    19: 3,    23: 5},       False),
        # error inputs
        ("bad",            ValueError,                       True),
        (1.5,              TypeError,                        True),
    ],
)
def test_get_fit_order_dict(inp, expected, should_raise):
    if should_raise:
        with pytest.raises(expected):
            worker.get_fit_order_dict(inp, SPWS)
        return
    cfg = worker.get_fit_order_dict(inp, SPWS)
    assert isinstance(cfg, dict) and set(cfg.keys()) == set(SPWS)
    assert cfg == expected

@pytest.mark.parametrize(
    "inp, expected, should_raise",
    [
        ((17, "sinusoid", [3, 5, 7], False),
        [3, 5, 7],
        False),
    ]
)
def test_configure_wave_number(inp, expected, should_raise):

    spw_id, fit_function, wave_number, switchpoly = inp
    heuristic = {
        spw_id: BaselineFitParamConfig(
            fitfunc=fit_function,
            switchpoly=switchpoly
        )
    }

    worker.configure_wave_number(heuristic, wave_number)

    assert heuristic[spw_id].wave_number == expected


