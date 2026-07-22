import collections.abc

import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.pipelineqa as pqa
import pipeline.qa.scorecalculator as qacalc
from pipeline.hsd.tasks.common import qautils
from . import baselineflag
from .renderer import accumulate_flag_per_source_spw

LOG = logging.get_logger(__name__)


class SDBLFlagListQAHandler(pqa.QAPlugin):
    result_cls = collections.abc.Iterable
    child_cls = baselineflag.SDBLFlagResults

    def __init__(self):
        """
        register the parameters for longmsg formatter and aggregator
        """
        # register the properties for 'qacalc.score_sdtotal_data_flagged'
        metric_name = 'score_sdtotal_data_flagged'
        keys = ['field', 'spw']
        qautils.registry.register_longmsg_keys(metric_name, keys)
        qautils.registry.register_keys_to_aggregate(metric_name, keys)

    def handle(self, context, result):
        # Accumulate flag per field, spw to a dictionary
        # accum_flag[field][spw] = {'additional': # of flagged in task, 'total': # of total}
        accum_flag = accumulate_flag_per_source_spw(context, result)
        # Now define score per field, spw
        scores = []
        for field, spwflag in accum_flag.items():
            for spw, flagval in spwflag.items():
                frac_flagged = flagval['additional'] / float(flagval['total'])
                scores.append(qacalc.score_sdtotal_data_flagged(frac_flagged, ms_name=None, field=field, spw=spw))

        # reformat the messages and append to result.qa.pool
        formatter = qautils.QAScoreFormatter()
        for qascore in scores:
            formatter.update_longmsg(qascore)

        result.qa.pool[:] = scores


class SDBLFlagQAHandler(pqa.QAPlugin):
    result_cls = baselineflag.SDBLFlagResults
    child_cls = None

    def __init__(self):
        """
        register the parameters for longmsg formatter and aggregator
        """
        # register the properties for 'qacalc.score_sdtotal_data_flagged'
        metric_name = 'qacalc.score_sdtotal_data_flagged'
        keys = ['vis', 'field', 'spw']
        qautils.registry.register_longmsg_keys(metric_name, keys)
        qautils.registry.register_keys_to_aggregate(metric_name, keys)

    def handle(self, context, result):
        # temporarily encapsulate result in a list so that we can use the same
        # QA scoring function as the aggregate ResultsList
        accum_flag = accumulate_flag_per_source_spw(context, [result])

        ms_name = result.inputs['vis']

        # Now define score per field, spw
        scores = []
        for field, spwflag in accum_flag.items():
            for spw, flagval in spwflag.items():
                frac_flagged = flagval['additional'] / float(flagval['total'])
                scores.append(qacalc.score_sdtotal_data_flagged(frac_flagged, ms_name=ms_name, field=field, spw=spw))

        # reformat the messages and append to result.qa.pool
        formatter = qautils.QAScoreFormatter()
        for qascore in scores:
            formatter.update_longmsg(qascore)

        result.qa.pool[:] = scores


# from pipeline.h.tasks.exportdata import aqua
# aqua_exporter = aqua.xml_generator_for_metric('score_sdtotal_data_flagged', '{:0.3%}')
# aqua.register_aqua_metric(aqua_exporter)
