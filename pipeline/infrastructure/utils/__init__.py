"""utils sub-package.

The utils package contains a set of utility classes and functions that are
useful to the pipeline framework and to tasks manipulating pipeline framework
objects, Python data types, and CASA data types.

The utils package is intended to be free of any task-specific logic. Code that
assumes knowledge or logic beyond that of the task-independent framework should
be housed in the h.common package (or hif.common, hifv.common, hsd.common, etc.
as appropriate).

Modules:
    utils: Core utility functions (imported first to prevent circular imports)
    caltable_tools: Caltable utilities
    casa_data: Utilities for handling CASA data structures
    conversion: Data conversion utilities
    diagnostics: Diagnostic and debugging tools
    framework: Pipeline framework utilities
    imaging: Image processing utilities
    math: Mathematical functions and algorithms
    positioncorrection: Position correction utilities
    parallactic_range: Parallactic range calculation utilties
    ppr: Pipeline processing request utilities
    sorting: Sorting algorithms and utilities
    weblog: Web logging utilities
"""

from importlib import import_module

# generic utility functions first to prevent potential circular imports
from .utils import *

from .caltable_tools import *
from .casa_data import *
from .casa_types import *
from .conversion import *
from .diagnostics import *
from .framework import *
from .imaging import *
from .math import *
from .parallactic_range import *
from .positioncorrection import *
from .ppr import *
from .sorting import *
from .weblog import *
from .conf import *

# IMPORTANT! If you import from a new submodule, please add it to the list below
_all_modules = [
    'caltable_tools',
    'casa_data',
    'casa_types',
    'conversion',
    'diagnostics',
    'framework',
    'imaging',
    'ppr',
    'sorting',
    'utils',
    'weblog',
    'math',
    'parallactic_range',
    'positioncorrection',
]


def _ensure_no_multiple_definitions(module_names):
    """
    Raise an ImportError if references are exported with the same name.

    The aim of this function is to prevent functions with the same name being
    imported into the same namespace. For example, import
    module_a.my_function and module_b.my_function would raise an error.

    This function depends on __all__ being defined correctly in the package
    modules.

    :param module_names: names of submodules to check
    """
    package_modules = [import_module('.{}'.format(m), package=__name__) for m in module_names]
    names_and_declarations = [(m, set(m.__all__)) for m in package_modules]

    all_declarations = set()
    for module_name, declaration in names_and_declarations:
        if declaration.isdisjoint(all_declarations):
            all_declarations.update(declaration)
        else:
            raise ImportError('Utility module {} contains duplicate definitions: {}'
                              ''.format(module_name.__name__,
                                        ','.join(d for d in declaration.intersection(all_declarations))))


_ensure_no_multiple_definitions(_all_modules)
