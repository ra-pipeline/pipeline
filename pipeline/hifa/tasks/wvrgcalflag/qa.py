import collections.abc
import os

import pipeline.h.tasks.exportdata.aqua as aqua
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.pipelineqa as pqa
import pipeline.infrastructure.utils as utils
import pipeline.infrastructure.renderer.rendererutils as rendererutils
import pipeline.qa.scorecalculator as qacalc
from . import resultobjects

LOG = infrastructure.logging.get_logger(__name__)


class WvrgcalflagQAHandler(pqa.QAPlugin):    
    """QA handler for an uncontained WvrgcalflagResults."""
    result_cls = resultobjects.WvrgcalflagResults
    child_cls = None

    def handle(self, context, result):
        ms_name = os.path.basename(result.inputs['vis'])

        # If too few unflagged antennas were left over after flagging,
        # then return a fixed low score. PIPE-1868: change fixed score of 0.1 to
        # 0.34 (yellow), or 0.67 (blue) if BPgood. Add MS name to longmsg.
        if result.too_few_wvr_post_flagging:
            dataresult = result.flaggerresult.dataresult
            score_too_few = (rendererutils.SCORE_THRESHOLD_WARNING + 0.01  # lowest blue
                             if dataresult.BPgood else
                             rendererutils.SCORE_THRESHOLD_ERROR + 0.01)   # lowest yellow
            if dataresult.BPgood:
                bp_ph = 'Bandpass ' + ('and Phase ' if dataresult.PHgood else '')
                extra = bp_ph + 'calibrator atmospheric phase stability appears to be good'
            else:
                extra = ''
            longmsg_too_few = f'Not enough unflagged WVR available for {ms_name}.'
            if extra:
                longmsg_too_few += f' {extra}'
            score_object = pqa.QAScore(
                score_too_few, longmsg=longmsg_too_few,
                shortmsg='Not enough unflagged WVR', vis=ms_name)
            new_origin = pqa.QAOrigin(
                metric_name='PhaseRmsRatio',
                metric_score=score_object.origin.metric_score,
                metric_units='Phase RMS improvement after applying WVR correction')
            score_object.origin = new_origin
            result.qa.pool[:] = [score_object]
        else:
            # Try to retrieve WVR QA score from result.
            try:
                wvr_score = result.flaggerresult.dataresult.qa_wvr.overall_score
                # If a WVR QA score was available, then adopt this as the
                # final QA score for the task.
                if wvr_score:
                    score_object = qacalc.score_wvrgcal(ms_name, result.flaggerresult.dataresult)
                    new_origin = pqa.QAOrigin(
                        metric_name='PhaseRmsRatio',
                        metric_score=score_object.origin.metric_score,
                        metric_units='Phase RMS improvement after applying WVR correction')
                    score_object.origin = new_origin
                    result.qa.pool[:] = [score_object]
                else:
                    # If wvr_score was not available, check if this is caused
                    # by too few antennas with WVR (set by threshold). If so,
                    # then no QA score is necessary; if not, then set task QA
                    # score to 0.
                    if not result.too_few_wvr:
                        score_object = pqa.QAScore(
                            0.0, longmsg='No WVR scores available',
                            shortmsg='No WVR', vis=ms_name)
                        new_origin = pqa.QAOrigin(
                            metric_name='PhaseRmsRatio',
                            metric_score=score_object.origin.metric_score,
                            metric_units='Phase RMS improvement after applying WVR correction')
                        score_object.origin = new_origin
                        result.qa.pool[:] = [score_object]
            except AttributeError:
                pass


class WvrgcalflagListQAHandler(pqa.QAPlugin):
    """
    QA handler for a list containing WvrgcalflagResults.
    """
    result_cls = collections.abc.Iterable
    child_cls = resultobjects.WvrgcalflagResults

    def handle(self, context, result):
        # collate the QAScores from each child result, pulling them into our
        # own QAscore list
        collated = utils.flatten([r.qa.pool for r in result]) 
        result.qa.pool[:] = collated


aqua_exporter = aqua.xml_generator_for_metric('PhaseRmsRatio', '{:0.3f}')
aqua.register_aqua_metric(aqua_exporter)
