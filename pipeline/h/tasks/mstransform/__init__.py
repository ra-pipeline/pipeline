import pipeline.infrastructure.renderer.qaadapter as qaadapter
import pipeline.infrastructure.renderer.weblog as weblog
from . import mssplit
from . import mstransform
from . import qa
from . import renderer
from .mssplit import MsSplit
from .mstransform import Mstransform, SerialMstransform

qaadapter.registry.register_to_dataset_topic(mssplit.MsSplitResults)
qaadapter.registry.register_to_dataset_topic(mstransform.MstransformResults)

weblog.add_renderer(MsSplit, renderer.T2_4MDetailsMsSplitRenderer(), group_by=weblog.UNGROUPED)
weblog.add_renderer(Mstransform, renderer.T2_4MDetailsMstransformRenderer(), group_by=weblog.UNGROUPED)
weblog.add_renderer(SerialMstransform, renderer.T2_4MDetailsMstransformRenderer(), group_by=weblog.UNGROUPED)

