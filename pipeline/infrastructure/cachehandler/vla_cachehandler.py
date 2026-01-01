from . import CacheHandler
from functools import lru_cache

import pipeline.hif.heuristics.findrefant as findrefant


class VLA_CacheHandler(CacheHandler):
    """
    Derived cache handler for VLA-specific computations.
    Implements cached properties for expensive methods.
    """
    def __init__(self):
        pass

    @staticmethod
    @lru_cache(maxsize=128)
    def compute_refant_output(vis, field, spw, intent, geometry, flagging, refantignore=None):
        """Compute and cache the reference antenna output."""

        refantobj = findrefant.RefAntHeuristics(
            vis=vis,
            field=field,
            geometry=geometry,
            flagging=flagging,
            intent=intent,
            spw=spw,
            refantignore=refantignore
        )
        return refantobj.calculate()
