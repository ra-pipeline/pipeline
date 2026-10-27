"""Unit tests for the qa/scorecalculator.py module.

Covers line range and channel heuristics, QA score calculations, the log_qa
decorator, and behavior when DISABLE_WEBLOG or DISABLE_QA is enabled.
"""

from unittest.mock import MagicMock, patch

import pytest

import pipeline.infrastructure.pipelineqa as pqa
import pipeline.qa.scorecalculator as qacalc
from pipeline.infrastructure import basetask


@pytest.mark.parametrize(
    'lines, expected',
    [
        ([(10, 5, True)], [(8, 13)]),
        ([(10, 5, False)], []),
        # round-off tests
        ([(5.0, 10, True)], [(0, 10)]),
        ([(5.2, 10.1, True)], [(0, 10)]),
        ([(5.6, 10.1, True)], [(1, 11)])
    ]
)
def test_get_line_ranges(lines: list[tuple[int, int, bool]], expected: list[tuple[int, int]]):
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
    ]
)
def test_examine_sd_edge_lines(lines: list[tuple[int, int]], nchan: int, edge: tuple[int, int], expected: float):
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
    ]
)
def test_examine_sd_wide_lines(lines: list[tuple[int, int]], nchan: int, edge: tuple[int, int], expected: float):
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
    ]
)
def test_channel_ranges_for_image(edge: tuple[int, int], nchan: int, sideband: int, ranges: list[tuple[int, int]], expected: list[tuple[int, int]]):
    ranges_image = qacalc.channel_ranges_for_image(edge, nchan, sideband, ranges)
    assert ranges_image == expected


# --- Tests for log_qa decorator, DISABLE_WEBLOG, and DISABLE_QA handling ---


@pytest.mark.parametrize(
    'return_val, expected_infos, expected_warns',
    [
        # Single score: optimal vs suboptimal
        (pqa.QAScore(1.0, longmsg='Opt', shortmsg='Opt'), ['Opt'], []),
        (pqa.QAScore(0.5, longmsg='Sub', shortmsg='Sub'), [], ['Sub']),
        # List of scores: verify each score is logged rather than only the first
        ([pqa.QAScore(1.0, longmsg='S1'), pqa.QAScore(0.3, longmsg='S2')], ['S1'], ['S2']),
        # Tuple with non-QAScore items
        ((pqa.QAScore(0.95, longmsg='TupleOpt'), 123, 'extra'), ['TupleOpt'], []),
        # Empty collections, None, and non-score returns
        ([], [], []),
        ((), [], []),
        (None, [], []),
        (0.85, [], []),
    ],
)
def test_log_qa_weblog_disabled(return_val, expected_infos, expected_warns, monkeypatch):
    monkeypatch.setattr(basetask, 'DISABLE_WEBLOG', True)

    @qacalc.log_qa
    def dummy(self):
        return return_val

    with patch.object(qacalc.LOG, 'info') as mock_info, patch.object(qacalc.LOG, 'warning') as mock_warn:
        assert dummy(None) == return_val
        assert [c.args[0] for c in mock_info.call_args_list] == expected_infos
        assert [c.args[0] for c in mock_warn.call_args_list] == expected_warns


def test_log_qa_weblog_enabled(monkeypatch):
    monkeypatch.setattr(basetask, 'DISABLE_WEBLOG', False)
    score = pqa.QAScore(0.5, longmsg='Sub', shortmsg='Sub')

    @qacalc.log_qa
    def dummy(self):
        return score

    with patch.object(qacalc.LOG, 'info') as mock_info, patch.object(qacalc.LOG, 'warning') as mock_warn:
        assert dummy(None) is score
        mock_info.assert_not_called()
        mock_warn.assert_not_called()


def test_score_amp_vs_time_plots_weblog_disabled(monkeypatch):
    monkeypatch.setattr(basetask, 'DISABLE_WEBLOG', True)
    assert qacalc.score_amp_vs_time_plots(None, None) == []


class DummyResults(basetask.Results):
    def __init__(self):
        super().__init__()
        self.stage_number = 1
        self.timestamps = None
        self.inputs = {}

    def merge_with_context(self, context):
        pass


@pytest.mark.parametrize('disable_qa, should_call', [(True, False), (False, True)])
def test_results_accept_respects_disable_qa(disable_qa, should_call, monkeypatch):
    monkeypatch.setattr(basetask, 'DISABLE_WEBLOG', True)
    monkeypatch.setattr(basetask, 'DISABLE_QA', disable_qa)

    context = MagicMock()
    context.results = []
    results = DummyResults()

    with (
        patch.object(pqa.qa_registry, 'do_qa') as mock_do_qa,
        patch.object(
            basetask.ResultsProxy, 'write', autospec=True, side_effect=lambda self, r: setattr(self, 'uuid', r.uuid)
        ),
        patch('pipeline.infrastructure.basetask.write_pipeline_casa_tasks'),
        patch('pipeline.infrastructure.eventbus.send_message'),
    ):
        results.accept(context)
        if should_call:
            mock_do_qa.assert_called_once_with(context, results)
        else:
            mock_do_qa.assert_not_called()
