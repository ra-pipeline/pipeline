import collections
import collections.abc
import os

import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.pipelineqa as pqa
import pipeline.infrastructure.utils as utils
import pipeline.qa.scorecalculator as qacalc
from . import testBPdcals
from . import testBPdcalsResults


LOG = logging.get_logger(__name__)


class testBPdcalsQAHandler(pqa.QAPlugin):
    result_cls = testBPdcalsResults
    child_cls = None
    generating_task = testBPdcals

    def handle(self, context, result):
        # get a QA score for fraction of failed (flagged) bandpass solutions in the bandpass table
        # < 5%   of data flagged  --> 1
        # 5%-60% of data flagged  --> 1 to 0
        # > 60%  of data flagged  --> 0
        # 
        # Note: With PIPE-3064 fix, calibration tables may be missing if a band is fully flagged.
        # We score independently for each available table rather than failing entirely.

        m = context.observing_run.get_ms(result.inputs['vis'])
        vis = result.inputs['vis']
        scores = []

        self.antspw = collections.defaultdict(list)
        for bandname, bpdgain_touse in result.bpdgain_touse.items():
            # Check each table independently for availability
            has_bandpass_solution = (bandname in result.flaggedSolnApplycalbandpass and 
                                     result.flaggedSolnApplycalbandpass[bandname])
            has_delay_solution = (bandname in result.flaggedSolnApplycaldelay and 
                                 result.flaggedSolnApplycaldelay[bandname])

            # Process K-type (delay) calibration solution if available
            if has_delay_solution:
                self._checkKandBsolution(result.flaggedSolnApplycaldelay[bandname], m)
            
            # Process B-type (bandpass) calibration solution if available
            if has_bandpass_solution:
                self._checkKandBsolution(result.flaggedSolnApplycalbandpass[bandname], m)

            # Score bandpass solutions if both flagged solution data and table file exist
            if has_bandpass_solution and os.path.exists(result.bpdgain_touse[bandname]):
                score1 = qacalc.score_total_data_flagged_vla_bandpass(result.bpdgain_touse[bandname],
                                                                      result.flaggedSolnApplycalbandpass[bandname]['antmedian']['fraction'])
                scores.append(score1)
            elif not has_bandpass_solution:
                LOG.warning('Bandpass calibration table missing for band %s (band may be fully flagged).', bandname)

            # Score delay solutions if both flagged solution data and table file exist
            if has_delay_solution and os.path.exists(result.ktypecaltable[bandname]):
                score2 = qacalc.score_total_data_vla_delay(result.ktypecaltable[bandname],
                                                           result.inputs['vis'], bandname)
                scores.append(score2)
            elif not has_delay_solution:
                LOG.warning('Delay calibration table missing for band %s (band may be fully flagged).', bandname)

            # Flag error only if BOTH are missing (indicates real problem)
            if not has_bandpass_solution and not has_delay_solution:
                scores.append(pqa.QAScore(0.0,
                                          longmsg='Band {!s}: Both delay (K-type) and bandpass (B-type) calibration tables missing. Band is likely fully flagged.'.format(bandname),
                                          shortmsg='Band {!s}: K-type and B-type calibration tables missing (fully flagged).'.format(bandname)))

            # get a QA score for flagging
            # 0%   of data flagged  --> 1
            # 0%-30% of data flagged  --> 1 to 0
            # > 30%  of data flagged  --> 0
            score3 = qacalc.score_flagged_vla_baddef(result.amp_collection[bandname],
                                                     result.phase_collection[bandname],
                                                     result.num_antennas[bandname])
            scores.append(score3)

            score_dts_ant = qacalc.score_testBPdcals_dts_ants(vis, result.amp_collection[bandname], result.phase_collection[bandname], bandname)
            scores.append(score_dts_ant)

            score_refant = qacalc.score_testBPdcals_refant(vis, result.bad_refant[bandname], bandname)
            scores.append(score_refant)

            if os.path.exists(result.ktypecaltable[bandname]):
                score_median_delay = qacalc.score_testBPdcals_delay(vis, result.ktypecaltable[bandname], bandname)
                scores.append(score_median_delay)

        for antenna, spwlist in self.antspw.items():
            uniquespw = list(set(spwlist))
            uniquespwlist = [int(spw) for spw in uniquespw]
            uniquespwlist.sort()
            uniquespwlist = [str(spw) for spw in uniquespwlist]
            LOG.warning('Antenna %s, spws: %s have a flagging fraction of 1.0.', antenna, ','.join(uniquespwlist))

        # PIPE-2512: add QA score for spw solint
        for bandname, spw_solint in result.spw_solint.items():
            score3 = qacalc.score_spw_solint(vis, bandname, spw_solint)
            if score3:
                scores.append(score3)

        result.qa.pool.extend(scores)

    def _checkKandBsolution(self, table, m):

        antenna_names = [a.name for a in m.antennas]

        for antenna in table['antspw']:
            spwcollect = []
            for spw in table['antspw'][antenna]:
                for pol in table['antspw'][antenna][spw]:
                    frac = table['antspw'][antenna][spw][pol]['fraction']
                    if frac == 1.0:
                        spwcollect.append(int(spw))
            if len(spwcollect) > 1:
                spwcollect = sorted(set(spwcollect))
                spwcollect = [str(spw) for spw in spwcollect]
                self.antspw[antenna_names[antenna]].extend(spwcollect)
                # LOG.warning('Antenna {!s}, spws: {!s} have a flagging fraction of 1.0.'
                #         ''.format(antenna_names[antenna], ','.join(spwcollect)))

        return


class testBPdcalsListQAHandler(pqa.QAPlugin):
    """
    QA handler for a list containing testBPdcalsResults.
    """
    result_cls = collections.abc.Iterable
    child_cls = testBPdcalsResults

    def handle(self, context, result):
        # collate the QAScores from each child result, pulling them into our
        # own QAscore list
        collated = utils.flatten([r.qa.pool for r in result])
        result.qa.pool.extend(collated)
