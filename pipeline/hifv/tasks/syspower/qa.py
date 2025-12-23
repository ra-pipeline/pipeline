import collections

from pipeline import infrastructure
import pipeline.infrastructure.pipelineqa as pqa
import pipeline.infrastructure.utils as utils
import pipeline.qa.scorecalculator as qacalc

from . import syspower
from pipeline.infrastructure.utils.profiling import profile_io

LOG = infrastructure.logging.get_logger(__name__)


class SyspowerQAHandler(pqa.QAPlugin):
    result_cls = syspower.SyspowerResults
    child_cls = None
    generating_task = syspower.Syspower

    @profile_io(output_file="syspower_io_log.csv")
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
