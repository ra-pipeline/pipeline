import pipeline.infrastructure.renderer.weblog as weblog
import pipeline.hsd.tasks.exportdata.renderer as renderer
from .exportdata import SDExportData

weblog.add_renderer(SDExportData, 
                    renderer.T2_4MDetailsSDExportDataRenderer(always_rerender=False),
                    group_by=weblog.UNGROUPED)
