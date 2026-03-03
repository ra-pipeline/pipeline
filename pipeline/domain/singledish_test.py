"""Unit tests for singledish module."""

import unittest
from types import SimpleNamespace

from pipeline.domain.singledish import MSReductionGroupDesc, MSReductionGroupMember


class DummyMS:
    """Mock MeasurementSet for testing."""

    def __init__(self, name: str, basename: str) -> None:
        self.name = name
        self.basename = basename
        self.antennas = [
            SimpleNamespace(id=0, name='DV01'),
            SimpleNamespace(id=1, name='DV02'),
        ]
        self.spectral_windows = [
            SimpleNamespace(id=0, name='SPW_0'),
            SimpleNamespace(id=1, name='SPW_1'),
        ]
        self.fields = [
            SimpleNamespace(id=0, name='Field0'),
            SimpleNamespace(id=1, name='Field1'),
        ]


class DummyField:
    """Mock Field for testing."""

    def __init__(self, name: str) -> None:
        self.name = name


class TestMSReductionGroupMember(unittest.TestCase):
    """Test MSReductionGroupMember class."""

    def setUp(self) -> None:
        self.ms = DummyMS('test.ms', 'test.ms')
        self.member = MSReductionGroupMember(
            ms=self.ms, antenna_id=0, spw_id=0, field_id=0
        )

    def test_initialization(self) -> None:
        """Test basic initialization."""
        self.assertEqual(self.member.antenna_id, 0)
        self.assertEqual(self.member.spw_id, 0)
        self.assertEqual(self.member.field_id, 0)
        self.assertEqual(self.member.iteration, 0)
        self.assertEqual(self.member.linelist, [])
        self.assertEqual(self.member.channelmap_range, [])

    def test_default_field_id(self) -> None:
        """Test default field_id becomes -1."""
        member = MSReductionGroupMember(
            ms=self.ms, antenna_id=0, spw_id=0
        )
        self.assertEqual(member.field_id, -1)

    def test_npol_property(self) -> None:
        """Test npol property always returns 1."""
        self.assertEqual(self.member.npol, 1)

    def test_spw_property(self) -> None:
        """Test spw property returns correct spectral window."""
        spw = self.member.spw
        self.assertEqual(spw.id, 0)
        self.assertEqual(spw.name, 'SPW_0')

    def test_antenna_property(self) -> None:
        """Test antenna property returns correct antenna."""
        antenna = self.member.antenna
        self.assertEqual(antenna.id, 0)
        self.assertEqual(antenna.name, 'DV01')

    def test_antenna_name_property(self) -> None:
        """Test antenna_name property."""
        self.assertEqual(self.member.antenna_name, 'DV01')

    def test_field_property(self) -> None:
        """Test field property returns correct field."""
        field = self.member.field
        self.assertEqual(field.id, 0)
        self.assertEqual(field.name, 'Field0')

    def test_field_name_property(self) -> None:
        """Test field_name property."""
        self.assertEqual(self.member.field_name, 'Field0')

    def test_iter_countup(self) -> None:
        """Test iteration counter increment."""
        self.assertEqual(self.member.iteration, 0)
        self.member.iter_countup()
        self.assertEqual(self.member.iteration, 1)
        self.member.iter_countup()
        self.assertEqual(self.member.iteration, 2)

    def test_iter_reset(self) -> None:
        """Test iteration counter reset."""
        self.member.iter_countup()
        self.member.iter_countup()
        self.assertEqual(self.member.iteration, 2)
        self.member.iter_reset()
        self.assertEqual(self.member.iteration, 0)

    def test_add_linelist_without_channelmap(self) -> None:
        """Test add_linelist without explicit channelmap_range."""
        linelist = ['line1', 'line2']
        self.member.add_linelist(linelist)
        self.assertEqual(self.member.linelist, linelist)
        self.assertEqual(self.member.channelmap_range, linelist)

    def test_add_linelist_with_channelmap(self) -> None:
        """Test add_linelist with explicit channelmap_range."""
        linelist = ['line1', 'line2']
        channelmap = [0, 1, 2]
        self.member.add_linelist(linelist, channelmap_range=channelmap)
        self.assertEqual(self.member.linelist, linelist)
        self.assertEqual(self.member.channelmap_range, channelmap)

    def test_repr(self) -> None:
        """Test string representation."""
        repr_str = repr(self.member)
        self.assertIn('MSReductionGroupMember', repr_str)
        self.assertIn('test.ms', repr_str)
        self.assertIn('antenna=0', repr_str)
        self.assertIn('spw=0', repr_str)

    def test_equality(self) -> None:
        """Test equality comparison."""
        member2 = MSReductionGroupMember(
            ms=self.ms, antenna_id=0, spw_id=0, field_id=0
        )
        self.assertEqual(self.member, member2)

    def test_inequality_different_antenna(self) -> None:
        """Test inequality with different antenna."""
        member2 = MSReductionGroupMember(
            ms=self.ms, antenna_id=1, spw_id=0, field_id=0
        )
        self.assertNotEqual(self.member, member2)

    def test_inequality_different_ms(self) -> None:
        """Test inequality with different MS."""
        ms2 = DummyMS('other.ms', 'other.ms')
        member2 = MSReductionGroupMember(
            ms=ms2, antenna_id=0, spw_id=0, field_id=0
        )
        self.assertNotEqual(self.member, member2)

    def test_hash(self) -> None:
        """Test hash function for use in sets/dicts."""
        member2 = MSReductionGroupMember(
            ms=self.ms, antenna_id=0, spw_id=0, field_id=0
        )
        self.assertEqual(hash(self.member), hash(member2))


class TestMSReductionGroupDesc(unittest.TestCase):
    """Test MSReductionGroupDesc class."""

    def setUp(self) -> None:
        self.ms = DummyMS('test.ms', 'test.ms')
        self.field = DummyField('TestField')
        self.group_desc = MSReductionGroupDesc(
            spw_name='spw_0',
            min_frequency=1e9,
            max_frequency=2e9,
            nchan=64,
            field=self.field,
        )

    def test_initialization(self) -> None:
        """Test basic initialization."""
        self.assertEqual(self.group_desc.spw_name, 'spw_0')
        self.assertEqual(self.group_desc.min_frequency, 1e9)
        self.assertEqual(self.group_desc.max_frequency, 2e9)
        self.assertEqual(self.group_desc.nchan, 64)
        self.assertEqual(self.group_desc.field, self.field)
        self.assertEqual(self.group_desc.members, [])

    def test_frequency_range_property(self) -> None:
        """Test frequency_range property."""
        freq_range = self.group_desc.frequency_range
        self.assertEqual(freq_range, [1e9, 2e9])

    def test_field_name_property(self) -> None:
        """Test field_name property with quoted field."""
        quoted_field = DummyField('"TestField"')
        group = MSReductionGroupDesc(
            field=quoted_field,
            min_frequency=1e9,
            max_frequency=2e9,
            nchan=64,
        )
        self.assertEqual(group.field_name, 'TestField')

    def test_field_name_property_none(self) -> None:
        """Test field_name property when field is None."""
        group = MSReductionGroupDesc(
            min_frequency=1e9,
            max_frequency=2e9,
            nchan=64,
        )
        self.assertIsNone(group.field_name)

    def test_add_member(self) -> None:
        """Test add_member method."""
        self.assertEqual(len(self.group_desc), 0)
        self.group_desc.add_member(self.ms, antenna_id=0, spw_id=0, field_id=0)
        self.assertEqual(len(self.group_desc), 1)
        member = self.group_desc.members[0]
        self.assertEqual(member.antenna_id, 0)

    def test_add_duplicate_member_not_added(self) -> None:
        """Test that duplicate members are not added."""
        self.group_desc.add_member(self.ms, antenna_id=0, spw_id=0, field_id=0)
        self.group_desc.add_member(self.ms, antenna_id=0, spw_id=0, field_id=0)
        self.assertEqual(len(self.group_desc), 1)

    def test_get_iteration(self) -> None:
        """Test get_iteration method."""
        self.group_desc.add_member(self.ms, antenna_id=0, spw_id=0, field_id=0)
        iteration = self.group_desc.get_iteration(self.ms, antenna_id=0, spw_id=0, field_id=0)
        self.assertEqual(iteration, 0)

    def test_iter_countup(self) -> None:
        """Test iter_countup method."""
        self.group_desc.add_member(self.ms, antenna_id=0, spw_id=0, field_id=0)
        self.group_desc.iter_countup(self.ms, antenna_id=0, spw_id=0, field_id=0)
        iteration = self.group_desc.get_iteration(self.ms, antenna_id=0, spw_id=0, field_id=0)
        self.assertEqual(iteration, 1)

    def test_add_linelist(self) -> None:
        """Test add_linelist method."""
        self.group_desc.add_member(self.ms, antenna_id=0, spw_id=0, field_id=0)
        linelist = ['line1', 'line2']
        self.group_desc.add_linelist(
            linelist, self.ms, antenna_id=0, spw_id=0, field_id=0
        )
        member = self.group_desc.members[0]
        self.assertEqual(member.linelist, linelist)

    def test_search_member_found(self) -> None:
        """Test _search_member method when member exists."""
        self.group_desc.add_member(self.ms, antenna_id=0, spw_id=0, field_id=0)
        index = self.group_desc._search_member(self.ms, antenna_id=0, spw_id=0, field_id=0)
        self.assertEqual(index, 0)

    def test_search_member_not_found(self) -> None:
        """Test _search_member method when member does not exist."""
        with self.assertRaises(ValueError):
            self.group_desc._search_member(self.ms, antenna_id=1, spw_id=1, field_id=1)

    def test_equality_by_frequency(self) -> None:
        """Test equality based on frequency range and field."""
        group2 = MSReductionGroupDesc(
            min_frequency=1e9,
            max_frequency=2e9,
            nchan=64,
            field=self.field,
        )
        self.assertEqual(self.group_desc, group2)

    def test_inequality_different_frequency(self) -> None:
        """Test inequality with different frequency."""
        group2 = MSReductionGroupDesc(
            min_frequency=2e9,
            max_frequency=3e9,
            nchan=64,
            field=self.field,
        )
        self.assertNotEqual(self.group_desc, group2)

    def test_repr_without_spw_name(self) -> None:
        """Test string representation without spw_name."""
        repr_str = repr(self.group_desc)
        self.assertIn('frequency_range', repr_str)
        self.assertIn('nchan=64', repr_str)

    def test_list_operations(self) -> None:
        """Test list-like operations."""
        member = MSReductionGroupMember(
            ms=self.ms, antenna_id=0, spw_id=0, field_id=0
        )
        self.group_desc.append(member)
        self.assertEqual(len(self.group_desc), 1)
        self.assertEqual(self.group_desc[0], member)
        self.assertIn(member, self.group_desc)

    def test_list_iteration(self) -> None:
        """Test iteration over members."""
        member1 = MSReductionGroupMember(
            ms=self.ms, antenna_id=0, spw_id=0, field_id=0
        )
        member2 = MSReductionGroupMember(
            ms=self.ms, antenna_id=1, spw_id=1, field_id=1
        )
        self.group_desc.append(member1)
        self.group_desc.append(member2)
        members = list(self.group_desc)
        self.assertEqual(len(members), 2)
        self.assertEqual(members[0], member1)
        self.assertEqual(members[1], member2)

    def test_merge_groups(self) -> None:
        """Test merge operation between two groups."""
        group2 = MSReductionGroupDesc(
            spw_name='spw_0',
            min_frequency=1e9,
            max_frequency=2e9,
            nchan=64,
            field=self.field,
        )
        member = MSReductionGroupMember(
            ms=self.ms, antenna_id=0, spw_id=0, field_id=0
        )
        group2.append(member)
        self.assertEqual(len(self.group_desc), 0)
        self.group_desc.merge(group2)
        self.assertEqual(len(self.group_desc), 1)


if __name__ == '__main__':
    unittest.main()
