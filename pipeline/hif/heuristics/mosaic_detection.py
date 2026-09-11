from collections import defaultdict

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components


class MosaicDetectionHeuristics:
    """Handles mosaic detection and mosaic-aware field grouping for imaging pipelines.

    This class abstracts spatial clustering logic used to detect overlapping
    pointings and form mosaic groups.
    """

    @staticmethod
    def normalize_dec(dec_str: str) -> str:
        """Normalize declination string.

        Replaces first two dots with colons if needed for coordinate parsing.

        Args:
            dec_str: Declination string with dot separators.

        Returns:
            Normalized declination string with colon separators.
        """
        parts = dec_str.split('.')
        if len(parts) > 2:
            return f'{parts[0]}:{parts[1]}:{".".join(parts[2:])}'
        return dec_str

    @staticmethod
    def _parse_field_coords(fields, fieldlist: list[str]) -> tuple[list[str], list['SkyCoord']]:
        """Parse field coordinates from measurement set fields.

        Args:
            fields: Fields from measurement set.
            fieldlist: List of field names to include.

        Returns:
            Tuple of (field names, sky coordinates) for fields in fieldlist.
        """
        fieldnames, coordlist = [], []
        for field in fields:
            if field.name not in fieldlist:
                continue
            dec_str = MosaicDetectionHeuristics.normalize_dec(field.dec)
            coord = SkyCoord(field.ra, dec_str, unit=(u.hourangle, u.deg))
            fieldnames.append(field.name)
            coordlist.append(coord)
        return fieldnames, coordlist

    @staticmethod
    def create_mosaic_groups(
        ra: np.ndarray, dec: np.ndarray, names: np.ndarray, hpbw: float, overlap_tol: float = 1.0
    ) -> tuple[list[list[str]], list[str]]:
        """Create mosaic groups from coordinate arrays.

        Simplified interface for testing that directly accepts coordinate arrays.

        Args:
            ra: Right ascension values in degrees.
            dec: Declination values in degrees.
            names: Field names corresponding to each coordinate.
            hpbw: Half-power beam width in arcseconds.
            overlap_tol: Overlap tolerance multiplier for clustering.

        Returns:
            Tuple of (mosaics, single_fields) where mosaics is a list of
            field name groups, and single_fields is a list of isolated field names.
        """
        if len(ra) == 0:
            return [], []

        # Create SkyCoord objects from ra/dec arrays
        coords = SkyCoord(ra=ra * u.deg, dec=dec * u.deg, frame='icrs')

        # Find overlapping pointings
        idx_a, idx_b, _, _ = coords.search_around_sky(coords, hpbw * overlap_tol * u.arcsec)

        # Cluster into groups
        groups = MosaicDetectionHeuristics.merge_pairs(list(zip(idx_a, idx_b)))

        # Separate into mosaics (>1 field) and single fields
        mosaics = []
        single_fields = []

        for group in groups:
            if len(group) > 1:
                mosaics.append(names[list(group)].tolist())
            else:
                single_fields.append(names[group[0]])

        return mosaics, single_fields

    @staticmethod
    def check_targets_for_mosaic(
        observing_run,
        vislist: list[str],
        fieldlist: list[str],
        hpbw: float,
        overlap_tol: float = 1.0,
    ) -> tuple[dict, dict]:
        """Detect mosaic and single-field groups by clustering overlapping pointings.

        Args:
            observing_run: Observing run object containing measurement sets.
            vislist: List of visibility (MS) names to process.
            fieldlist: List of field names to consider.
            hpbw: Half-power beam width in arcseconds.
            overlap_tol: Overlap tolerance multiplier for clustering.

        Returns:
            Tuple of (mosaic_groups, single_fields) where mosaic_groups maps
            MS names to lists of field name groups, and single_fields maps
            MS names to lists of isolated field names.
        """
        mosaic_groups = defaultdict(list)
        single_fields = defaultdict(list)

        for vis in vislist:
            ms = observing_run.get_ms(vis)
            fieldnames, coordlist = MosaicDetectionHeuristics._parse_field_coords(ms.fields, fieldlist)

            if len(coordlist) == 0:
                continue

            if len(coordlist) < 2:
                single_fields[vis].extend(fieldnames)
                continue

            # Convert SkyCoord list to RA/Dec arrays for create_mosaic_groups
            coords = SkyCoord(coordlist)
            ra = coords.ra.deg
            dec = coords.dec.deg
            names = np.array(fieldnames)

            # Reuse clustering logic
            mosaics, singles = MosaicDetectionHeuristics.create_mosaic_groups(ra, dec, names, hpbw, overlap_tol)

            mosaic_groups[vis].extend(mosaics)
            single_fields[vis].extend(singles)

        return mosaic_groups, single_fields

    @staticmethod
    def merge_pairs(pairs: list[tuple[int, int]]) -> list[list[int]]:
        """Merge connected pairs into groups using graph connectivity.

        Uses scipy's connected components algorithm to find transitive
        closure of pairwise connections.

        Args:
            pairs: List of pairs where each tuple (a, b) represents
                a connection between elements a and b.

        Returns:
            List of groups, where each group contains directly or
            indirectly connected elements.

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
