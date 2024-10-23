"""ALMA Single Dish Tasks
"""
from docstring_inheritance import inherit_google_docstring

from .hsd_applycal import hsd_applycal
from .hsd_atmcor import hsd_atmcor
from .hsd_baseline import hsd_baseline
from .hsd_blflag import hsd_blflag
from .hsd_exportdata import hsd_exportdata
from .hsd_flagdata import hsd_flagdata
from .hsd_imaging import hsd_imaging
from .hsd_importdata import hsd_importdata
from .hsd_k2jycal import hsd_k2jycal
from .hsd_restoredata import hsd_restoredata
from .hsd_skycal import hsd_skycal
from .hsd_tsysflag import hsd_tsysflag

from pipeline.h.cli import utils as utils
from pipeline.hsd.tasks.baseline.baseline import SDBaselineInputs

__all__ = ['hsd_applycal',
           'hsd_atmcor',
           'hsd_baseline',
           'hsd_blflag',
           'hsd_exportdata',
           'hsd_flagdata',
           'hsd_imaging',
           'hsd_importdata',
           'hsd_k2jycal',
           'hsd_restoredata',
           'hsd_skycal',
           'hsd_tsysflag']

inherit_google_docstring(SDBaselineInputs.__init__.__doc__, hsd_baseline)
utils.inherit_type_hints(SDBaselineInputs.__init__, hsd_baseline)
