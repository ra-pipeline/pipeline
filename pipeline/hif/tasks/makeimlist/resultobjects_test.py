from __future__ import annotations

import pytest

from .resultobjects import MakeImListResult


@pytest.mark.parametrize(
    'field_val,expected_field_str',
    [
        ('TARGET_01', 'TARGET_01'),
        (['0,1,2', '3,4'], "['0,1,2', '3,4']"),
        (None, 'None'),
    ],
)
def test_make_imlist_result_repr_handles_non_string_fields(
    field_val: str | list[str] | None,
    expected_field_str: str,
) -> None:
    """Verify MakeImListResult.__repr__ formats string, list, and None field values without error."""
    result = MakeImListResult()
    target = {
        'field': field_val,
        'intent': 'TARGET',
        'spw': '2,3,4',
        'phasecenter': 'J2000 12h00m00.0 +00d00m00.0',
        'cell': ['0.6arcsec'],
        'imsize': [1024, 1024],
        'imagename': '/tmp/example.image',
        'specmode': 'cont',
    }
    result.add_target(target)

    rendered = repr(result)
    lines = rendered.splitlines()

    assert lines[0] == 'MakeImList:'
    assert expected_field_str in lines[2]
    assert 'example.image' in lines[2]
    assert len(lines[1]) == len(lines[2])


def test_make_imlist_result_repr_empty_and_optional_columns() -> None:
    """Verify MakeImListResult.__repr__ handles empty targets and mixed optional keys."""
    empty_result = MakeImListResult()
    assert repr(empty_result) == 'MakeImList:\n is empty'

    result = MakeImListResult()
    result.add_target({
        'field': ['0,1'],
        'intent': 'TARGET',
        'spw': '2',
        'phasecenter': 'J2000 12h00m00.0 +00d00m00.0',
        'cell': ['0.6arcsec'],
        'imsize': [512, 512],
        'imagename': '/tmp/one.image',
        'specmode': 'cont',
        'uvrange': '<12km',
    })
    result.add_target({
        'field': 'TARGET_02',
        'intent': None,
        'spw': '3',
        'phasecenter': None,
        'cell': None,
        'imsize': None,
        'imagename': None,
    })

    lines = repr(result).splitlines()
    assert len(lines) == 4
    assert 'specmode' in lines[1]
    assert 'uvrange' in lines[1]
    assert 'start' not in lines[1]
    assert len(lines[1]) == len(lines[2]) == len(lines[3])
