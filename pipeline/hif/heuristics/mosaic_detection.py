import numpy as np

import astropy.units as u
from astropy.coordinates import SkyCoord
from collections import defaultdict
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from typing import List, Tuple, Dict


class MosaicDetectionHeuristics:
    """
    Handles mosaic detection and mosaic-aware field grouping
    for imaging pipelines.

    This class abstracts spatial clustering logic used to
    detect overlapping pointings and form mosaic groups.
    """
    def normalize_dec(self, dec_str: str) -> str:
        """Normalize dec string, replacing first two dots with colons if needed."""
        parts = dec_str.split(".")
        if len(parts) > 2:
            return f"{parts[0]}:{parts[1]}:{'.'.join(parts[2:])}"
        return dec_str

    def _parse_field_coords(self, fields, fieldlist) -> Tuple[List[str], List[SkyCoord]]:
        """Return (fieldnames, coordlist) for fields that are in fieldlist."""
        fieldnames, coordlist = [], []
        for field in fields:
            if field.name not in fieldlist:
                continue
            dec_str = self.normalize_dec(field.dec)
            coord = SkyCoord(field.ra, dec_str, unit=(u.hourangle, u.deg))
            fieldnames.append(field.name)
            coordlist.append(coord)
        return fieldnames, coordlist

    def check_targets_for_mosaic(
            self, context, vislist, fieldlist, hpbw, overlap_tol=1.0,
            ) -> Tuple[Dict, Dict]:
        """Detect mosaic and single-field groups across all measurement sets by clustering overlapping pointings."""
        mosaic_groups = defaultdict(list)
        single_fields = defaultdict(list)

        for vis in vislist:
            ms = context.observing_run.get_ms(vis)
            fieldnames, coordlist = self._parse_field_coords(ms.fields, fieldlist)
            if len(coordlist) < 2:
                single_fields[vis].extend(fieldnames)
                continue

            coords = SkyCoord(coordlist)
            idx_a, idx_b, _, _ = coords.search_around_sky(coords, hpbw * overlap_tol * u.arcsec)
            fieldnames_arr = np.array(fieldnames)
            groups = self.merge_pairs(list(zip(idx_a, idx_b)))

            for group in groups:
                if len(group) > 1:
                    mosaic_groups[vis].append(fieldnames_arr[list(group)].tolist())
                else:
                    single_fields[vis].append(fieldnames[group[0]])

        return mosaic_groups, single_fields

    def merge_pairs(self, pairs) -> List[List[int]]:
        """Merge connected pairs into groups of directly/indirectly connected elements.

        Args:
            pairs (list of tuple): A list of pairs (tuples) where each tuple (a, b)
                                represents a connection between elements `a` and `b`.

        Returns:
            list of list: A list of groups, where each group is a list of connected elements.

        Example:
            >>> merge_pairs([(1, 2), (2, 3), (4, 5), (6, 7), (5, 6)])
            [[1, 2, 3], [4, 5, 6, 7]]
        """
        if not pairs:
            return []

        # Create unique ID mapping
        unique_ids = {x for pair in pairs for x in pair}
        id_map = {id_: i for i, id_ in enumerate(unique_ids)}

        # Create adjacency matrix
        n = len(unique_ids)
        adjacency_matrix = np.zeros((n, n), dtype=bool)

        for a, b in pairs:
            adjacency_matrix[id_map[a], id_map[b]] = True
            adjacency_matrix[id_map[b], id_map[a]] = True

        # Find connected components
        graph = csr_matrix(adjacency_matrix)
        n_components, labels = connected_components(csgraph=graph, directed=False)

        # Group elements based on components
        clusters = {i: [] for i in range(n_components)}
        for id_, label in zip(unique_ids, labels):
            clusters[label].append(id_)

        return list(clusters.values())
