import collections.abc

import pipeline.infrastructure.pipelineqa as pqa
import pipeline.infrastructure.utils as utils

from . import resultobjects


CYCLE_13_QA_FLOOR = 0.9
PLOT_FAILURE_SCORE = 0.5


class FindROIQAHandler(pqa.QAPlugin):
    result_cls = resultobjects.FindROIResult
    child_cls = None

    def handle(self, context, result):
        summary = result.summary
        n_selected_spws = int(summary.get('n_selected_spws', 0))
        n_successful_spws = int(summary.get('n_successful_spws', 0))
        n_failed_spws = int(summary.get('n_failed_spws', 0))
        n_plot_failures = int(summary.get('n_plot_failures', 0))
        has_unclassified_error = bool(result.errors) and n_failed_spws == 0

        if getattr(result, 'fatal_error', False) or has_unclassified_error:
            raw_score = 0.0
            longmsg = 'hif_findroi encountered a stage-level error; inspect the weblog error list for details.'
            shortmsg = 'findROI failed'
        elif n_selected_spws == 0:
            raw_score = 0.0
            longmsg = 'hif_findroi had no selected science SPWs to analyze.'
            shortmsg = 'No findROI selections'
        else:
            raw_score = float(n_successful_spws) / float(n_selected_spws)
            if n_failed_spws:
                longmsg = (
                    f'hif_findroi successfully analyzed {n_successful_spws} of '
                    f'{n_selected_spws} selected science SPWs; {n_failed_spws} failed. '
                    'Inspect the weblog error list for details.'
                )
                shortmsg = 'findROI partial failure'
            else:
                longmsg = f'hif_findroi successfully analyzed all {n_successful_spws} selected science SPWs.'
                shortmsg = 'findROI complete'

        if n_plot_failures and raw_score > 0.0:
            raw_score = min(raw_score, PLOT_FAILURE_SCORE)
            longmsg = (
                f'{longmsg} {n_plot_failures} plot generation failure'
                f'{"s" if n_plot_failures != 1 else ""} occurred.'
            )
            shortmsg = 'findROI plot failure'

        score_value = max(raw_score, CYCLE_13_QA_FLOOR)
        if raw_score < CYCLE_13_QA_FLOOR:
            longmsg = (
                f'{longmsg} Would have been {raw_score:.2f}; '
                f'hard-floored to {CYCLE_13_QA_FLOOR:.2f} for Cycle 13.'
            )
        score = pqa.QAScore(score_value, longmsg=longmsg, shortmsg=shortmsg)
        result.qa.pool.append(score)


class FindROIListQAHandler(pqa.QAPlugin):
    result_cls = collections.abc.Iterable
    child_cls = resultobjects.FindROIResult

    def handle(self, context, result):
        result.qa.pool[:] = utils.flatten([r.qa.pool for r in result])
