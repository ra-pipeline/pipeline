"""QA scoring handlers for VLASetjy tasks."""

from __future__ import annotations

import collections.abc
from typing import TYPE_CHECKING

import pipeline.infrastructure.pipelineqa as pqa
import pipeline.infrastructure.utils as utils
from pipeline import infrastructure
from pipeline.h.tasks.common import commonfluxresults
from pipeline.infrastructure import casa_tasks

from . import vlasetjy

if TYPE_CHECKING:
    from pipeline.infrastructure.launcher import Context

LOG = infrastructure.logging.get_logger(__name__)


class VLASetjyQAHandler(pqa.QAPlugin):
    """QA handler for VLASetjy results."""

    result_cls = commonfluxresults.FluxCalibrationResults
    child_cls = None
    generating_task = vlasetjy.VLASetjy

    def handle(self, context: Context, result: commonfluxresults.FluxCalibrationResults) -> None:
        """Score flux calibration results for VLA standard calibrators."""
        vis = result.inputs['vis']
        standard_source_names, standard_source_fields = vlasetjy.standard_sources(vis)
        m = context.observing_run.get_ms(vis)
        scores = []

        if not any(standard_source_fields):
            score = pqa.QAScore(
                0.0, longmsg='No VLA standard calibrator present', shortmsg='No standard calibrator present.'
            )
            scores.append(score)
        else:
            # Find standard calibrators that have fields with AMPLITUDE intent
            standard_sources_with_amp = []
            for name, fields in zip(standard_source_names, standard_source_fields):
                amp_fields = []
                for myfield in fields:
                    domainfields = m.get_fields(myfield)
                    if domainfields and 'AMPLITUDE' in domainfields[0].intents:
                        amp_fields.append(myfield)
                if amp_fields:
                    standard_sources_with_amp.append((name, amp_fields))

            if not standard_sources_with_amp:
                score = pqa.QAScore(
                    0.0, longmsg='No flux calibration intent found', shortmsg='No flux calibration intent found'
                )
                scores.append(score)
            else:
                cal_field_ids = [str(f) for _, amp_fields in standard_sources_with_amp for f in amp_fields]
                calfields = ','.join(cal_field_ids)
                flagdata_task = casa_tasks.flagdata(vis=vis, mode='summary', field=calfields, intent='*CALIBRATE*')
                flagdata_result = flagdata_task.execute()
                flagdata_fields = flagdata_result.get('field', {}) if isinstance(flagdata_result, dict) else {}

                for name, amp_fields in standard_sources_with_amp:
                    field_names = {m.get_fields(f)[0].name.strip('"') for f in amp_fields if m.get_fields(f)}

                    total_flagged = 0
                    total = 0
                    for fname in field_names:
                        field_stats = flagdata_fields.get(fname)
                        if field_stats:
                            total_flagged += field_stats.get('flagged', 0)
                            total += field_stats.get('total', 0)

                    ms_fields_str = ', '.join(sorted(field_names))
                    cal_name_str = f'{name} ({ms_fields_str})' if ms_fields_str != name else name

                    if total > 0 and (total_flagged / total) < 0.995:
                        scorevalue = 1.0
                        msg = f'Standard calibrator {cal_name_str} present.'
                    else:
                        scorevalue = 0.0
                        msg = f'Standard calibrator {cal_name_str} is fully flagged'

                    score = pqa.QAScore(scorevalue, longmsg=msg, shortmsg=msg)
                    scores.append(score)

        result.qa.pool.extend(scores)


class VLASetjyListQAHandler(pqa.QAPlugin):
    """QA handler for a list containing FluxCalibrationResults."""

    result_cls = collections.abc.Iterable
    child_cls = commonfluxresults.FluxCalibrationResults

    def handle(
        self, context: Context, result: collections.abc.Iterable[commonfluxresults.FluxCalibrationResults]
    ) -> None:
        """Collate QAScores from each child result into our own QAScore list."""
        collated = utils.flatten([r.qa.pool for r in result])
        result.qa.pool[:] = collated

        mses = [r.inputs['vis'] for r in result]
        longmsg = 'No missing flux measurements in %s' % utils.commafy(mses, quotes=False, conjunction='or')
        result.qa.all_unity_longmsg = longmsg
