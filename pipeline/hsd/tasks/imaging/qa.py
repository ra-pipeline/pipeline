from pipeline.hsd.tasks.common import qautils
import pipeline.infrastructure.logging as logging
import pipeline.qa.scorecalculator as qacalc
import pipeline.infrastructure.utils as utils
import pipeline.infrastructure.pipelineqa as pqa
import pipeline.h.tasks.exportdata.aqua as aqua
from pipeline.hsd.tasks.common import utils as sdutils
from . import imaging
from . import resultobjects

LOG = logging.get_logger(__name__)


class SDImagingQAHandler(pqa.QAPlugin):
    """
    SDImagingQAHandler is qa handler for each image product represented
    as the SDImagingResultItem instance.
    """
    result_cls = resultobjects.SDImagingResultItem
    child_cls = None
    generating_task = imaging.SDImaging

    IMAGE_RELATED_QASCORES = ['SingleDishImageMaskedPixels',
                            'score_sd_line_emission_off_range_at_peak',
                            'score_sd_line_emission_off_range_extended',
                            'SingleDishImageContamination',
                            'score_sd_image_sensitivity_ratio']
    IMAGE_RELATED_QASCORES_KEYS = ['field', 'spw']

    RASTERSCAN_RELATED_QASCORES = ['score_rasterscan_correctness']
    RASTERSCAN_RELATED_QASCORES_KEYS = ['vis', 'ant']

    def __init__(self):
        """
        register the parameters for longmsg formatter and aggregator
        """
        # register the properties
        for metric_name in self.IMAGE_RELATED_QASCORES:
            qautils.registry.register_longmsg_keys(metric_name, self.IMAGE_RELATED_QASCORES_KEYS)
            qautils.registry.register_keys_to_aggregate(metric_name, self.IMAGE_RELATED_QASCORES_KEYS)
        for metric_name in self.RASTERSCAN_RELATED_QASCORES:
            qautils.registry.register_longmsg_keys(metric_name, self.RASTERSCAN_RELATED_QASCORES_KEYS)
            qautils.registry.register_keys_to_aggregate(metric_name, self.RASTERSCAN_RELATED_QASCORES_KEYS)

    def handle(self, context, result):
        """
        This handles single SDImagingResultItem.
        """
        # result.outcome should have 'image'
        if 'image' not in result.outcome:
            return

        # we only evaluate the score for combined image
        antenna_name = result.outcome['image'].antenna
        if antenna_name != 'COMBINED':
            return

        # accumulate QAScore
        scores = []

        score_masked = qacalc.score_sdimage_masked_pixels(context, result)
        scores.append(score_masked)

        score_sd_line_emission_off_range_at_peak = qacalc.score_sd_line_emission_off_range_at_peak(context, result)
        scores.append(score_sd_line_emission_off_range_at_peak)

        score_sd_line_emission_off_range_extended = qacalc.score_sd_line_emission_off_range_extended(context, result)
        scores.append(score_sd_line_emission_off_range_extended)

        score_contamination = qacalc.score_sdimage_contamination(context, result)
        scores.append(score_contamination)

        if result.sensitivity_info is not None:
            score_sd_sensitivity_ratio = qacalc.score_sdimage_sensitivity_ratio(result)
            scores.append(score_sd_sensitivity_ratio)

        # If NRO, these 'may' run twice for I and XXYY,
        # resulting in duplicated lines for 'score_rasterscan_correctness' in the AQUA report.
        # Weblog accordion will be 'aggregated', which 'should solve' the duplication (as a result).
        score_resterscan_raster_gap = qacalc.score_rasterscan_correctness_imaging_raster_gap(result)
        scores.extend(score_resterscan_raster_gap)

        score_resterscan_incomplete = qacalc.score_rasterscan_correctness_imaging_raster_analysis_incomplete(result)
        scores.extend(score_resterscan_incomplete)

        # Override registry for NRO to add 'pol' to longmsg_keys and keys_to_aggregate
        # for IMAGE_RELATED_QASCORES.
        # Placed here since this cannot be done in __init__() under the current framework.
        # Those in RASTERSCAN_RELATED_QASCORES are excluded, since they are absolutely
        # pol independent by definition and should not show pol in their QA message.
        if sdutils.is_nro(context):
            for metric_name in self.IMAGE_RELATED_QASCORES:
                longmsg_keys = qautils.registry.get_longmsg_keys(metric_name)
                if 'pol' not in longmsg_keys:
                    longmsg_keys.append('pol')
                qautils.registry.register_longmsg_keys(metric_name, longmsg_keys)
                keys_to_aggregate = qautils.registry.get_keys_to_aggregate(metric_name)
                if 'pol' not in keys_to_aggregate:
                    keys_to_aggregate.append('pol')
                qautils.registry.register_longmsg_keys(metric_name, keys_to_aggregate)

        # reformat the messages and append to result.qa.pool
        formatter = qautils.QAScoreFormatter()
        for qascore in scores:
            formatter.update_longmsg(qascore)
        result.qa.pool.extend(scores)


class SDImagingListQAHandler(pqa.QAPlugin):
    """
    SDImagingListQAHandler is qa handler for a list of image products
    represented as the SDImagingResults. SDImagingResults is a subclass
    of ResultsList and contains SDImagingResultsItem instances.
    """
    result_cls = resultobjects.SDImagingResults
    child_cls = resultobjects.SDImagingResultItem

    def handle(self, context, result):
        # collate the QAScores from each child result, pulling them into our
        # own QAscore list
        collated = utils.flatten([r.qa.pool for r in result])
        result.qa.pool[:] = collated


aqua_exporter = aqua.xml_generator_for_metric('SingleDishImageMaskedPixels', '{:0.3}')
aqua.register_aqua_metric(aqua_exporter)
