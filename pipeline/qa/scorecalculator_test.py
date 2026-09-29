"""scorecalculator_test.py : Unit tests for "qa/scorecalculator.py".

Unit tests for "qa/scorecalculator.py"
"""

import pytest

import pipeline.qa.scorecalculator as qacalc


@pytest.mark.parametrize(
    'lines, expected',
    [
        ([(10, 5, True)], [(8, 13)]),
        ([(10, 5, False)], []),
        # round-off tests
        ([(5.0, 10, True)], [(0, 10)]),
        ([(5.2, 10.1, True)], [(0, 10)]),
        ([(5.6, 10.1, True)], [(1, 11)]),
    ],
)
def test_get_line_ranges(lines: list[tuple[int, int, bool]], expected: list[tuple[int, int]]):
    """Test get_line_ranges helper function."""
    line_ranges = qacalc.get_line_ranges(lines)
    assert line_ranges == expected


@pytest.mark.parametrize(
    'lines, nchan, edge, expected',
    [
        # line not extend to the edge
        ([(1020, 1030)], 2048, (0, 0), False),
        ([(1, 11)], 1024, (0, 0), False),
        ([(800, 1022)], 1024, (0, 0), False),
        # narrow edge lines
        ([(0, 10)], 1024, (0, 0), True),
        ([(0, 203)], 1024, (0, 0), True),
        ([(990, 1023)], 1024, (0, 0), True),
        ([(-10, 200)], 1024, (0, 0), True),
        ([(900, 2047)], 1024, (0, 0), True),
        # wide edge lines
        ([(0, 204)], 1024, (0, 0), True),
        ([(800, 1023)], 1024, (0, 0), True),
        ([(800, 1024)], 1024, (0, 0), True),
        ([(0, 1023)], 1024, (0, 0), True),
        ([(-10, 210)], 1024, (0, 0), True),
        ([(800, 2047)], 1024, (0, 0), True),
        # edge excuded
        ([(2, 11)], 1024, (2, 0), True),
        ([(2, 11)], 1024, (1, 0), False),
        ([(800, 1021)], 1024, (0, 2), True),
        ([(800, 1021)], 1024, (0, 1), False),
    ],
)
def test_examine_sd_edge_lines(lines: list[tuple[int, int]], nchan: int, edge: tuple[int, int], expected: float):
    """Test examine_sd_edge_lines helper function."""
    score = qacalc.examine_sd_edge_lines(lines, nchan, edge)
    assert score == expected


@pytest.mark.parametrize(
    'lines, nchan, edge, expected',
    [
        # single narrow line
        ([(1020, 1030)], 2048, (0, 0), False),
        ([(500, 840)], 1024, (0, 0), False),
        ([(1000, 1681)], 2048, (0, 0), False),
        # single wide line that lowers QA score
        ([(0, 1023)], 1024, (0, 0), True),
        ([(0, 2047)], 1024, (0, 0), True),
        ([(500, 841)], 1024, (0, 0), True),
        ([(1000, 1682)], 2048, (0, 0), True),
        # multiple lines, less coverage than threshold
        ([(100, 199), (300, 399), (500, 599), (700, 740)], 1024, (0, 0), False),
        # multiple lines, enough coverage to lower QA score
        ([(100, 199), (300, 399), (500, 599), (700, 741)], 1024, (0, 0), True),
        # edge excluded
        ([(501, 840)], 1024, (3, 2), True),
        ([(501, 840)], 1024, (5, 0), True),
        ([(501, 840)], 1024, (0, 5), True),
    ],
)
def test_examine_sd_wide_lines(lines: list[tuple[int, int]], nchan: int, edge: tuple[int, int], expected: float):
    """Test examine_sd_wide_lines helper function."""
    score = qacalc.examine_sd_wide_lines(lines, nchan, edge)
    assert score == expected


@pytest.mark.parametrize(
    'edge, nchan, sideband, ranges, expected',
    [
        ((0, 0), 16, 1, [(3, 5), (9, 12)], [(3, 5), (9, 12)]),
        ((0, 0), 16, -1, [(3, 5), (9, 12)], [(3, 6), (10, 12)]),
        ((1, 0), 16, 1, [(3, 5), (9, 12)], [(2, 4), (8, 11)]),
        ((1, 1), 16, 1, [(3, 5), (9, 12)], [(2, 4), (8, 11)]),
        ((1, 0), 16, -1, [(3, 5), (9, 12)], [(3, 6), (10, 12)]),
        ((1, 1), 16, -1, [(3, 5), (9, 12)], [(2, 5), (9, 11)]),
    ],
)
def test_channel_ranges_for_image(
    edge: tuple[int, int], nchan: int, sideband: int, ranges: list[tuple[int, int]], expected: list[tuple[int, int]]
):
    """Test channel_ranges_for_image helper function."""
    ranges_image = qacalc.channel_ranges_for_image(edge, nchan, sideband, ranges)
    assert ranges_image == expected


def test_scorecalculator_exports():
    """Verify that scorecalculator re-exports all expected symbols."""
    assert len(qacalc.__all__) == 117
    for name in qacalc.__all__:
        assert hasattr(qacalc, name), f'Missing symbol on scorecalculator: {name}'


def test_submodule_exports():
    """Verify that all submodule symbols are present both in the submodule and the facade."""
    from pipeline.qa import common_scores, hif_scores, hifa_scores, hifv_scores, hsd_scores

    submodules = [common_scores, hif_scores, hifa_scores, hifv_scores, hsd_scores]
    total_symbols = 0
    for mod in submodules:
        assert hasattr(mod, '__all__')
        assert len(mod.__all__) > 0
        total_symbols += len(mod.__all__)
        for sym in mod.__all__:
            assert hasattr(mod, sym), f'{mod.__name__} missing symbol {sym}'
            assert getattr(qacalc, sym) is getattr(mod, sym), (
                f'{sym} on qacalc is not identical to {mod.__name__}.{sym}'
            )
    assert total_symbols == len(qacalc.__all__)


def test_linear_score_calculation():
    """Verify linear_score behavior from common_scores and qacalc."""
    from pipeline.qa.common_scores import linear_score

    assert linear_score(0.0, 0.0, 1.0, 0.0, 1.0) == 0.0
    assert linear_score(0.5, 0.0, 1.0, 0.0, 1.0) == 0.5
    assert linear_score(1.0, 0.0, 1.0, 0.0, 1.0) == 1.0
    assert qacalc.linear_score(0.5, 0.0, 1.0, 0.0, 1.0) == 0.5
