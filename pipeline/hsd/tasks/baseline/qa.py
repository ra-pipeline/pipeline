"""QA score calculation for baseline subtraction task."""
import os
from typing import TYPE_CHECKING, List, Optional, Union

import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.pipelineqa as pqa
import pipeline.infrastructure.renderer.logger as logger
import pipeline.infrastructure.utils as utils
import pipeline.qa.scorecalculator as qacalc

from ..common import compress
from . import baseline

if TYPE_CHECKING:
    from pipeline.infrastructure.launcher import Context

LOG = logging.get_logger(__name__)


class SDBaselineQAHandler(pqa.QAPlugin):
    """QA handler for baseline subtraction task."""

    result_cls = baseline.SDBaselineResults
    child_cls = None

    def handle(self, context: 'Context', result: result_cls) -> None:
        """Compute QA score for baseline subtraction task.

        QA scoring is performed based on the following metric:

            - Flatness of spectral baseline

        Scores and associated metrics are attached to the results instance.

        Args:
            context: Pipeline context
            result: Result instance of baseline subtraction task
        """
        scores = []
        for qstat in result.outcome['baseline_quality_stat']:
            scores.append(qacalc.score_sd_baseline_quality(qstat.vis, qstat.field, qstat.ant,
                                                           qstat.spw, qstat.pol, qstat.stat))
        result.qa.pool.extend(scores)


def _get_plot(plots: List[logger.Plot], figfile: str) -> Optional[Union[compress.CompressedObj, logger.Plot]]:
    """
    Return Plot instance that matches figure file name.

    Args:
        plots: A list of plot objects
        figfile: The name of figure file
    Returns:
        Plot instance. Returns None if no match is found.
    """
    for p in plots:
        if isinstance(p, compress.CompressedObj):
            p = p.decompress()
        if p.basename == os.path.basename(figfile):
            return p
    return None


class SDBaselineListQAHandler(pqa.QAPlugin):
    """QA handler to handle list of results."""

    result_cls = basetask.ResultsList
    child_cls = baseline.SDBaselineResults

    def handle(self, context: 'Context', result: result_cls) -> None:
        """Compute QA score for baseline subtraction task.

        Collect and join QA scores from results instances included in the
        ResultsList instance received as argument, result, and attach them to
        the result.

        Args:
            context: Pipeline context
            result: ResultsList instance
        """
        # collate the QAScores from each child result, pulling them into our
        # own QAscore list
        collated = utils.flatten([r.qa.pool for r in result])
        result.qa.pool[:] = collated
