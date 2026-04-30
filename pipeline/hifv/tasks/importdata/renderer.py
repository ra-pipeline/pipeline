import functools
import operator

from pipeline import infrastructure
from pipeline.infrastructure.renderer import basetemplates, rendererutils

LOG = infrastructure.logging.get_logger(__name__)


class T2_4MDetailsVLAImportDataRenderer(basetemplates.T2_4MDetailsDefaultRenderer):
    def __init__(self, uri='vlaimportdata.mako', 
                 description='Register VLA measurement sets with the pipeline', 
                 always_rerender=False):
        super().__init__(
            uri=uri, description=description, always_rerender=always_rerender)

    def get_display_context(self, context, result):
        super_cls = super()
        ctx = super_cls.get_display_context(context, result)

        setjy_results = []
        for r in result:
            setjy_results.extend(r.setjy_results)

        measurements = []        
        for r in setjy_results:
            measurements.extend(r.measurements)

        num_mses = functools.reduce(operator.add, [len(r.mses) for r in result])

        ctx.update({'flux_imported': True if measurements else False,
                    'setjy_results': setjy_results,
                    'num_mses': num_mses})

        return ctx

    def update_mako_context(self, mako_context, pipeline_context, result):
        super().update_mako_context(mako_context, pipeline_context, result)

        minparang = result.inputs['minparang']
        parang_ranges = result.parang_ranges
        if parang_ranges['intents_found']:
            parang_plots = rendererutils.make_parang_plots(
                pipeline_context,
                result,
                intent_lookup={
                    'PHASE': 'CALIBRATE_PHASE#UNSPECIFIED',
                    'POLLEAKAGE': 'CALIBRATE_POL_LEAKAGE#UNSPECIFIED',
                    },
                )
        else:
            parang_plots = {}

        mako_context.update({
            'minparang': minparang,
            'parang_ranges': parang_ranges,
            'parang_plots': parang_plots,
        })
