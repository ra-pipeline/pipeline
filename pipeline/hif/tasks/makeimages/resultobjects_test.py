from __future__ import annotations

import pytest

from .resultobjects import MakeImagesResult


@pytest.mark.parametrize(
    'field_val,expected_field_str',
    [
        ('TARGET_01', 'TARGET_01'),
        (['0,1,2', '3,4'], "['0,1,2', '3,4']"),
        (None, 'None'),
    ],
)
def test_make_images_result_repr_handles_non_string_fields(
    field_val: str | list[str] | None,
    expected_field_str: str,
) -> None:
    """Verify MakeImagesResult.__repr__ formats string, list, and None field values without error."""
    result = MakeImagesResult()
    target = {
        'field': field_val,
        'intent': 'TARGET',
        'spw': '2,3,4',
        'phasecenter': 'J2000 12h00m00.0 +00d00m00.0',
        'cell': ['0.6arcsec'],
        'imsize': [1024, 1024],
        'imagename': '/tmp/example.image',
        'heuristics': None,
    }
    result.add_result(result=object(), target=target, outcome='success')

    rendered = repr(result)
    lines = rendered.splitlines()

    assert lines[0] == 'MakeImages:'
    assert expected_field_str in lines[2]
    assert 'example.image' in lines[2]
    assert 'success' in lines[2]
    assert len(lines[1]) == len(lines[2])


def test_make_images_result_repr_handles_none_attributes() -> None:
    """Verify MakeImagesResult.__repr__ does not raise when optional target values are None."""
    result = MakeImagesResult()
    target = {
        'field': ['0,1'],
        'intent': None,
        'spw': None,
        'phasecenter': None,
        'cell': None,
        'imsize': None,
        'imagename': None,
        'heuristics': None,
    }
    result.add_result(result=object(), target=target, outcome=None)

    rendered = repr(result)
    lines = rendered.splitlines()

    assert len(lines) == 3
    assert "['0,1']" in lines[2]
    assert len(lines[1]) == len(lines[2])


def test_make_images_result_repr_empty_targets() -> None:
    """Verify MakeImagesResult.__repr__ prints header line when targets is empty."""
    result = MakeImagesResult()
    rendered = repr(result)
    lines = rendered.splitlines()

    assert len(lines) == 2
    assert lines[0] == 'MakeImages:'
    assert 'field' in lines[1]
    assert 'outcome' in lines[1]
