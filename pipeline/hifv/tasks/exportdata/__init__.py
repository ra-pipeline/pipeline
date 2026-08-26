# import pipeline.infrastructure.pipelineqa as pipelineqa
import pipeline.infrastructure.renderer.weblog as weblog
import pipeline.infrastructure.renderer.basetemplates as basetemplates

from . import renderer
from .vlaexportdata import VLAExportData

# Add QA handers if necesssary
# from . import qa
#
# pipelineqa.registry.add_handler(qa.VLAExportDataQAHandler())

# Use the VLA-specific ExportData renderer to render VLAExportData results
weblog.add_renderer(VLAExportData,
                    renderer.T2_4MDetailsVLAExportDataRenderer(),
                    group_by=weblog.UNGROUPED)
