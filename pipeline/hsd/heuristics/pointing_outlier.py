from __future__ import annotations

import collections
from typing import TYPE_CHECKING

import numpy as np

import pipeline.infrastructure.api as api
from pipeline.infrastructure.utils import coordinate_utils

if TYPE_CHECKING:
    from numpy.typing import NDArray

PointingOutlierHeuristicsResult = collections.namedtuple(
    "PointingOutlierHeuristicsResult",
    ["cx", "cy", "med_dist", "factor", "mask", "dist"]
)


class PointingOutlierHeuristics(api.Heuristic):
    # Variables below are the threshold factors for the heuristics.
    # Which factor to use depends on the situation of the scan,
    # especially, whether the last scan can be interrupted or not,
    # and the number of raster rows per map.

    # (1) Interrupted scan is not allowed by the system.
    #     The factor is 2.0 in this case.
    FACTOR_NO_INTERRUPT = 2

    # (2) Raster scan can be interrupted in the middle, and
    #     number of raster rows per map is always greater than 2.
    #     The factor is sqrt(13 * pi / 8) in this case.
    FACTOR_INTERRUPT = 2.26

    # (3) Raster scan can be interrupted in the middle, and
    #     number of raster rows per map can be 2.
    #     The factor is 4 * sqrt(5) / 3 in this case.
    FACTOR_INTERRUPT_LESS_RASTER_ROWS = 2.982

    def calculate(self,
                  dir_frame: str,
                  x: NDArray,
                  y: NDArray,
                  iterate: bool = False) -> PointingOutlierHeuristicsResult:
        """Perform pointing outlier heuristics.

        Algorithm is as follows:

            1. take median of x and y coordinates -> med_x, med_y
            2. compute distance from (med_x, med_y) for each data -> dist
            3. take median of distance array, dist -> med_dist
            4. mask data if dist > threshold * med_dist
               (mask is False if dist > threshold * med_dist)
               please see below for threshold factor
            5. if iterate is True, do the following:
                5-1. re-compute med_x and med_y using a subset of
                     the data where mask is True
                5-2. re-compute distance from updated (med_x, med_y)
                     to update dist
                5-3. take median of updated dist
                5-4. update mask using updated med_dist

        Regarding the step 4, three threshold factors are available.
        They are defined as class attributes. Which factor should use
        depends on the observing strategy. Current observing strategy
        in ALMA corresponds to the first case, so the current
        implementation uses FACTOR_INTERRUPT.

            - If interrupted scan can happen, and there is a guarantee
              that number of raster rows > 2, then threshold will be
              FACTOR_INTERRUPT.
            - if interrupted scan can happen, and number of raster
              rows can be 2, then threshold will be
              FACTOR_INTERRUPT_LESS_RASTER_ROWS.
            - if interrupted scan should not happen, threshold will be
              FACTOR_NO_INTERRUPT.

        Args:
            dir_frame: direction reference frame
            x: List of RA values in degrees. For ephemeris source,
               RA values must be shifted in advance (use SHIFT_RA column
               in datatable).
            y: List of DEC values in degrees. For ephemeris source,
               DEC values must be shifted in advance (use SHIFT_DEC column
               in datatable).
            iterate: whether or not perform iteration. Default is False.

        Returns:
            PointingOutlierHeuristicsResult object, which includes:

                - cx: x coordinate of nominal center position
                - cy: y coordinate of nominal center position
                - med_dist: median distance from the nominal center
                - threshold: factor to derive the threshold from
                    median distance
                - mask: validity mask (False means flagged by this heuristic)
                - dist: computed distance array with respect to
                    the nominal center
        """
        med_x = np.median(x)
        med_y = np.median(y)
        distance = coordinate_utils.angular_distances(dir_frame, x, y, med_x, med_y)
        median_distance = np.median(distance)
        # raster scan can be interrupted, and number of raster rows > 2
        threshold = self.FACTOR_INTERRUPT
        if iterate:
            unflagged = distance <= threshold * median_distance
            med_x = np.median(x[unflagged])
            med_y = np.median(y[unflagged])
            distance = np.sqrt(np.square(x - med_x) + np.square(y - med_y))
            median_distance = np.median(distance)
        mask = distance <= threshold * median_distance

        return PointingOutlierHeuristicsResult(
            med_x,
            med_y,
            median_distance,
            threshold,
            mask,
            distance
        )
