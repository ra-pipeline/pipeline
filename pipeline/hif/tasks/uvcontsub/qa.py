import collections
import os

import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.pipelineqa as pqa
import pipeline.infrastructure.utils as utils
import pipeline.qa.scorecalculator as qacalc
from . import uvcontsub

LOG = logging.get_logger(__name__)

class UVcontSubQAHandler(pqa.QAPlugin):
    result_cls = uvcontsub.UVcontSubResults
    child_cls = None
    generating_task = uvcontsub.SerialUVcontSub

    def handle(self, context, result):

        scores = []

        if result.mitigation_error:
            scores.append(pqa.QAScore(0.0, longmsg='Size mitigation error. No continuum information available.',
                                      shortmsg='Size mitigation error'))
        else:
            scores.append(pqa.QAScore(1.0, longmsg='Continuum subtraction applied.', shortmsg=''))

        result.qa.pool.extend(scores)


class UVcontSubListQAHandler(pqa.QAPlugin):
    """
    QA handler for a list containing UVcontSubResults.
    """
    result_cls = collections.Iterable
    child_cls = uvcontsub.UVcontSubResults
    generating_task = uvcontsub.UVcontSub

    def handle(self, context, result):
        # collate the QAScores from each child result, pulling them into our
        # own QAscore list
        collated = utils.flatten([r.qa.pool for r in result])
        result.qa.pool[:] = collated
        mses = [r.inputs['vis'] for r in result]
        longmsg = 'No missing target MS(s) for %s' % utils.commafy(mses, quotes=False, conjunction='or')
        result.qa.all_unity_longmsg = longmsg
