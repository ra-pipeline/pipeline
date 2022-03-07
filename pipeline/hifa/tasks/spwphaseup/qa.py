import collections

import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.pipelineqa as pqa
import pipeline.infrastructure.utils as utils
import pipeline.qa.scorecalculator as qacalc
from . import spwphaseup

LOG = logging.get_logger(__name__)


class SpwPhaseupQAHandler(pqa.QAPlugin):
    result_cls = spwphaseup.SpwPhaseupResults
    child_cls = None
    generating_task = spwphaseup.SpwPhaseup

    def handle(self, context, result):
        vis = result.inputs['vis']
        ms = context.observing_run.get_ms(vis)

        scores = []

        # Step through each spwmapping to create QA scores.
        for (intent, field), spwmapping in result.spwmaps.items():
            # For PHASE calibrator fields, score the spwmapping based on
            # fraction of unmapped science spws.
            if intent == 'PHASE':
                scores.append(qacalc.score_phaseup_mapping_fraction(ms, intent, field, spwmapping))
            # For CHECK fields, score the spwmapping based on whether or not
            # it is combining spws.
            elif intent == 'CHECK':
                scores.append(qacalc.score_combine_spwmapping(ms, intent, field, spwmapping))

        # Create QA score for whether or not the phaseup caltable was created succesfully.
        if not result.phaseup_result.final:
            gaintable = list(result.phaseup_result.error)[0].gaintable
        else:
            gaintable = result.phaseup_result.final[0].gaintable
        scores.append(qacalc.score_path_exists(ms.name, gaintable, 'caltable'))

        # Create QA score for median SNR per field and per SpW.
        for (field, spw), median_snr in result.snr_info.items():
            scores.append(qacalc.score_phaseup_spw_median_snr(ms, field, spw, median_snr, result.inputs['phasesnr']))

        # Add scores to QA pool in result.
        result.qa.pool.extend(scores)


class SpwPhaseupListQAHandler(pqa.QAPlugin):
    """
    QA handler for a list containing SpwPhaseupResults.
    """
    result_cls = collections.Iterable
    child_cls = spwphaseup.SpwPhaseupResults
    generating_task = spwphaseup.SpwPhaseup

    def handle(self, context, result):
        # collate the QAScores from each child result, pulling them into our
        # own QAscore list
        collated = utils.flatten([r.qa.pool for r in result])
        result.qa.pool[:] = collated

        mses = [r.inputs['vis'] for r in result]
        longmsg = 'No mapped narrow spws in %s' % utils.commafy(mses, quotes=False, conjunction='or')
        result.qa.all_unity_longmsg = longmsg
