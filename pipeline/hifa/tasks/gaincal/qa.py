import collections
import os

import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.pipelineqa as pqa
import pipeline.infrastructure.utils as utils
from pipeline.infrastructure import casa_tools
import pipeline.qa.gpcal as gpcal
from pipeline.h.tasks.common import commonhelpermethods
from pipeline.hif.tasks.gaincal import common

import numpy as np

LOG = logging.get_logger(__name__)


class TimegaincalQAPool(pqa.QAScorePool):
    xy_x2x1_score_types = {
        'PHASE_SCORE_XY': ('XY_TOTAL', 'X-Y phase deviation'),
        'PHASE_SCORE_X2X1': ('X2X1_TOTAL', 'X2-X1 phase deviation')
    }

    xy_x2x1_short_msg = {
        'PHASE_SCORE_XY': 'X-Y deviation',
        'PHASE_SCORE_X2X1': 'X2-X1 deviation'
    }

    def __init__(self, phase_qa_results_dict, phase_offsets_qa_results_dict):
        super(TimegaincalQAPool, self).__init__()
        self.phase_qa_results_dict = phase_qa_results_dict
        self.phase_offsets_qa_results_dict = phase_offsets_qa_results_dict

    def update_scores(self, ms, refant):
        # Phase offsets scores
        hidden_phase_offsets_scores, public_phase_offsets_scores = self._get_phase_offset_scores(ms, refant.split(',')[0])
        self.pool.extend(public_phase_offsets_scores)
        self.pool.extend(hidden_phase_offsets_scores)

        # X-Y / X2-X1 scores
        #
        # PIPE-365: Revise hifa_timegaincal QA scores for Cy7
        #
        # Remy: Remove consideration of X-Y, X2-X1 phase vs. time metrics
        # from QA scoring (keep evaluation for now - I will open a CASR to
        # revise these evaluations)
        #
        # phase_field_ids = [field.id for field in ms.get_fields(intent='PHASE')]
        # self.pool.extend([self._get_xy_x2x1_qascore(ms, phase_field_ids, t) for t in self.xy_x2x1_score_types])

    def _get_phase_offset_scores(self, ms, refant):

        """
        Calculate phase offsets scores.
        """

        try:
            tbTool = casa_tools.table

            # Define thresholds (in degrees) a factors for QA tests
            NoiseThresh = 15.0

            QA1_Thresh1 = 5.0
            QA1_Thresh2 = 30.0
            QA1_Factor = 6.0

            QA2_Thresh1 = 15.0
            QA2_Thresh2 = 30.0
            QA2_Factor1 = 2.0
            QA2_Factor2 = 4.0

            QA3_Thresh1 = 15.0
            QA3_Thresh2 = 30.0
            QA3_Factor = 6.0

            phase_scan_ids = np.array([s.id for s in ms.get_scans(scan_intent='PHASE')])

            # Create antenna ID to name translation dictionary, reject empty antenna name strings.
            antenna_id_to_name = {ant.id: ant.name for ant in ms.antennas if ant.name.strip()}

            # Get refant ID
            refant_id = [ant.id for ant in ms.antennas if ant.name.strip() == refant][0]

            hidden_phase_offsets_scores = []
            public_phase_offsets_scores = []
            subscores = {}
            for gaintable in self.phase_offsets_qa_results_dict:
                tbTool.open(gaintable)
                # Get phase offsets in degrees, obeying any flags.
                phase_offsets = np.rad2deg(np.ma.angle(np.ma.array(tbTool.getcol('CPARAM'), mask=tbTool.getcol('FLAG'))))
                scan_numbers = tbTool.getcol('SCAN_NUMBER')
                spw_ids = tbTool.getcol('SPECTRAL_WINDOW_ID')
                ant_ids = tbTool.getcol('ANTENNA1')
                tbTool.done()
                subscores[gaintable] = {}
                noisy_spw_ids = []
                poor_stats_spw_ids = {}
                for spw_id in sorted(set(spw_ids)):
                    subscores[gaintable][spw_id] = {}
                    # Get names of polarization(s), and create polarization index
                    corr_type = commonhelpermethods.get_corr_axis(ms, spw_id)
                    # Estimate of the overall noise (all ant, pol, solutions) for a given EB and SPW
                    selection = phase_offsets[:, 0,
                        np.ma.where((np.isin(scan_numbers, phase_scan_ids)) & (spw_ids == spw_id) & (ant_ids != refant_id))]
                    # MAD multiplied by a fudge factor that makes it equivalent to standard deviation if the input values are normally distributed
                    Stot = 1.4826 * np.ma.median(np.ma.abs(selection - np.ma.median(selection)))
                    if Stot > NoiseThresh:
                        # Noise too high for further evaluation
                        noisy_spw_ids.append(spw_id)
                        for ant_id in sorted(set(ant_ids)-{refant_id}):
                            subscores[gaintable][spw_id][ant_id] = {}
                            # PIPE-1628: in case when the given spw has only a single polarization
                            # (this always means 'X' in the current workflow), the phase_offsets table
                            # still has two columns, but one of them is empty and should be ignored.
                            for pol_id, pol_name in enumerate(corr_type):
                                subscores[gaintable][spw_id][ant_id][pol_id] = {}
                                for scorekey in ['QA1', 'QA2', 'QA3']:
                                    score = 0.82
                                    longmsg = f'Phase offsets too noisy to usefully evaluate {ms.basename} SPW {spw_id} Antenna {antenna_id_to_name[ant_id]} Polarization {pol_name}'
                                    shortmsg = 'Phase offsets too noisy'
                                    origin = pqa.QAOrigin(metric_name='Stot(EB, spw)',
                                                          metric_score=Stot,
                                                          metric_units='degrees')
                                    data_selection = pqa.TargetDataSelection(vis={ms.basename}, spw={spw_id}, intent={'PHASE'}, ant={ant_id}, pol={pol_name})
                                    weblog_location = pqa.WebLogLocation.HIDDEN
                                    subscores[gaintable][spw_id][ant_id][pol_id][scorekey] = pqa.QAScore(score=score,
                                        longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin,
                                        applies_to=data_selection, weblog_location=weblog_location)
                                    hidden_phase_offsets_scores.append(subscores[gaintable][spw_id][ant_id][pol_id][scorekey])
                    else:
                        for ant_id in sorted(set(ant_ids)-{refant_id}):
                            subscores[gaintable][spw_id][ant_id] = {}
                            for pol_id, pol_name in enumerate(corr_type):  # PIPE-1628: loop over available polarizations, which could be fewer than the number of columns in the table
                                subscores[gaintable][spw_id][ant_id][pol_id] = {}
                                selection = phase_offsets[pol_id, 0,
                                    np.ma.where((np.isin(scan_numbers, phase_scan_ids)) & (spw_ids == spw_id) & (ant_ids == ant_id))]
                                N = np.ma.count(selection)  # number of unflagged phase solutions for given spw, ant, pol selection
                                if N > 0:
                                    M = np.ma.mean(selection)
                                    S = np.ma.std(selection, ddof=1)
                                    MaxOff = np.ma.max(np.ma.abs(selection))
                                else:
                                    # no data for the given pol/ant/spw combination exists;
                                    # in this case the second test (standard deviation) will show a score 0.85,
                                    # and the other two tests will appear normal (score 1.0),
                                    # but in the end the lowest score will be displayed anyway
                                    M = S = MaxOff = np.nan

                                # Mean test
                                QA1_score = 1.0
                                QA1_longmsg = f'Phase offsets mean for {ms.basename} SPW {spw_id} Antenna {antenna_id_to_name[ant_id]} Polarization {pol_name} within range'
                                QA1_shortmsg = 'Phase offsets mean within range'
                                if np.abs(M) > max(QA1_Thresh1, QA1_Factor * Stot / np.sqrt(N)):
                                    QA1_score = 0.8
                                    QA1_longmsg = f'Phase offsets mean for {ms.basename} SPW {spw_id} Antenna {antenna_id_to_name[ant_id]} Polarization {pol_name} exceeding first threshold'
                                    QA1_shortmsg = 'Phase offsets mean too large'
                                if np.abs(M) > max(QA1_Thresh2, QA1_Factor * Stot / np.sqrt(N)):
                                    QA1_score = 0.5
                                    QA1_longmsg = f'Phase offsets mean for {ms.basename} SPW {spw_id} Antenna {antenna_id_to_name[ant_id]} Polarization {pol_name} exceeding second threshold'
                                    QA1_shortmsg = 'Phase offsets mean too large'
                                QA1_origin = pqa.QAOrigin(metric_name='phase offsets mean',
                                                          metric_score=M,
                                                          metric_units='degrees')
                                QA1_data_selection = pqa.TargetDataSelection(vis={ms.basename}, spw={spw_id}, intent={'PHASE'}, ant={ant_id}, pol={pol_name})
                                QA1_weblog_location = pqa.WebLogLocation.HIDDEN
                                subscores[gaintable][spw_id][ant_id][pol_id]['QA1'] = pqa.QAScore(score=QA1_score,
                                    longmsg=QA1_longmsg, shortmsg=QA1_shortmsg, vis=ms.basename, origin=QA1_origin,
                                    applies_to=QA1_data_selection, weblog_location=QA1_weblog_location)
                                hidden_phase_offsets_scores.append(subscores[gaintable][spw_id][ant_id][pol_id]['QA1'])

                                if N < 4:
                                    # Poor statistics
                                    if spw_id not in poor_stats_spw_ids:
                                        poor_stats_spw_ids[spw_id] = {ant_id}
                                    else:
                                        poor_stats_spw_ids[spw_id].add(ant_id)
                                    QA2_score = 0.85
                                    QA2_longmsg = f'Phase offsets with poor statistics for {ms.basename} SPW {spw_id} Antenna {antenna_id_to_name[ant_id]} Polarization {pol_name}'
                                    QA2_shortmsg = 'Poor phase offsets statistics'
                                    QA2_origin = pqa.QAOrigin(metric_name='Number of solutions',
                                                          metric_score=N,
                                                          metric_units='N/A')
                                else:
                                    # Standard deviation test
                                    QA2_score = 1.0
                                    QA2_longmsg = f'Phase offsets standard deviation for {ms.basename} SPW {spw_id} Antenna {antenna_id_to_name[ant_id]} Polarization {pol_name} within range'
                                    QA2_shortmsg = 'Phase offsets standard deviation within range'
                                    if S > max(QA2_Thresh1, QA2_Factor1 * Stot):
                                        QA2_score = 0.8
                                        QA2_longmsg = f'Phase offsets standard deviation for {ms.basename} SPW {spw_id} Antenna {antenna_id_to_name[ant_id]} Polarization {pol_name} exceeding first threshold'
                                        QA2_shortmsg = 'Phase offsets standard deviation too large'
                                    if S > max(QA2_Thresh2, QA2_Factor2 * Stot):
                                        QA2_score = 0.5
                                        QA2_longmsg = f'Phase offsets standard deviation for {ms.basename} SPW {spw_id} Antenna {antenna_id_to_name[ant_id]} Polarization {pol_name} exceeding second threshold'
                                        QA2_shortmsg = 'Phase offsets standard deviation too large'
                                    QA2_origin = pqa.QAOrigin(metric_name='phase offsets standard deviation',
                                                              metric_score=S,
                                                              metric_units='degrees')
                                QA2_data_selection = pqa.TargetDataSelection(vis={ms.basename}, spw={spw_id}, intent={'PHASE'}, ant={ant_id}, pol={pol_name})
                                QA2_weblog_location = pqa.WebLogLocation.HIDDEN
                                subscores[gaintable][spw_id][ant_id][pol_id]['QA2'] = pqa.QAScore(score=QA2_score,
                                    longmsg=QA2_longmsg, shortmsg=QA2_shortmsg, vis=ms.basename, origin=QA2_origin,
                                    applies_to=QA2_data_selection, weblog_location=QA2_weblog_location)
                                hidden_phase_offsets_scores.append(subscores[gaintable][spw_id][ant_id][pol_id]['QA2'])

                                # Maximum test
                                QA3_score = 1.0
                                QA3_longmsg = f'Phase offsets maximum for {ms.basename} SPW {spw_id} Antenna {antenna_id_to_name[ant_id]} Polarization {pol_name} within range'
                                QA3_shortmsg = 'Phase offsets maximum within range'
                                if np.abs(MaxOff) > max(QA3_Thresh1, QA3_Factor * Stot):
                                    QA3_score = 0.8
                                    QA3_longmsg = f'Phase offsets maximum for {ms.basename} SPW {spw_id} Antenna {antenna_id_to_name[ant_id]} Polarization {pol_name} exceeding first threshold'
                                    QA3_shortmsg = 'Phase offsets maximum too large'
                                if np.abs(MaxOff) > max(QA3_Thresh2, QA3_Factor * Stot):
                                    QA3_score = 0.5
                                    QA3_longmsg = f'Phase offsets maximum for {ms.basename} SPW {spw_id} Antenna {antenna_id_to_name[ant_id]} Polarization {pol_name} exceeding second threshold'
                                    QA3_shortmsg = 'Phase offsets maximum too large'
                                QA3_origin = pqa.QAOrigin(metric_name='phase offsets maximum',
                                                          metric_score=MaxOff,
                                                          metric_units='degrees')
                                QA3_data_selection = pqa.TargetDataSelection(vis={ms.basename}, spw={spw_id}, intent={'PHASE'}, ant={ant_id}, pol={pol_name})
                                QA3_weblog_location = pqa.WebLogLocation.HIDDEN
                                subscores[gaintable][spw_id][ant_id][pol_id]['QA3'] = pqa.QAScore(score=QA3_score,
                                    longmsg=QA3_longmsg, shortmsg=QA3_shortmsg, vis=ms.basename, origin=QA3_origin,
                                    applies_to=QA3_data_selection, weblog_location=QA3_weblog_location)
                                hidden_phase_offsets_scores.append(subscores[gaintable][spw_id][ant_id][pol_id]['QA3'])

                # Create aggregated scores
                good_spw_ids = []
                for spw_id in sorted(set(spw_ids)):
                    EB_spw_QA_scores = []
                    # PIPE-1628: loop over available polarizations, which could be fewer than the number of columns in the table
                    corr_type = commonhelpermethods.get_corr_axis(ms, spw_id)
                    for ant_id in sorted(set(ant_ids)-{refant_id}):
                        for pol_id, pol_name in enumerate(corr_type):
                            # Minimum of QA1, QA2, QA3 scores
                            QA_scores = [subscores[gaintable][spw_id][ant_id][pol_id]['QA1'],
                                         subscores[gaintable][spw_id][ant_id][pol_id]['QA2'],
                                         subscores[gaintable][spw_id][ant_id][pol_id]['QA3']]
                            min_index = np.argmin([qas.score for qas in QA_scores])
                            QA_score = QA_scores[min_index].score
                            QA_longmsg = QA_scores[min_index].longmsg
                            QA_shortmsg = QA_scores[min_index].shortmsg
                            QA_origin = QA_scores[min_index].origin
                            QA_data_selection = QA_scores[min_index].applies_to
                            QA_weblog_location = pqa.WebLogLocation.HIDDEN
                            subscores[gaintable][spw_id][ant_id][pol_id]['QA'] = pqa.QAScore(score=QA_score,
                                longmsg=QA_longmsg, shortmsg=QA_shortmsg, vis=ms.basename, origin=QA_origin,
                                applies_to=QA_data_selection, weblog_location=QA_weblog_location)
                            # Just collect the scores for further aggregation. The minimum is already
                            # in the hidden_phase_offsets_scores list.
                            EB_spw_QA_scores.append(subscores[gaintable][spw_id][ant_id][pol_id]['QA'])
                            if QA_score <= 0.8:
                                LOG.info(f'Poor phase offsets score for {ms.basename} SPW {spw_id} Antenna {antenna_id_to_name[ant_id]} Polarization {pol_name}: '
                                         f'QA score = {QA_score:.1f}, mean phase offset = {subscores[gaintable][spw_id][ant_id][pol_id]["QA1"].origin.metric_score:.1f} deg, '
                                         f'standard deviation = {subscores[gaintable][spw_id][ant_id][pol_id]["QA2"].origin.metric_score:.1f} deg, '
                                         f'max offset = {subscores[gaintable][spw_id][ant_id][pol_id]["QA3"].origin.metric_score:.1f} deg')
                    # Minimum of per aggregated ant/pol scores as per EB/spw score
                    EB_spw_min_index = np.argmin([qas.score for qas in EB_spw_QA_scores])
                    EB_spw_QA_score = EB_spw_QA_scores[EB_spw_min_index].score

                    # The aggregation of 0.82, 0.85 and 1.0 scores is handled separately outside this loop
                    if EB_spw_QA_score == 1.0:
                        good_spw_ids.append(spw_id)
                        continue
                    elif EB_spw_QA_score in [0.82, 0.85]:
                        continue
                    elif EB_spw_QA_score in [0.5, 0.8]:
                        antenna_names_list = []
                        for ant_id in sorted(set(ant_ids)-{refant_id}):
                            # Get only the non-noisy antennas
                            per_antenna_score = min(subscores[gaintable][spw_id][ant_id][pol_id]['QA'].score for pol_id in range(len(corr_type)))
                            if per_antenna_score not in [0.82, 0.85]:
                                if per_antenna_score <= 0.66:
                                    # Highlight bad antennas with an asterisk
                                    antenna_names_list.append(f'*{antenna_id_to_name[ant_id]}')
                                elif 0.66 < per_antenna_score <= 0.9:
                                    antenna_names_list.append(antenna_id_to_name[ant_id])
                        antenna_names = ', '.join(antenna_names_list)
                        EB_spw_QA_longmsg = f'Potential phase offset outliers for {ms.basename} SPW {spw_id} Antenna{"" if len(antenna_names_list) == 1 else "s"} {antenna_names}'
                        EB_spw_QA_shortmsg = f'Potential phase offset outliers'
                    else:
                        EB_spw_QA_longmsg = f'Potential phase offset outliers for {ms.basename} SPW {spw_id}'
                        EB_spw_QA_shortmsg = f'Potential phase offset outliers'
                    EB_spw_QA_origin = EB_spw_QA_scores[EB_spw_min_index].origin
                    EB_spw_QA_data_selection = EB_spw_QA_scores[EB_spw_min_index].applies_to
                    EB_spw_QA_weblog_location = pqa.WebLogLocation.ACCORDION
                    public_phase_offsets_scores.append(pqa.QAScore(score=EB_spw_QA_score, longmsg=EB_spw_QA_longmsg,
                        shortmsg=EB_spw_QA_shortmsg, vis=ms.basename, origin=EB_spw_QA_origin,
                        applies_to=EB_spw_QA_data_selection, weblog_location=EB_spw_QA_weblog_location))

                if good_spw_ids:
                    # Add aggregated score for good spws
                    score = 1.0
                    longmsg = f'Phase offsets for {ms.basename} SPW {",".join(map(str, sorted(set(good_spw_ids))))} within range'
                    shortmsg = 'Phase offsets within range'
                    origin = pqa.QAOrigin(metric_name='Stot / Mean / SD / MaxOff',
                                          metric_score=-999,
                                          metric_units='degrees')
                    data_selection = pqa.TargetDataSelection(vis={ms.basename}, spw=set(good_spw_ids), intent={'PHASE'})
                    weblog_location = pqa.WebLogLocation.ACCORDION
                    public_phase_offsets_scores.append(pqa.QAScore(score=score, longmsg=longmsg, shortmsg=shortmsg,
                        vis=ms.basename, origin=origin, applies_to=data_selection, weblog_location=weblog_location))

                if poor_stats_spw_ids:
                    # Add aggregated score for poor statistics spws and their antennas
                    score = 0.85
                    unique_ant_id_selections = dict((tuple(poor_stats_ant_ids), None) for poor_stats_ant_ids in poor_stats_spw_ids.values())
                    for unique_ant_id_selection in unique_ant_id_selections:
                        spw_ids_selection_list = [spw_id for spw_id in poor_stats_spw_ids if tuple(poor_stats_spw_ids[spw_id]) == unique_ant_id_selection]
                        spw_ids_selection = ','.join(str(spw_id) for spw_id in spw_ids_selection_list)
                        antenna_names = ', '.join([antenna_id_to_name[ant_id] for ant_id in sorted(unique_ant_id_selection)])
                        longmsg = f'Phase offsets: insufficient data to evaluate stability for {ms.basename} SPW {spw_ids_selection} Antenna{"" if len(unique_ant_id_selection) == 1 else "s"} {antenna_names}'
                        shortmsg = 'Phase offsets: insufficient data'
                        origin = pqa.QAOrigin(metric_name='Number of solutions',
                                              metric_score=-999,
                                              metric_units='N/A')
                        data_selection = pqa.TargetDataSelection(vis={ms.basename}, spw=set(spw_ids_selection_list), intent={'PHASE'})
                        weblog_location = pqa.WebLogLocation.ACCORDION
                        public_phase_offsets_scores.append(pqa.QAScore(score=score, longmsg=longmsg, shortmsg=shortmsg,
                            vis=ms.basename, origin=origin, applies_to=data_selection, weblog_location=weblog_location))

                if noisy_spw_ids:
                    # Add aggregated score for noisy spws
                    score = 0.82
                    longmsg = f'Phase offsets too noisy to usefully evaluate {ms.basename} SPW {",".join(map(str, sorted(set(noisy_spw_ids))))}'
                    shortmsg = 'Phase offsets too noisy'
                    origin = pqa.QAOrigin(metric_name='Stot(EB, spw)',
                                          metric_score=-999,
                                          metric_units='degrees')
                    data_selection = pqa.TargetDataSelection(vis={ms.basename}, spw=set(noisy_spw_ids), intent={'PHASE'})
                    weblog_location = pqa.WebLogLocation.ACCORDION
                    public_phase_offsets_scores.append(pqa.QAScore(score=score, longmsg=longmsg, shortmsg=shortmsg,
                        vis=ms.basename, origin=origin, applies_to=data_selection, weblog_location=weblog_location))

            return hidden_phase_offsets_scores, public_phase_offsets_scores

        except Exception as e:
            LOG.error('Phase offsets score calculation failed: %s' % (e))
            return [], [pqa.QAScore(-0.1, longmsg='Phase offsets score calculation failed', shortmsg='Phase offsets score calculation failed', vis=ms.basename)]


    def _get_xy_x2x1_qascore(self, ms, phase_field_ids, score_type):
        try:
            (total_score, table_name, field_name, ant_name, spw_name) = \
                self._get_xy_x2x1_total(phase_field_ids, self.xy_x2x1_score_types[score_type][0])
            longmsg = 'Total score for %s is %0.2f (%s field %s %s spw %s)' % (
                self.xy_x2x1_score_types[score_type][1], total_score, ms.basename, field_name, ant_name, spw_name)
            shortmsg = self.xy_x2x1_short_msg[score_type]

            origin = pqa.QAOrigin(metric_name='TimegaincalQAPool',
                                  metric_score=total_score,
                                  metric_units='Total gpcal QA score')

            return pqa.QAScore(total_score, longmsg=longmsg, shortmsg=shortmsg, vis=ms.basename, origin=origin)

        except Exception as e:
            LOG.error('X-Y / X2-X1 score calculation failed: %s' % (e))
            return pqa.QAScore(-0.1, longmsg='X-Y / X2-X1 score calculation failed', shortmsg='X-Y / X2-X1 score calculation failed', vis=ms.basename)

    def _get_xy_x2x1_total(self, phase_field_ids, score_key):
        # attrs to hold score and QA identifiers
        total_score = 1.0
        total_table_name = None
        total_field_name = 'N/A'
        total_ant_name = 'N/A'
        total_spw_name = 'N/A'

        for table_name in self.phase_qa_results_dict:
            qa_result = self.phase_qa_results_dict[table_name]
            for field_id in phase_field_ids:
                qa_context_score = qa_result['QASCORES']['SCORES'][field_id][score_key]
                if qa_context_score['SCORE'] != 'C/C':
                    if qa_context_score['SCORE'] < total_score:
                        total_score = qa_context_score['SCORE']
                        total_field_name = qa_result['QASCORES']['FIELDS'][qa_context_score['FIELD']]
                        total_ant_name = qa_result['QASCORES']['ANTENNAS'][qa_context_score['ANTENNA']]
                        total_spw_name = qa_result['QASCORES']['SPWS'][qa_context_score['SPW']]
                        total_table_name = table_name

        return total_score, total_table_name, total_field_name, total_ant_name, total_spw_name


class TimegaincalQAHandler(pqa.QAPlugin):
    """
    QA handler for an uncontained TimegaincalResult.
    """
    result_cls = common.GaincalResults
    child_cls = None

    def handle(self, context, result):
        vis = result.inputs['vis']
        ms = context.observing_run.get_ms(vis)

        qa_dir = os.path.join(context.report_dir, 'stage%s' % result.stage_number, 'qa')

        if not os.path.exists(qa_dir):
            os.makedirs(qa_dir)

        phase_qa_results_dict = {}
        phase_offsets_qa_results_dict = {}

        try:
            # Get phase cal tables
            for calapp in result.final:
                solint = utils.get_origin_input_arg(calapp, 'solint')
                calmode = utils.get_origin_input_arg(calapp, 'calmode')
                if solint == 'int' and calmode == 'p':
                    phase_qa_results_dict[calapp.gaintable] = gpcal.gpcal(calapp.gaintable)

            # Get phase offsets tables
            for calapp in result.phaseoffsetresult.final:
                phase_offsets_qa_results_dict[calapp.gaintable] = True

            result.qa = TimegaincalQAPool(phase_qa_results_dict, phase_offsets_qa_results_dict)
            result.qa.update_scores(ms, result.inputs['refant'])
        except Exception as e:
            LOG.error('Problem occurred running QA analysis. QA results will not be available for this task')
            LOG.exception(e)


class TimegaincalListQAHandler(pqa.QAPlugin):
    """
    QA handler for a list containing TimegaincalResults.
    """
    result_cls = collections.Iterable
    child_cls = common.GaincalResults

    def handle(self, context, result):
        # collate the QAScores from each child result, pulling them into our
        # own QAscore list
        collated = utils.flatten([r.qa.pool for r in result])
        result.qa.pool[:] = collated
