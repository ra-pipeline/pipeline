import collections
import collections.abc

import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.pipelineqa as pqa
import pipeline.infrastructure.utils as utils
import pipeline.qa.scorecalculator as qacalc
from . import semiFinalBPdcals
from . import semiFinalBPdcalsResults

LOG = logging.get_logger(__name__)


class semiFinalBPdcalsQAHandler(pqa.QAPlugin):
    result_cls = semiFinalBPdcalsResults
    child_cls = None
    generating_task = semiFinalBPdcals

    def handle(self, context, result):
        # get a QA score for fraction of failed (flagged) bandpass solutions in the bandpass table
        # < 5%   of data flagged  --> 1
        # 5%-60% of data flagged  --> 1 to 0
        # > 60%  of data flagged  --> 0

        vis = result.inputs['vis']
        m = context.observing_run.get_ms(vis)

        scores = []

        self.antspw = collections.defaultdict(list)
        for bandname, bpdgain_touse in result.bpdgain_touse.items():
            if result.flaggedSolnApplycalbandpass[bandname] and result.flaggedSolnApplycaldelay[bandname]:
                # Check if any spw are fully flagged or missing
                self._check_spw_flagged(result.flaggedSolnApplycalbandpass[bandname], bandname, m, 'Bandpass')
                self._check_spw_flagged(result.flaggedSolnApplycaldelay[bandname], bandname, m, 'Delay')

                # Check if antennas are fully flagged
                self._check_antenna_flagged(result.flaggedSolnApplycalbandpass[bandname], bandname, m, 'Bandpass')
                self._check_antenna_flagged(result.flaggedSolnApplycaldelay[bandname], bandname, m, 'Delay')

                score1 = qacalc.score_total_data_flagged_vla_bandpass(
                    bpdgain_touse, result.flaggedSolnApplycalbandpass[bandname]['antmedian']['fraction'])
                scores.append(score1)

                # if delay per BB >15 ns: score <0.5
                score2 = qacalc.score_total_data_vla_delay(result.ktypecaltable[bandname], result.inputs['vis'], bandname)
                scores.append(score2)
            else:
                LOG.error('Error with bandpass and/or delay table for band {!s}.'.format(bandname))
                scores = [pqa.QAScore(0.0, longmsg='No flagging stats about the bandpass table or info in delay table.',
                                      shortmsg='Bandpass or delay table problem.')]

        if result.bpdgain_touse:
            # if >50% of spws are flagged: score <0.5
            score3 = qacalc.score_flagged_ant_spw(result.inputs['vis'], result.flaggedSolnApplycaldelay)
            if len(score3) > 0:
                scores.extend(score3)

        # PIPE-2512: add QA score for spw solint
        for bandname, spw_solint in result.spw_solint.items():
            score4 = qacalc.score_spw_solint(vis, bandname, spw_solint)
            if score4:
                scores.append(score4)

        result.qa.pool.extend(scores)

    def _check_spw_flagged(self, table: dict, bandname: str, ms: object, table_type: str):
        for spw in ms.get_spectral_windows():
            if not spw.specline_window:
                continue
            spw_id = spw.id
            flaginfo = table.get('spw', {}).get(spw_id)

            if flaginfo is None:
                LOG.warning(
                    f"Spectral window {spw_id} is missing for band {bandname} "
                    f"from the {table_type} table."
                )
                continue

            if all(pol_info.get('fraction') == 1.0 for pol_info in flaginfo.values()):
                LOG.warning(
                    f"Spectral window {spw_id} is fully flagged "
                    f"for band {bandname} in the {table_type} table."
                )

    def _check_antenna_flagged(self, table: dict, bandname: str, ms: object, table_type: str):
        ant_table = table.get('ant', {})
        antenna_map = {a.id: a.name for a in ms.antennas}
        flagged_antennas = []
        for antenna_id, pol_data in ant_table.items():
            if all(pol_info.get('fraction') == 1.0 for pol_info in pol_data.values()):
                antenna_name = antenna_map.get(antenna_id, f"<unknown:{antenna_id}>")
                flagged_antennas.append(antenna_name)
        if len(flagged_antennas) > 1:
            LOG.warning(
                f"Antenna(s) {', '.join(flagged_antennas)} are fully flagged "
                f"for band {bandname} in the {table_type} table."
            )


class semiFinalBPdcalsListQAHandler(pqa.QAPlugin):
    """
    QA handler for a list containing semiFinalBPdcalsResults.
    """
    result_cls = collections.abc.Iterable
    child_cls = semiFinalBPdcalsResults

    def handle(self, context, result):
        # collate the QAScores from each child result, pulling them into our
        # own QAscore list
        collated = utils.flatten([r.qa.pool for r in result])
        result.qa.pool.extend(collated)
