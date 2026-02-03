"""
Created on 5 Sep 2014

@author: sjw
"""
from pipeline import infrastructure
from pipeline.h.tasks.importdata import renderer
from pipeline.infrastructure.renderer import rendererutils

LOG = infrastructure.logging.get_logger(__name__)


class T2_4MDetailsALMAImportDataRenderer(renderer.T2_4MDetailsImportDataRenderer):
    def __init__(self, uri='almaimportdata.mako',
                 description='Register measurement sets with the pipeline',
                 always_rerender=False):
        super().__init__(uri=uri, description=description, always_rerender=always_rerender)

    def update_mako_context(self, mako_context, pipeline_context, result):
        super().update_mako_context(mako_context, pipeline_context, result)

        cache = result.metadata.get('weblog_importdata_parang', {}) if hasattr(result, 'metadata') else {}
        if cache:
            minparang = cache.get('minparang')
            parang_ranges = cache.get('parang_ranges')
            parang_plots = cache.get('parang_plots', {})
        else:
            minparang = result.inputs['minparang']
            parang_ranges = result.parang_ranges
            if parang_ranges['intents_found']:
                parang_plots = rendererutils.make_parang_plots(
                    pipeline_context,
                    result,
                    intent_lookup={'POLARIZATION': 'CALIBRATE_POLARIZATION#ON_SOURCE'},
                    )
            else:
                parang_plots = {}

        mako_context.update({
            'minparang': minparang,
            'parang_ranges': parang_ranges,
            'parang_plots': parang_plots,
        })
