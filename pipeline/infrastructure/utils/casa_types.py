"""TypedDict definitions for CASA measure records.

This module provides type definitions for CASA measures and quantities that are
returned by CASA tools (me, qa). These types help provide type hints for code
working with CASA measure dictionaries.
"""
from __future__ import annotations

from typing import TypedDict

from numpy.typing import NDArray


class QuantityDict(TypedDict):
    """Type for CASA quantity dictionary (from qa tool)."""

    unit: str
    value: NDArray


class DirectionDict(TypedDict):
    """Type for CASA direction measure dictionary (from me tool)."""

    m0: QuantityDict
    m1: QuantityDict
    refer: str
    type: str


class EpochDict(TypedDict):
    """Type for CASA epoch measure dictionary (from me tool)."""

    m0: QuantityDict
    refer: str
    type: str


class PositionDict(TypedDict):
    """Type for CASA position measure dictionary (from me tool)."""

    m0: QuantityDict
    m1: QuantityDict
    m2: QuantityDict
    refer: str
    type: str


class LongLatDict(TypedDict):
    """Type for latitude/longitude pair."""

    latitude: QuantityDict
    longitude: QuantityDict


__all__ = [
    'QuantityDict',
    'DirectionDict',
    'EpochDict',
    'PositionDict',
    'LongLatDict',
]
