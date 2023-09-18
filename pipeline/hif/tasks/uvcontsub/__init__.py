import pipeline.infrastructure.renderer.qaadapter as qaadapter
import pipeline.infrastructure.renderer.weblog as weblog
from . import qa
from . import renderer
from . import uvcontsub
from .uvcontsub import UVcontSub

qaadapter.registry.register_to_dataset_topic(uvcontsub.UVcontSubResults)

weblog.add_renderer(UVcontSub, renderer.T2_4MDetailsUVcontSubRenderer(), group_by=weblog.UNGROUPED)
