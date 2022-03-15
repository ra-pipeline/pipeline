import pipeline.infrastructure.renderer.basetemplates as basetemplates
import pipeline.infrastructure.renderer.qaadapter as qaadapter
import pipeline.infrastructure.renderer.weblog as weblog

from .splitline import Splitline
from . import splitline

#qaadapter.registry.register_to_dataset_topic(splitline.SplitlineResults)

weblog.add_renderer(Splitline,
                    basetemplates.T2_4MDetailsDefaultRenderer(uri='splitline.mako',
                                                              description='Splitline'),
                    group_by=weblog.UNGROUPED)
