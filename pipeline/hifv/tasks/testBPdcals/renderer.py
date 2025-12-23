
from pipeline.hifv.tasks.common.renderer import renderer as baseRenderer
from pipeline.infrastructure.utils.profiling import profile_io

class T2_4MDetailstestBPdcalsRenderer(baseRenderer.calsRenderer):
    def __init__(self, uri='testbpdcals.mako', description='Initial test calibrations',
                 always_rerender=False):
        super().__init__(uri=uri, description=description,
                         always_rerender=always_rerender, taskname="testBPdcals")

    @profile_io(output_file="testbpdcals_io_log.csv")
    def get_display_context(self, context, results):
        ctx = super().get_display_context(context, results)
        return ctx
