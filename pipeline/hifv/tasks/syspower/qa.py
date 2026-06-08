import collections.abc

import pipeline.infrastructure.pipelineqa as pqa
import pipeline.infrastructure.utils as utils
import pipeline.qa.scorecalculator as qacalc
from pipeline import infrastructure

from . import syspower

LOG = infrastructure.logging.get_logger(__name__)


class SyspowerQAHandler(pqa.QAPlugin):
    result_cls = syspower.SyspowerResults
    child_cls = None
    generating_task = syspower.Syspower

    def handle(self, context, result):

        score = qacalc.score_syspowerdata(result.dat_common)

        result.qa.pool.append(score)


class SyspowerListQAHandler(pqa.QAPlugin):
    result_cls = collections.abc.Iterable
    child_cls = syspower.SyspowerResults

    def handle(self, context, result):
        # collate the QAScores from each child result, pulling them into our
        # own QAscore list
        collated = utils.flatten([r.qa.pool[:] for r in result])
        result.qa.pool.extend(collated)
