import collections.abc
import itertools

import pipeline.infrastructure.pipelineqa as pqa
import pipeline.qa.scorecalculator as qacalc
from pipeline import infrastructure
from pipeline.infrastructure import utils
from pipeline.h.tasks.importdata import qa as hqa
from . import importdata

LOG = infrastructure.logging.get_logger(__name__)


class VLAImportDataQAHandler(hqa.ImportDataQAHandler, pqa.QAPlugin):
    result_cls = importdata.VLAImportDataResults
    child_cls = None
    generating_task = importdata.SerialVLAImportData

    def handle(self, context, result):
        score1 = self._check_intents(result.mses)
        score2 = self._check_history_column(result.mses, result.inputs)
        # Check state of IERS tables relative to observation date (PIPE-2137)
        scores3 = self._check_iersstate(result.mses)

        scores = [score1, score2]
        result.qa.pool.extend(scores)
        result.qa.pool.extend(scores3)

    @staticmethod
    def _check_history_column(mses, inputs):
        """
        Check whether any of the measurement sets has entries in the history
        column, potentially signifying a non-pristine data set.
        """
        qascore = hqa.ImportDataQAHandler._check_history_column(mses, inputs)
        if qascore.score < 1.0:
            qascore.longmsg += " If hanning smooth has already been applied in previous execution, invoking hifv_hanning in a following stage means smoothing twice."
        return qascore

    def _check_intents(self, mses):
        """
        Check each measurement set in the list for a set of required intents.

        TODO Should we terminate execution on missing intents?        
        """
        return qacalc.score_missing_intents(mses, array_type='VLA')


class VLAImportDataListQAHandler(pqa.QAPlugin):
    result_cls = collections.abc.Iterable
    child_cls = importdata.VLAImportDataResults

    def handle(self, context, result):
        # collate the QAScores from each child result, pulling them into our
        # own QAscore list
        collated = utils.flatten([r.qa.pool[:] for r in result])
        result.qa.pool.extend(collated)

        # Check per-session parallactic angle coverage of polarisation calibration
        parallactic_threshold = result.inputs['minparang']
        # gather mses into a flat list
        mses = list(itertools.chain(*(r.mses for r in result)))

        # PIPE-836: retrieve parallactic angle from PHASE intents
        # parang_scores not currently needed but could be used in the future
        intents_to_test = {'PHASE', 'POLLEAKAGE'}
        parang_scores, parang_ranges = qacalc.score_parallactic_angle_range(mses, intents_to_test, parallactic_threshold)

        # result.qa.pool.extend(parang_scores)
        result.parang_ranges = parang_ranges
