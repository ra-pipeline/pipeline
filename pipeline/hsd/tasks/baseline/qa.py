"""QA score calculation for baseline subtraction task."""
import numpy
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

        QA scorering is performed based on the following metric:

            - Line detection: Whether or not any astronomical lines are detected
            - Flatness of spectral baseline

        Scores and associated metrics are attached to the results instance.

        Args:
            context: Pipeline context
            result: Result instance of baseline subtraction task
        """
        scores = []
        lines_list = []
        group_id_list = []
        spw_id_list = []
        field_id_list = []
        reduction_group = context.observing_run.ms_reduction_group
        baselined = result.outcome['baselined']
        for b in baselined:
            reduction_group_id = b['group_id']
            members = b['members']
            group_desc = reduction_group[reduction_group_id]
            spw_id = numpy.fromiter((group_desc[m].spw_id for m in members), dtype=numpy.int32)  # b['spw']
            field_id = numpy.fromiter((group_desc[m].field_id for m in members), dtype=numpy.int32)  # b['field']
            lines = b['lines']
            lines_list.append(lines)
            group_id_list.append(reduction_group_id)
            spw_id_list.append(spw_id)
            field_id_list.append(field_id)
        scores.append(qacalc.score_sd_line_detection_for_ms(group_id_list,
                                                            field_id_list,
                                                            spw_id_list,
                                                            lines_list))
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
