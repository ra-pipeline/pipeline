import collections.abc

import pipeline.infrastructure.pipelineqa as pqa
import pipeline.infrastructure.utils as utils
from pipeline import infrastructure
from pipeline.h.tasks.common import commonfluxresults
from pipeline.infrastructure import casa_tasks
from . import vlasetjy

LOG = infrastructure.logging.get_logger(__name__)


class VLASetjyQAHandler(pqa.QAPlugin):
    result_cls = commonfluxresults.FluxCalibrationResults
    child_cls = None
    generating_task = vlasetjy.VLASetjy

    def handle(self, context, result):
        vis = result.inputs['vis']
        _, standard_source_fields = vlasetjy.standard_sources(vis)
        m = context.observing_run.get_ms(vis)
        scores = []
        if sum(standard_source_fields, []):
            scorevalue = 0.0
            msg = ''
            field_ids = [str(fieldid) for sublist in standard_source_fields for fieldid in sublist]
            calfields = ",".join(field_ids)
            flagdata_task = casa_tasks.flagdata(vis=vis, mode="summary", field=calfields, intent='*CALIBRATE*')
            flagdata_result = flagdata_task.execute()
            for fields in standard_source_fields:
                field_intents = set()
                for myfield in fields:
                    field_intents.update(m.get_fields(myfield)[0].intents)
                if len(fields) != 0:
                    domainfield = m.get_fields(fields[0])[0]
                    if 'AMPLITUDE' in field_intents:
                        total_flagged = flagdata_result['field'][domainfield.name.strip('"')]['flagged']
                        total = flagdata_result['field'][domainfield.name.strip('"')]['total']
                        if (total_flagged/total) < 0.995:
                            scorevalue = 1.0
                            msg = 'Standard calibrator present.'
                        else:
                            scorevalue = 0.0
                            msg = "Standard calibrator is fully flagged"
                    else:
                        scorevalue = 0.0
                        msg = 'No flux calibration intent found'
                    score = pqa.QAScore(scorevalue, longmsg=msg, shortmsg=msg)
                    scores.append(score)
        else:
            score = pqa.QAScore(0.0,
                                longmsg='No VLA standard calibrator present', shortmsg='No standard calibrator present.')

            scores.append(score)

        result.qa.pool.extend(scores)

        """
        vis = result.inputs['vis']
        ms = context.observing_run.get_ms(vis)
        if 'spw' in result.inputs:
            spw = result.inputs['spw']
        else:
            spw = ''

        # Check for the existence of the expected flux measurements
        # and assign a score based on the fraction of actual to
        # expected ones.
        scores = [qacalc.score_setjy_measurements(ms, result.inputs['field'],
                  result.inputs['intent'], spw, result.measurements)]
        result.qa.pool[:] = scores
        result.qa.all_unity_longmsg = 'No missing flux measurements in %s' % ms.basename
        """


class VLASetjyListQAHandler(pqa.QAPlugin):
    """
    QA handler for a list containing FluxCalibrationResults.
    """
    result_cls = collections.abc.Iterable
    child_cls = commonfluxresults.FluxCalibrationResults

    def handle(self, context, result):
        # collate the QAScores from each child result, pulling them into our
        # own QAscore list
        collated = utils.flatten([r.qa.pool for r in result])
        result.qa.pool[:] = collated

        mses = [r.inputs['vis'] for r in result]
        longmsg = 'No missing flux measurements in %s' % utils.commafy(mses, quotes=False, conjunction='or')
        result.qa.all_unity_longmsg = longmsg
