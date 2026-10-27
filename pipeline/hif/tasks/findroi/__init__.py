import pipeline.infrastructure.renderer.qaadapter as qaadapter
import pipeline.infrastructure.renderer.weblog as weblog

from . import qa
from . import renderer
from . import resultobjects
from .findroi import FindROI

qaadapter.registry.register_to_imaging_topic(resultobjects.FindROIResult)

weblog.add_renderer(FindROI, renderer.T2_4MDetailsFindROIRenderer(), group_by=weblog.UNGROUPED)
