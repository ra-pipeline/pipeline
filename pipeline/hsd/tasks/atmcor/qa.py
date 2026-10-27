"""QA handling for hsd_atmcor stage."""
from __future__ import annotations

import collections.abc
import os
from typing import TYPE_CHECKING

import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.pipelineqa as pqa
import pipeline.infrastructure.utils as utils
from pipeline.hsd.tasks.common import qautils
from . import atmcor

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pipeline.infrastructure.launcher import Context

LOG = logging.get_logger(__name__)


class SDATMCorrectionQAHandler(pqa.QAPlugin):
    """QA handler for hsd_atmcor stage."""

    result_cls = atmcor.SDATMCorrectionResults
    child_cls = None

    def __init__(self):
        """
        Create SDATMCorrectionQAHandler instance
        """
        # register the properties for 'score_sd_atmcor_status'
        metric_name = 'score_sd_atmcor_status'
        keys = ['vis']
        qautils.registry.register_longmsg_keys(metric_name, keys)
        qautils.registry.register_keys_to_aggregate(metric_name, keys)

    def handle(self, context: Context, result: atmcor.SDATMCorrectionResults):
        """Generate QA score for hsd_atmcor.

        Generate QA score for hsd_atmcor and register it to the result.
        Handle single results instance.

        Args:
            context: pipeline context
            result: results instance
        """
        atmcor_ms_name = result.atmcor_ms_name
        is_outfile_exists = os.path.exists(atmcor_ms_name)
        task_exec_status = result.success
        is_successful = (task_exec_status is True) and (is_outfile_exists is True)

        vis = os.path.basename(result.inputs['vis'])

        if is_successful:
            shortmsg = 'Execution of sdatmcor has succeeded'
            longmsg = f'Execution of sdatmcor for {vis} has succeeded'
            score = 1.0
        else:
            shortmsg = 'Execution of sdatmcor has failed'
            longmsg = f'Execution of sdatmcor for {vis} has failed. Output MS may be created but will be corrupted.'
            score = 0.0
        selection = pqa.TargetDataSelection(vis={vis})

        origin = pqa.QAOrigin(metric_name='score_sd_atmcor_status',
                              metric_score=score,
                              metric_units='Execution stratus of sdatmcor')

        scores = [pqa.QAScore(score, longmsg=longmsg, shortmsg=shortmsg, origin=origin, applies_to=selection)]

        # reformat the messages and append to result.qa.pool
        formatter = qautils.QAScoreFormatter()
        for qascore in scores:
            formatter.update_longmsg(qascore)

        result.qa.pool.extend(scores)


class SDATMCorrectionListQAHandler(pqa.QAPlugin):
    """QA handler for hsd_atmcor stage."""

    result_cls = collections.abc.Iterable
    child_cls = atmcor.SDATMCorrectionResults

    def handle(self, context: Context, result: Iterable[atmcor.SDATMCorrectionResults]):
        """Generate QA score for hsd_atmcor.

        Generate QA score for hsd_atmcor and register it to the result.
        Handles list of results using handler specified by child_cls.

        Args:
            context: pipeline context
            result: list of results instance
        """
        # collate the QAScores from each child result, pulling them into our
        # own QAscore list
        collated = utils.flatten([r.qa.pool for r in result])
        result.qa.pool[:] = collated
