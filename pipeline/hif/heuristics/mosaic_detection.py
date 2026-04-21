import numpy as np

import astropy.units as u
from astropy.coordinates import SkyCoord
import scipy.cluster.hierarchy as hc


class MosaicDetectionHeuristics:
    """
    Handles mosaic detection and mosaic-aware field grouping
    for imaging pipelines.

    This class abstracts spatial clustering logic used to
    detect overlapping pointings and form mosaic groups.
    """

    def check_targets_for_mosaic(self, context, vislist, fieldlist, freq, overlap_tol=1.0):
        mosaic_groups = {}
        single_fields = {}

        # For VLA, hpbw (in arcmin) = 42.0 / observing frequency in Hz
        hpbw = 42.0e9 / freq * 60.0

        for vis in vislist:
            ms = context.observing_run.get_ms(vis)
            fields = ms.fields
            ra = []
            dec = []
            fieldnames = []

            for field in fields:
                if field.name not in fieldlist:
                    continue
                ra_str = field.ra
                dec_str = field.dec
                if field.dec.count(".") >= 2:
                    # Convert from "hh:mm:ss.sss" to "hh:mm:ss.sss"
                    dec_str = field.dec.replace(".", ":", 2)

                coord = SkyCoord(ra_str, dec_str, unit=(u.hourangle, u.deg))
                fieldnames.append(field.name)
                ra.append(coord.ra.deg)
                dec.append(coord.dec.deg)
            if len(fieldnames) > 1:
                mosaic_groups[vis], single_fields[vis] = self.create_mosaic_groups(np.array(ra),
                                                                                   np.array(dec),
                                                                                   np.array(fieldnames),
                                                                                   hpbw,
                                                                                   overlap_tol)
            else:
                mosaic_groups[vis] = []
                single_fields[vis] = fieldnames

        return mosaic_groups, single_fields

    def create_mosaic_groups(self, ra_arr, dec_arr, names, hpbw, overlap_tol=1.0):

        pointings = np.vstack((ra_arr, dec_arr)).T
        Z = hc.linkage(pointings, method='single', optimal_ordering=True)
        dist_threshold = hpbw * overlap_tol / 3600.0
        clusters = hc.fcluster(Z, t=dist_threshold, criterion='distance')
        unique_groups = np.unique(clusters)
        single_fields = []
        mosaics = []

        for group in unique_groups:
            members = names[clusters == group]
            if len(members) > 1:
                mosaics.append(members.tolist())
            else:
                single_fields.append(members[0])

        return mosaics, single_fields
