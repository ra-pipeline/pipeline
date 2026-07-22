import pipeline.infrastructure.renderer.weblog as weblog
import pipeline.hsd.tasks.tsysflag.renderer as renderer

from .tsysflag import SerialTsysflag  # , Tsysflag

weblog.add_renderer(SerialTsysflag, renderer.T2_4MDetailsSDTsysflagRenderer(), group_by=weblog.UNGROUPED)
# weblog.add_renderer(Tsysflag, super_renderer.T2_4MDetailsTsysflagRenderer(), group_by=weblog.UNGROUPED)
