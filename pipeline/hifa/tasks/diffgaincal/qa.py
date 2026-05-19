import collections.abc

import numpy as np

import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.pipelineqa as pqa
import pipeline.infrastructure.utils as utils
import pipeline.qa.scorecalculator as qacalc
from pipeline.domain.measurementset import MeasurementSet
from pipeline.h.tasks.common import commonhelpermethods
from pipeline.infrastructure import casa_tools

from . import diffgaincal

LOG = logging.get_logger(__name__)

# PIPE-2689: threshold to declare if overall SNR is low.
THRESHOLD_OVERALL_SNR = 5.0


class DiffgaincalQAHandler(pqa.QAPlugin):
    """
    QA handler for an uncontained DiffgaincalResults.
    """
    result_cls = diffgaincal.DiffGaincalResults
    child_cls = None
    generating_task = diffgaincal.DiffGaincal

    def handle(self, context, result):
        ms = context.observing_run.get_ms(result.inputs['vis'])
        # Only create QA scores for BandToBand measurement sets:
        if ms.is_band_to_band:
            # Add scoring of gaincal results w.r.t. SpW combination and missing/
            # flagged data.
            result.qa.pool.extend(self._score_gaincal_result(ms, result.ref_phase_result,
                                                             caltable_type='diffgaincal reference caltable',
                                                             phaseup_type='low frequency reference'))
            result.qa.pool.extend(self._score_gaincal_result(ms, result,
                                                             caltable_type='diffgaincal B2B offset caltable',
                                                             phaseup_type='offset'))
            result.qa.pool.extend(self._score_gaincal_result(ms, result.residual_phase_result,
                                                             caltable_type='diffgaincal residual caltable',
                                                             phaseup_type='residual diagnostics'))

            # QA scores for the diagnostic phase residuals caltable.
            result.qa.pool.extend(self._score_residual_phase_caltable(ms, result.residual_phase_result))

    @staticmethod
    def _extract_info_residual_phase(ms: MeasurementSet, result) -> dict:
        """
        Compute statistics on diffgain residual phase offsets.

        Args:
            ms: MeasurementSet to analyse.
            result: GaincalResults instance for diffgain residual phase offsets.

        Returns:
            Dictionary containing statistics on residual phase offsets
        """
        # Create antenna ID to name translation dictionary, reject empty antenna name strings.
        antenna_id_to_name = {ant.id: ant.name for ant in ms.antennas if ant.name.strip()}

        # Retrieve data from caltable.
        caltable = result.final[0].gaintable
        with casa_tools.TableReader(caltable) as table:
            spwids = table.getcol("SPECTRAL_WINDOW_ID")
            flags = table.getcol("FLAG")
            snrs = table.getcol("SNR")
            ant_ids = table.getcol("ANTENNA1")
            refant_id = table.getcol("ANTENNA2")
            cparams = table.getcol("CPARAM")

        # filter the ant_ids to use - dont assess the refant
        ant_loop = np.unique(np.array([ant_id for ant_id in ant_ids if ant_id not in refant_id]))

        # Convert phase to angles in degrees.
        angles = np.degrees(np.angle(cparams))

        # Get number of polarizations (aka correlations). It is assumed here
        # that all SpWs have the same number of polarizations, so retrieve
        # arbitrarily from 1st SpW ID.
        corr_type = commonhelpermethods.get_corr_products(ms, spwids[0]) if len(spwids) > 0 else []

        # Initialize dictionary for collecting statistics.
        residual_data = {}
        for spwid in sorted(set(spwids)):
            # Select data for current SpW and exclude the reference antenna.
            ind_spw_ant = np.where((spwids == spwid) & (ant_ids != np.unique(refant_id)))[0]

            # Compute statistics separately for each correlation (polarization).
            for icorr, corr in enumerate(corr_type):
                # Select phase angles, SNRs, and corresponding flags for current
                # pol and SpW, turn into masked arrays. The channel dimension is expected to be length 1, so just pick element 0.
                flags_sel = flags[icorr, 0, ind_spw_ant]
                angles_sel = angles[icorr, 0, ind_spw_ant]
                angles_sel_masked = np.ma.masked_array(angles_sel, flags_sel)
                snrs_sel = snrs[icorr, 0, ind_spw_ant]
                snrs_sel_masked = np.ma.masked_array(snrs_sel, flags_sel)

                # Compute mean and RMS for phase angles.
                residual_data[(spwid, corr, 'all', 'mean')] = np.ma.mean(angles_sel_masked)
                residual_data[(spwid, corr, 'all', 'rms')] = np.ma.std(angles_sel_masked)
                # Compute mean for SNRs.
                residual_data[(spwid, corr, 'all', 'snr')] = np.ma.mean(snrs_sel_masked)

                # For each antenna, compute max, mean, and RMS for phase angles.
                for ant_id in ant_loop: # only loop over the unique antennas and below find the respective index from the array of solns
                    ant_name = antenna_id_to_name[ant_id]
                    # Select data for current SpW, polarization, and antenna.
                    ant_idx = np.where((ant_ids == ant_id) & (spwids == spwid))[0]
                    angles_sel = angles[icorr, 0, ant_idx]
                    flags_sel = flags[icorr, 0, ant_idx]
                    angles_sel_masked = np.ma.masked_array(angles_sel, flags_sel)

                    # Compute statistics.
                    residual_data[(spwid, corr, ant_name, 'max')] = np.ma.max(np.abs(angles_sel_masked))
                    residual_data[(spwid, corr, ant_name, 'mean')] = np.ma.mean(angles_sel_masked)
                    residual_data[(spwid, corr, ant_name, 'rms')] = np.ma.std(angles_sel_masked)

        # Compute stats across all SpWs, per polarization.
        ind_all = np.where(ant_ids != np.unique(refant_id))[0]
        for icorr, corr in enumerate(corr_type):
            # Select data for current polarization.
            flags_all = flags[icorr, 0, ind_all]
            angles_all = angles[icorr, 0, ind_all]
            angles_all_masked = np.ma.masked_array(angles_all, flags_all)
            snrs_all = snrs[icorr, 0, ind_all]
            snrs_all_masked = np.ma.masked_array(snrs_all, flags_all)

            # Compute mean and RMS for phase angles across all antennas (except refant).
            residual_data[('all', corr, 'all', 'mean')] = np.ma.mean(angles_all_masked)
            residual_data[('all', corr, 'all', 'rms')] = np.ma.std(angles_all_masked)
            # Compute mean for SNRs across all antennas (except refant).
            residual_data[('all', corr, 'all', 'snr')] = np.ma.mean(snrs_all_masked)

        # Filter out entries that are masked; these can occur where the original
        # data selection was entirely masked due to flagging.
        residual_data = {k: v for k, v in residual_data.items() if not np.ma.is_masked(v)}

        # Compute overall mean SNR value and check if this is below a threshold.
        snr_values = [v for (spwid, _, _, stat), v in residual_data.items() if stat == 'snr' and spwid != 'all']
        snr_overall = np.mean(snr_values) if snr_values else 0.
        low_snr = snr_overall < THRESHOLD_OVERALL_SNR

        # Collect into output dictionary.
        residuals_info = {
            "ms_name": ms.basename,
            "intent": result.inputs['intent'],
            "field": result.inputs['field'],
            "data": residual_data,
            "low_snr": low_snr,
        }
        return residuals_info

    @staticmethod
    def _score_gaincal_result(ms: MeasurementSet, result, caltable_type, phaseup_type) -> list[pqa.QAScore]:
        """Score the band-to-band result and caltable."""
        scores = []
        if result is None:
            return scores

        if result.final:
            gaintable = result.final[0].gaintable
            # Retrieve combine parameter for gaintable result and create score
            # for whether spw combination was used.
            combine = utils.get_origin_input_arg(result.pool[0], 'combine')
            scores.append(qacalc.score_diffgaincal_combine(ms.name, combine, result.qa_message, phaseup_type))
        elif result.error:
            gaintable = list(result.error)[0].gaintable
        else:
            gaintable = None

        # Create score for whether caltable exists.
        scores.append(qacalc.score_path_exists(ms.name, gaintable, caltable_type))

        return scores

    def _score_residual_phase_caltable(self, ms: MeasurementSet, result) -> list[pqa.QAScore]:
        scores = []
        # Extract info from band-to-band caltable.
        residuals_info = self._extract_info_residual_phase(ms, result)

        # Compute QA scores.
        for score_type in ['offsets', 'rms', 'outliers']:
            scores.append(qacalc.score_diffgaincal_residuals(residuals_info, score_type=score_type))

        return scores


class DiffgaincalListQAHandler(pqa.QAPlugin):
    """
    QA handler for a list containing DiffgaincalResults.
    """
    result_cls = collections.abc.Iterable
    child_cls = diffgaincal.DiffGaincalResults
    generating_task = diffgaincal.DiffGaincal

    def handle(self, context, result):
        # collate the QAScores from each child result, pulling them into our
        # own QAscore list
        collated = utils.flatten([r.qa.pool for r in result])
        result.qa.pool[:] = collated

        mses = [r.inputs['vis'] for r in result]
        longmsg = f"Diffgain phase caltables created for {utils.commafy(mses, quotes=False, conjunction='and')}"
        result.qa.all_unity_longmsg = longmsg
