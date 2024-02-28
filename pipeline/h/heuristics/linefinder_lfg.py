#*******************************************************************************
# ALMA - Atacama Large Millimeter Array
# Copyright (c) ATC - Astronomy Technology Center - Royal Observatory Edinburgh, 2011
# (in the framework of the ALMA collaboration).
# All rights reserved.
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307  USA
#*******************************************************************************
"""Find indice of lines from spectrum data."""

import numpy as np
import pipeline.infrastructure.api as api
from typing import List, Optional

from .lfgmn.lf_g_gmngs import line_finder

class ZeroCrossLineFinder(api.Heuristic):
    """
    A heuristics class to invoke line finding on a spectrum.

    This class inherits Heuristic class.
    Methods:
        calculate: Override calculate method in the super class.
    """

    def calculate(self, spectrum: List[float], mask: List[bool]=[], *args, **kwargs) -> List[int]:
        """
        Invoke line finding algorithm and return indices of spectral line ranges.

        Line finding is based on zero-crossing of 1st/2nd derivatives of input
        spectrum with Gaussian smoothing.

        Args:
            spectrum: list of spectrum data.
            mask: mask of spectrum array. An elements of spectrum is valid when
                  the corresponding element of mask is True. If False, invalid.
                  The length of list should be equal to that of spectrum.
        Returns:
            ranges: A list of start and end indices of spectral lines. The indices of
                    lines are in the order of, e.g., [start1, end1, ..., startN, endN].
        """
        _spectrum = np.array(spectrum)
        # input mask: True is valid, False is invalid
        # mask for line_finder: True is *invalid*, False is *valid*
        if len(mask) == 0:
            mask = np.zeros(len(_spectrum), dtype=bool)
        else:
            mask = np.logical_not(np.array(mask, bool))

        try:
            ranges, _, _ = line_finder(_spectrum, mask)
        except Exception:
            np.savetxt('failed_spectrum.txt', (_spectrum, mask), delimiter=',')
            raise

        print(f'detected lines: {ranges}')

        return ranges
