import pipeline.infrastructure.renderer.weblog as weblog
import pipeline.infrastructure.renderer.basetemplates as super_renderer
import pipeline.hsd.tasks.exportdata.renderer as renderer
from .exportdata import SDExportData

weblog.add_renderer(SDExportData, 
                    super_renderer.T2_4MDetailsDefaultRenderer(always_rerender=False),
                    group_by=weblog.UNGROUPED)
