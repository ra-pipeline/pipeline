"""
This module defines types of objects used in single dish.
"""

from typing import TypeAlias

import numpy as np
import numpy.typing as npt

# N-Dimension Array of float64
NpArray1D: TypeAlias = npt.NDArray[np.float64]
NpArray2D: TypeAlias = npt.NDArray[np.float64]
NpArray3D: TypeAlias = npt.NDArray[np.float64]

# Direction / Angle are dictionaries produced by CASA measures/quanta
Direction: TypeAlias = dict[str, str | float]
Angle: TypeAlias = dict[str, str | float]
