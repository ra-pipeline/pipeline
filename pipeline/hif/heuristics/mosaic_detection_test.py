"""Tests for VLA mosaic detection clustering heuristics."""

import numpy as np
import pytest

from pipeline.hif.heuristics.mosaic_detection import MosaicDetectionHeuristics


@pytest.fixture
def heuristics() -> MosaicDetectionHeuristics:
    """Fixture providing a MosaicDetectionHeuristics instance."""
    return MosaicDetectionHeuristics()


def test_mosaic_clustering_low_dec(heuristics: MosaicDetectionHeuristics) -> None:
    """Verify clustering groups overlapping pointings correctly at low declination."""
    # Two fields separated by 0.5 degrees in RA, within HPBW of 1.0 degree
    ra = np.array([10.0, 10.5])
    dec = np.array([0.0, 0.0])
    names = np.array(['field1', 'field2'])
    hpbw = 3600.0  # 1 degree in arcsec

    mosaics, single_fields = heuristics.create_mosaic_groups(ra, dec, names, hpbw, overlap_tol=1.0)

    assert len(mosaics) == 1
    assert set(mosaics[0]) == {'field1', 'field2'}
    assert len(single_fields) == 0


def test_mosaic_clustering_high_dec(heuristics: MosaicDetectionHeuristics) -> None:
    """Verify clustering correctly scales RA by cos(Dec) for high declination fields.

    At Dec = 60°, cos(60°) = 0.5. Two fields separated by 1.5° in RA have
    a physical separation of 1.5 * 0.5 = 0.75° on the sky. With HPBW of 1.0°,
    they should be grouped. Without RA scaling, Euclidean distance would be
    1.5° > HPBW, resulting in no grouping.
    """
    ra = np.array([10.0, 11.5])
    dec = np.array([60.0, 60.0])
    names = np.array(['field1', 'field2'])
    hpbw = 3600.0  # 1 degree in arcsec

    mosaics, single_fields = heuristics.create_mosaic_groups(ra, dec, names, hpbw, overlap_tol=1.0)

    assert len(mosaics) == 1
    assert set(mosaics[0]) == {'field1', 'field2'}
    assert len(single_fields) == 0


def test_mosaic_clustering_independent_fields(heuristics: MosaicDetectionHeuristics) -> None:
    """Verify non-overlapping pointings are identified as single fields."""
    # Two fields separated by 2.0 degrees with HPBW of 1.0 degree
    ra = np.array([10.0, 12.0])
    dec = np.array([0.0, 0.0])
    names = np.array(['field1', 'field2'])
    hpbw = 3600.0

    mosaics, single_fields = heuristics.create_mosaic_groups(ra, dec, names, hpbw, overlap_tol=1.0)

    assert len(mosaics) == 0
    assert len(single_fields) == 2
    assert set(single_fields) == {'field1', 'field2'}


def test_empty_input(heuristics: MosaicDetectionHeuristics) -> None:
    """Verify empty input arrays return empty results."""
    ra = np.array([])
    dec = np.array([])
    names = np.array([])
    hpbw = 3600.0

    mosaics, single_fields = heuristics.create_mosaic_groups(ra, dec, names, hpbw, overlap_tol=1.0)

    assert len(mosaics) == 0
    assert len(single_fields) == 0


def test_single_field(heuristics: MosaicDetectionHeuristics) -> None:
    """Verify single field is correctly identified as isolated."""
    ra = np.array([10.0])
    dec = np.array([0.0])
    names = np.array(['field1'])
    hpbw = 3600.0

    mosaics, single_fields = heuristics.create_mosaic_groups(ra, dec, names, hpbw, overlap_tol=1.0)

    assert len(mosaics) == 0
    assert len(single_fields) == 1
    assert single_fields[0] == 'field1'


def test_transitive_clustering(heuristics: MosaicDetectionHeuristics) -> None:
    """Verify transitive closure: A overlaps B, B overlaps C, so A-B-C form one mosaic.

    Even if A and C don't directly overlap, they should be in the same mosaic
    if connected through B.
    """
    # Three fields in a line, each 0.6 degrees apart (within 1.0 degree HPBW)
    ra = np.array([10.0, 10.6, 11.2])
    dec = np.array([0.0, 0.0, 0.0])
    names = np.array(['field_A', 'field_B', 'field_C'])
    hpbw = 3600.0  # 1 degree

    mosaics, single_fields = heuristics.create_mosaic_groups(ra, dec, names, hpbw, overlap_tol=1.0)

    assert len(mosaics) == 1
    assert set(mosaics[0]) == {'field_A', 'field_B', 'field_C'}
    assert len(single_fields) == 0


def test_multiple_mosaics(heuristics: MosaicDetectionHeuristics) -> None:
    """Verify detection of multiple independent mosaic groups."""
    # Two separate mosaic groups plus one isolated field
    # Mosaic 1: field1, field2 (close together)
    # Mosaic 2: field4, field5 (close together, far from mosaic 1)
    # Single: field3 (isolated)
    ra = np.array([10.0, 10.5, 20.0, 30.0, 30.5])
    dec = np.array([0.0, 0.0, 0.0, 0.0, 0.0])
    names = np.array(['field1', 'field2', 'field3', 'field4', 'field5'])
    hpbw = 3600.0  # 1 degree

    mosaics, single_fields = heuristics.create_mosaic_groups(ra, dec, names, hpbw, overlap_tol=1.0)

    assert len(mosaics) == 2
    assert len(single_fields) == 1

    # Check that we have the right groupings (order doesn't matter)
    mosaic_sets = [set(m) for m in mosaics]
    assert {'field1', 'field2'} in mosaic_sets
    assert {'field4', 'field5'} in mosaic_sets
    assert single_fields[0] == 'field3'


def test_overlap_tolerance(heuristics: MosaicDetectionHeuristics) -> None:
    """Verify overlap_tol parameter affects clustering threshold."""
    # Two fields separated by 1.8 degrees
    ra = np.array([10.0, 11.8])
    dec = np.array([0.0, 0.0])
    names = np.array(['field1', 'field2'])
    hpbw = 3600.0  # 1 degree

    # With overlap_tol=1.0, they should NOT group (separation > 1.0 degree)
    mosaics, single_fields = heuristics.create_mosaic_groups(ra, dec, names, hpbw, overlap_tol=1.0)
    assert len(mosaics) == 0
    assert len(single_fields) == 2

    # With overlap_tol=2.0, they SHOULD group (separation < 2.0 degrees)
    mosaics, single_fields = heuristics.create_mosaic_groups(ra, dec, names, hpbw, overlap_tol=2.0)
    assert len(mosaics) == 1
    assert set(mosaics[0]) == {'field1', 'field2'}
    assert len(single_fields) == 0


def test_merge_pairs_basic(heuristics: MosaicDetectionHeuristics) -> None:
    """Test merge_pairs with simple connected pairs."""
    pairs = [(1, 2), (2, 3)]

    groups = heuristics.merge_pairs(pairs)

    assert len(groups) == 1
    assert set(groups[0]) == {1, 2, 3}


def test_merge_pairs_multiple_groups(heuristics: MosaicDetectionHeuristics) -> None:
    """Test merge_pairs with multiple disconnected groups."""
    pairs = [(1, 2), (2, 3), (4, 5), (6, 7), (5, 6)]

    groups = heuristics.merge_pairs(pairs)

    assert len(groups) == 2
    group_sets = [set(g) for g in groups]
    assert {1, 2, 3} in group_sets
    assert {4, 5, 6, 7} in group_sets


def test_merge_pairs_empty(heuristics: MosaicDetectionHeuristics) -> None:
    """Test merge_pairs with empty input."""
    pairs: list[tuple[int, int]] = []

    groups = heuristics.merge_pairs(pairs)

    assert len(groups) == 0


def test_normalize_dec(heuristics: MosaicDetectionHeuristics) -> None:
    """Test declination string normalization."""
    # Should replace first two dots with colons
    assert heuristics.normalize_dec('12.34.56.78') == '12:34:56.78'

    # Should handle normal colon-separated format
    assert heuristics.normalize_dec('12:34:56.78') == '12:34:56.78'

    # Should handle cases with fewer separators
    assert heuristics.normalize_dec('12.34') == '12.34'
    assert heuristics.normalize_dec('12') == '12'
