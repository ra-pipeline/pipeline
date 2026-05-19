from __future__ import annotations

import collections.abc
from typing import TYPE_CHECKING

import pipeline.infrastructure.pipelineqa as pqa
from pipeline import infrastructure
from pipeline.infrastructure import utils
from . import hanning

LOG = infrastructure.logging.get_logger(__name__)

if TYPE_CHECKING:
    from pipeline.infrastructure.api import Results
    from pipeline.infrastructure.launcher import Context


class HanningQAHandler(pqa.QAPlugin):
    result_cls = hanning.HanningResults
    child_cls = None
    generating_task = hanning.Hanning

    def handle(self, context: Context, result: Results) -> None:
        # Check if the hanningsmooth task was successful or not
        score1 = self._task_success(result.task_successful, result.qa_message)
        scores = [score1]

        result.qa.pool[:] = scores

    def _task_success(self, task_successful: bool, qa_message: str) -> pqa.QAScore:
        """
        Check whether task completed successfully.
        """
        score = 0.0
        if task_successful:
            score = 1.0

        origin = pqa.QAOrigin(metric_name='score_hanning',
                              metric_score=score,
                              metric_units='task success')

        return pqa.QAScore(score, longmsg=qa_message, shortmsg=qa_message, origin=origin)


class HanningListQAHandler(pqa.QAPlugin):
    """
    QA handler for a list containing HanningResults.
    """
    result_cls = collections.abc.Iterable
    child_cls = hanning.HanningResults
    generating_task = hanning.Hanning

    def handle(self, context: Context, result: Results) -> None:
        # collate the QAScores from each child result, pulling them into our
        # own QAscore list
        collated = utils.flatten([r.qa.pool[:] for r in result])
        result.qa.pool[:] = collated
        mses = [r.inputs['vis'] for r in result]
        longmsg = 'No missing target MS(s) for %s' % utils.commafy(mses, quotes=False, conjunction='or')
        result.qa.all_unity_longmsg = longmsg
