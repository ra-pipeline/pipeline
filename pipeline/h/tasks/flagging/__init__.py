import pipeline.infrastructure.renderer.qaadapter as qaadapter
from . import flagdeterbase
from . import flagdatasetter
from . import qa

qaadapter.registry.register_to_flagging_topic(flagdeterbase.FlagDeterBaseResults)
qaadapter.registry.register_to_flagging_topic(flagdatasetter.FlagdataSetterResults)
