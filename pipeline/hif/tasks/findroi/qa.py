import collections.abc

import pipeline.infrastructure.pipelineqa as pqa
import pipeline.infrastructure.utils as utils

from . import resultobjects


class FindROIQAHandler(pqa.QAPlugin):
    result_cls = resultobjects.FindROIResult
    child_cls = None

    def handle(self, context, result):
        if result.errors and result.summary.get('n_source_spws', 0) == 0:
            score = pqa.QAScore(0.0, longmsg='hif_findroi did not produce usable results.', shortmsg='findROI failed')
        elif result.errors:
            n_failed_spws = int(result.summary.get('n_failed_spws', 0))
            n_selected_spws = int(result.summary.get('n_selected_spws', 0))
            score_value = 1.0 - (float(n_failed_spws) / float(n_selected_spws)) if n_selected_spws else 0.0
            score = pqa.QAScore(
                score_value,
                longmsg=f'hif_findroi completed with {n_failed_spws} failed SPW task(s); inspect the weblog error list for details.',
                shortmsg='findROI partial failure',
            )
        elif result.summary.get('n_source_spws', 0) == 0:
            score = pqa.QAScore(0.0, longmsg='hif_findroi found no source/SPW products.', shortmsg='No findROI products')
        else:
            n_total = int(result.summary.get('n_source_spws', 0))
            n_cont = int(result.summary.get('n_roi_with_continuum', 0))
            score_value = float(n_cont) / float(n_total) if n_total else 0.0
            score = pqa.QAScore(
                score_value,
                longmsg=f'hif_findroi produced continuum selections for {n_cont} of {n_total} source/SPW products.',
                shortmsg='findROI complete',
            )
        result.qa.pool.append(score)


class FindROIListQAHandler(pqa.QAPlugin):
    result_cls = collections.abc.Iterable
    child_cls = resultobjects.FindROIResult

    def handle(self, context, result):
        result.qa.pool[:] = utils.flatten([r.qa.pool for r in result])
