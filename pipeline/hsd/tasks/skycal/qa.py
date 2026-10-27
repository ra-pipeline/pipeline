"""QA score module for skycal task."""
from __future__ import annotations

from typing import TYPE_CHECKING

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.basetask as basetask
import pipeline.infrastructure.pipelineqa as pqa
import pipeline.infrastructure.utils as utils
import pipeline.qa.scorecalculator as qacalc
import pipeline.h.tasks.exportdata.aqua as aqua
from pipeline.hsd.tasks.common import qautils
from . import skycal

if TYPE_CHECKING:
    from pipeline.infrastructure.launcher import Context

LOG = infrastructure.logging.get_logger(__name__)


class SDSkyCalQAHandler(pqa.QAPlugin):
    """Class to handle QA score for skycal result."""

    result_cls = skycal.SDSkyCalResults
    child_cls = None

    def __init__(self):
        """
        register er the parameters for longmsg formatter and aggregator
        """
        # register the properties for 'OnOffElevationDifference'
        metric_name = 'OnOffElevationDifference'
        keys = ['vis', 'field', 'ant']
        qautils.registry.register_longmsg_keys(metric_name, keys)
        qautils.registry.register_keys_to_aggregate(metric_name, keys)

    def handle(self, context: Context, result: skycal.SDSkyCalResults) -> None:
        """Evaluate QA score for skycal result.

        Args:
            context: Pipeline context object containing state information.
            result: SDSkyCalResults instance.
        """
        calapps = result.final
        resultdict = skycal.compute_elevation_difference(context, result)

        if len(calapps) == 0:
            LOG.warning('No skycal solution found, skipping QA score calculation.')
            return

        vis = calapps[0].calto.vis
        ms = context.observing_run.get_ms(vis)
        el_threshold = skycal.ELEVATION_DIFFERENCE_THRESHOLD
        qascores = qacalc.score_sd_skycal_elevation_difference(ms, resultdict, el_threshold)

        if qascores:
            # this block does not aggregate for 'vis', override keys_to_aggregate with ['field', 'ant']
            metric_name = 'OnOffElevationDifference'
            original_keys = qautils.registry.get_keys_to_aggregate(metric_name)
            qautils.registry.register_keys_to_aggregate(metric_name, ['field', 'ant'])

            # try-finally block is implemented to recover keys_to_aggregate even when the aggregator fails
            try:
                # first, consolidate QAScores for field and antennas before feeding into result.qa.pool
                aggregator = qautils.QAScoreAggregator()
                qascores = aggregator.aggregate_qascores(qascores, metric_scores_func=max)
            finally:
                # recover keys_to_aggregate
                qautils.registry.register_keys_to_aggregate(metric_name, original_keys)

            result.qa.pool.extend(qascores)


class SDSkyCalListQAHandler(pqa.QAPlugin):
    """Class to handle QA score for a list of skycal results."""

    result_cls = basetask.ResultsList
    child_cls = skycal.SDSkyCalResults

    def handle(self, context: Context, result: skycal.SDSkyCalResults) -> None:
        """Evaluate QA score for a list of skycal results.

        Args:
            context: Pipeline context (not used).
            result: List of SDSkyCalResults instances.
        """
        # collate the QAScores from each child result, pulling them into our
        # own QAscore list
        collated = utils.flatten([r.qa.pool for r in result])
        result.qa.pool[:] = collated


aqua_exporter = aqua.xml_generator_for_metric('OnOffElevationDifference', '{:0.3f}deg')
aqua.register_aqua_metric(aqua_exporter)
