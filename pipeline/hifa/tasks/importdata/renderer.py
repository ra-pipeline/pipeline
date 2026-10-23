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

        minparang = result.inputs['minparang']
        # Some results (e.g. ResultsList) may not have parang_ranges.
        # Guard access and default to no intents found when absent.
        if hasattr(result, 'parang_ranges') and result.parang_ranges is not None:
            parang_ranges = result.parang_ranges
        else:
            parang_ranges = {'intents_found': False}

        if parang_ranges.get('intents_found'):
            parang_plots = rendererutils.make_parang_plots(
                pipeline_context,
                result,
                intent=['POLARIZATION'],
                )
        else:
            parang_plots = {}

        # PIPE-65 call new rendererutils task for separation angle plots
        sepang_plots = rendererutils.make_separation_plots(
            pipeline_context,
            result,
            )  
        
        if result.sep_angles:
            # where is this from PIPE-836 removed the equivalant parang_ranges
            # from almaimportdata ? 
            sep_table = rendererutils.sep_angles_for_table(pipeline_context, result.sep_angles, sepang_plots) # context is context, result is from QA 
        else:
            sep_table = []  


        mako_context.update({
            'minparang': minparang,
            'parang_ranges': parang_ranges,
            'parang_plots': parang_plots,
            'sepangle_table': sep_table,
            'sepangle_plots': sepang_plots
        })
