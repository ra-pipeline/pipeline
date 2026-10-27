"""QA score handlers for k2jycal task."""
from __future__ import annotations

import collections.abc
from typing import TYPE_CHECKING

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.pipelineqa as pqa
import pipeline.infrastructure.utils as utils
from pipeline.hsd.tasks.common import qautils
from . import k2jycal

if TYPE_CHECKING:
    from pipeline.infrastructure.launcher import Context
    from pipeline.infrastructure.basetask import ResultsList

LOG = infrastructure.logging.get_logger(__name__)


class SDK2JyCalQAHandler(pqa.QAPlugin):
    """Class to handle QA score for k2jycal result."""

    result_cls = k2jycal.SDK2JyCalResults
    child_cls = None

    def __init__(self):
        """
        Create SDK2JyCalQAHandler instance
        """
        # register the properties for 'score_sd_jyperk_factors' 'and score_sd_jkperk_dbaccess'
        keys = ['vis']
        for metric_name in ['score_sd_jyperk_factors','score_sd_jkperk_dbaccess']:
            qautils.registry.register_longmsg_keys(metric_name, keys)
            qautils.registry.register_keys_to_aggregate(metric_name, keys)

    def handle(self, context: Context, result: k2jycal.SDK2JyCalResults) -> None:
        """Evaluate QA score for k2jycal result.

        Score is 0.0 if

            - there is missing Jy/K factor, or,
            - accessed Jy/K DB and failed.

        Args:
            context: Pipeline context (not used)
            result: SDK2JyCalResults instance
        """
        is_missing_factor = (not result.all_ok)

        if is_missing_factor:
            shortmsg = "Jy/K factors are missing for some data. They will stay with Kelvin unit."
        else:
            shortmsg = "Jy/K factors are found for all data"
        longmsg = shortmsg + (" in "+result.vis if result.vis is not None else "")
        score = 0.0 if is_missing_factor else 1.0

        selection = pqa.TargetDataSelection(vis={result.vis} if result.vis else set())

        origin = pqa.QAOrigin(metric_name='score_sd_jyperk_factors',
                              metric_score=score,
                              metric_units='Jy/K factors status')

        scores = [pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, applies_to=selection, origin=origin)]

        # PIPE-384 lower the score to 0.8 if DB access was failed
        if result.dbstatus is not None:
            # the task attempted to access the DB
            if result.dbstatus is True:
                statusstr = 'succeeded'
                score = 1.0
            else:
                statusstr = 'failed'
                score = 0.0
                #score = 0.8
            shortmsg = "Jy/K DB access has {}".format(statusstr)
            longmsg = shortmsg + " for " + (result.vis if result.vis is not None else "input vis")

            selection = pqa.TargetDataSelection(vis={result.vis} if result.vis else set())

            origin = pqa.QAOrigin(metric_name='score_sd_jkperk_dbaccess',
                                  metric_score=score,
                                  metric_units='Access to Jy/K DB')

            scores.append(pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, applies_to=selection, origin=origin))

        # reformat the messages and append to result.qa.pool
        formatter = qautils.QAScoreFormatter()
        for qascore in scores:
            formatter.update_longmsg(qascore)

        result.qa.pool.extend(scores)


class SDK2JyCalListQAHandler(pqa.QAPlugin):
    """Class to handle QA score for a list of k2jycal results."""

    result_cls = collections.abc.Iterable
    child_cls = k2jycal.SDK2JyCalResults

    def handle(self, context: Context, result: ResultsList) -> None:
        """Evaluate QA score for a list of k2jycal results.

        Args:
            context: Pipeline context (not used)
            result: list of SDK2JyCalResults instances
        """
        # collate the QAScores from each child result, pulling them into our
        # own QAscore list
        collated = utils.flatten([r.qa.pool for r in result])
        result.qa.pool[:] = collated
