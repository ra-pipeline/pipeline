import collections

import numpy as np

import pipeline.infrastructure.logging as logging
import pipeline.infrastructure.renderer.basetemplates as basetemplates
from pipeline.infrastructure import casa_tools

LOG = logging.get_logger(__name__)

TR = collections.namedtuple('TR', 'robust uvtaper beam cell beamRatio bandwidth bwmode sensitivity')


class T2_4MDetailsCheckProductSizeRenderer(basetemplates.T2_4MDetailsDefaultRenderer):
    def __init__(self,
                 uri='imageprecheck.mako',
                 description='Image pre-check',
                 always_rerender=True):
        super(T2_4MDetailsCheckProductSizeRenderer, self).__init__(uri=uri,
                                                           description=description,
                                                           always_rerender=always_rerender)

    def update_mako_context(self, mako_context, pipeline_context, results):
        # as a multi-vis task, there's only one result for ImagePreCheck
        result = results[0]

        table_rows = self._get_table_rows(pipeline_context, result)

        mako_context.update({'table_rows': table_rows})

    def _get_table_rows(self, context, result):

        cqa = casa_tools.quanta

        rows = []

        minAR_v = cqa.getvalue(cqa.convert(result.minAcceptableAngResolution, 'arcsec'))
        maxAR_v = cqa.getvalue(cqa.convert(result.maxAcceptableAngResolution, 'arcsec'))

        for item in result.sensitivities:
            robust = item['robust']
            uvtaper = item['uvtaper']
            try:
                bmin_v = cqa.getvalue(cqa.convert(item['beam']['minor'], 'arcsec'))
            except:
                bmin_v = 'N/A'
            try:
                bmaj_v = cqa.getvalue(cqa.convert(item['beam']['major'], 'arcsec'))
            except:
                bmaj_v = 'N/A'
            try:
                bpa_v = cqa.getvalue(cqa.convert(item['beam']['positionangle'], 'deg'))
            except:
                bpa_v = 'N/A'
            try:
                beam = '%#.3g x %#.3g arcsec @ %#.3g deg' % (np.asarray(bmaj_v).item(), np.asarray(bmin_v).item(), np.asarray(bpa_v).item())
            except:
                beam = 'N/A'
            try:
                robustAR_v = bmin_v * bmaj_v
                meanAR_v = minAR_v * maxAR_v
                if (meanAR_v != 0.0):
                    beam_vs_minAR_maxAR = '%.1f%%' % (np.asarray(100. * (robustAR_v - meanAR_v) / meanAR_v).item())
                else:
                    beam_vs_minAR_maxAR = 'N/A'
            except:
                beam_vs_minAR_maxAR = 'N/A'
            beamRatio = '%.2f' % (float(cqa.getvalue(result.beamRatios[(robust, str(uvtaper))])[0]))
            if cqa.getvalue(item['cell'][0])[0] != 0.0 and cqa.getvalue(item['cell'][1])[0] != 0.0:
                cell = '%.2g x %.2g arcsec' % (cqa.getvalue(cqa.convert(item['cell'][0], 'arcsec'))[0], cqa.getvalue(cqa.convert(item['cell'][1], 'arcsec'))[0])
            else:
                cell = 'N/A'
            if cqa.getvalue(item['bandwidth'])[0] != 0.0:
                bandwidth = '%.4g MHz' % (cqa.getvalue(cqa.convert(item['bandwidth'], 'MHz'))[0])
            else:
                bandwidth = 'N/A'
            bwmode = item['bwmode']
            if cqa.getvalue(item['theoretical_sensitivity'])[0] != 0.0:
                sensitivity = '%.3g Jy/beam' % (cqa.getvalue(cqa.convert(item['theoretical_sensitivity'], 'Jy/beam'))[0])
            else:
                sensitivity = 'N/A'

            rows.append(TR(robust=robust, uvtaper=uvtaper, beam=beam, cell=cell, beamRatio=beamRatio, bandwidth=bandwidth, bwmode=bwmode, sensitivity=sensitivity))

        return rows
