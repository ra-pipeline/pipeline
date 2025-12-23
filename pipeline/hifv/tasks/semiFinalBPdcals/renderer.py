from pipeline.hifv.tasks.common.renderer import renderer as baseRenderer
from pipeline.infrastructure.utils.profiling import profile_io

class T2_4MDetailssemifinalBPdcalsRenderer(baseRenderer.calsRenderer):
    def __init__(self, uri='semifinalbpdcals.mako', description='Semi-final delay and bandpass calibrations',
                 always_rerender=False):
        super().__init__(uri=uri, description=description,
                         always_rerender=always_rerender, taskname="semiFinalBPdcals")

    @profile_io(output_file="semifinalBPdcals_io_log.csv")
    def get_display_context(self, context, results):
        ctx = super().get_display_context(context, results)
        return ctx
