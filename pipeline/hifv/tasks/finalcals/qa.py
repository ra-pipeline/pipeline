import collections.abc

import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.pipelineqa as pqa
import pipeline.infrastructure.utils as utils
import pipeline.qa.scorecalculator as qacalc
from pipeline.h.tasks.applycal.applycal import ApplycalResults

from . import Applycals, Finalcals, FinalcalsResults

LOG = logging.get_logger(__name__)


class FinalcalsQAHandler(pqa.QAPlugin):
    result_cls = FinalcalsResults
    child_cls = None
    generating_task = Finalcals

    def handle(self, context, result):
        # get a QA score for fraction of failed (flagged) bandpass solutions in the bandpass table
        # < 5%   of data flagged  --> 1
        # 5%-60% of data flagged  --> 1 to 0
        # > 60%  of data flagged  --> 0

        vis = result.inputs['vis']
        m = context.observing_run.get_ms(vis)

        if result.flaggedSolnApplycalbandpass and result.flaggedSolnApplycaldelay:
            self._checkKandBsolution(result.flaggedSolnApplycaldelay, m)
            self._checkKandBsolution(result.flaggedSolnApplycalbandpass, m)

            score1 = qacalc.score_total_data_flagged_vla_bandpass(
                result.bpdgain_touse, result.flaggedSolnApplycalbandpass['antmedian']['fraction'])
            score2 = qacalc.score_total_data_vla_delay(result.ktypecaltable, result.inputs['vis'])
            scores = [score1, score2]
        else:
            LOG.error('Error with bandpass and/or delay table.')
            scores = [pqa.QAScore(0.0, longmsg='No flagging stats about the bandpass table or info in delay table.',
                                  shortmsg='Bandpass or delay table problem.')]

        # PIPE-2512: add QA score for spw solint
        for bandname, spw_solint in result.spw_solint.items():
            score3 = qacalc.score_spw_solint(vis, bandname, spw_solint)
            if score3:
                scores.append(score3)

        result.qa.pool.extend(scores)

    @staticmethod
    def _checkKandBsolution(table, m):

        antenna_names = [a.name for a in m.antennas]

        for antenna in table['antspw']:
            spwcollect = []
            for spw in table['antspw'][antenna]:
                for pol in table['antspw'][antenna][spw]:
                    frac = table['antspw'][antenna][spw][pol]['fraction']
                    if frac == 1.0:
                        spwcollect.append(str(spw))
            if len(spwcollect) > 1:
                spwcollect = sorted(set(spwcollect))
                spwcollect = [int(spw) for spw in spwcollect]
                spwcollect.sort()
                spwcollect = [str(spw) for spw in spwcollect]
                LOG.warning('Antenna {!s}, spws: {!s} have a flagging fraction of 1.0.'
                            ''.format(antenna_names[antenna], ','.join(spwcollect)))

        return


class FinalcalsListQAHandler(pqa.QAPlugin):
    """
    QA handler for a list containing FinalcalsResults.
    """
    result_cls = collections.abc.Iterable
    child_cls = FinalcalsResults

    def handle(self, context, result):
        # collate the QAScores from each child result, pulling them into our
        # own QAscore list
        collated = utils.flatten([r.qa.pool for r in result])
        result.qa.pool.extend(collated)


class ApplycalsQAHandler(pqa.QAPlugin):
    """PIPE-2586: VLA-specific QA on the data flagged by hifv_applycals."""

    result_cls = ApplycalResults
    child_cls = None
    generating_task = Applycals

    def handle(self, context, result):
        """Add the VLA applycal flagging scores to the result's QA pool."""
        vis = result.inputs['vis']
        ms = context.observing_run.get_ms(vis)

        scores = []
        summaries = getattr(result, 'summaries', None)
        if summaries:
            # If > 85% of all data are flagged: QA score < 0.5
            scores.append(qacalc.applycal_score_total_flagged(ms, summaries[-1]))

        band_stats = getattr(result, 'band_flag_stats', None)
        if band_stats:
            # Complex gain calibrator (CGC) and science target fields
            cgc_fields = utils.deduplicate(utils.dequote(f.name) for f in ms.get_fields(intent='PHASE'))
            target_fields = utils.deduplicate(utils.dequote(f.name) for f in ms.get_fields(intent='TARGET'))

            # If >30% of additional data flagged per science target or per CGC (in any band): QA score < 0.5
            scores.extend(qacalc.applycal_score_additional_flagged(ms, band_stats, cgc_fields, target_fields))

            # If target flag change percentage > 1.1x the CGC flagging change: QA score < 0.5
            scores.extend(qacalc.applycal_score_target_vs_cgc_additional(ms, band_stats, cgc_fields, target_fields))

            # If spectral line windows become completely flagged on science target: QA score < 0.5
            scores.extend(qacalc.applycal_score_specline_spws_flagged(ms, band_stats, target_fields))

        result.qa.pool.extend(scores)
