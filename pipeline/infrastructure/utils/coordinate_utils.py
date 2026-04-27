""" Ulititiy methods related to coordinate calculations."""
from __future__ import annotations

from typing import TYPE_CHECKING

from astropy.coordinates import SkyCoord

import pipeline.infrastructure.utils.conversion as conversion

if TYPE_CHECKING:
    from numpy import floating
    from numpy.typing import NDArray


def angular_distances(dir_frame: str,
                      ra: NDArray[floating],
                      dec: NDArray[floating],
                      ref_ra: float,
                      ref_dec: float) -> NDArray[floating]:
    """Compute angular distances from a reference position.

    Args:
        dir_frame: direction reference frame.
        ra: List of RA values in degrees.
        dec: List of DEC values in degrees.
        ref_ra: RA value of reference position in degrees.
        ref_dec: DEC value of reference position in degrees.

    Returns:
        List of distance values from the reference position in degrees.
    """
    sky_frame = conversion.refcode_to_skyframe(dir_frame)
    ref_dir = SkyCoord(ra=ref_ra, dec=ref_dec, unit='deg', frame=sky_frame)

    _dir = SkyCoord(ra=ra, dec=dec, unit='deg', frame=sky_frame)
    dist = ref_dir.separation(_dir).degree

    return dist
