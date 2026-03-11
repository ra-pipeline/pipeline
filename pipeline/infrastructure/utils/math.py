import decimal
from typing import Union

import numpy as np

__all__ = ['round_half_up', 'round_up']


def round_half_up(value: Union[int, str], precision: float = 0) -> float:
    """
    Provides the "round to given precision with ties going away from zero"
    behaviour that was the default Python2 rounding behavior.

    The behaviour of the "round" built-in changed from Python 2 to Python 3.

    In Python 2, round() was rounding to the given precision, with ties going
    away from 0. For example:

    [round(a) for a in [-2.5, -1.5, -0.5, 0.5, 1.5, 2.5]] == [-3.0, -2.0, -1.0, 1.0, 2.0, 3.0]

    In Python 3, round() become "Banker's rounding", rounding to the nearest
    even integer, following the IEEE 754 standard for floating-point arithmetic.
    For example:

    >>> [round(a) for a in [-2.5, -1.5, -0.5, 0.5, 1.5, 2.5]]
    [-2, -2, 0, 0, 2, 2]

    Note: in this function and the underlying Python decimal module,
    "round half up" refers to "round half away from zero" behaviour, rather than
    rounding half up to positive infinity.

    Args:
        value: Un-rounded value
        precision: Precision of un-rounded value to consider when rounding

    Returns:
        rounded value to given precision with ties going away from 0
    """
    return float(
        decimal.Decimal(float(np.asarray(value).item()) * 10 ** precision).to_integral_value(rounding=decimal.ROUND_HALF_UP)) / 10 ** precision


def round_up(value: Union[int, str], precision: float = 0) -> float:
    """
    Round to given precision away from zero.

    Example:
    >>> [round_up(a) for a in [-1.5, -1.1, -0.5, 0.5, 1.1, 1.5]]
    [-2.0, -2.0, -1.0, 1.0, 2.0, 2.0]

    >>> [round_up(a, 1) for a in [-1.25, -1.15, 1.15, 1.25]]
    [-1.3, -1.2, 1.2, 1.3]

    Args:
        value: Un-rounded value
        precision: Precision of un-rounded value to consider when rounding

    Returns:
        rounded value to given precision away from 0
    """
    return float(
        decimal.Decimal(float(value) * 10 ** precision).to_integral_value(rounding=decimal.ROUND_UP)) / 10 ** precision

def round_down(value: Union[int, str], precision: float = 0) -> float:
    """
    Round to given precision toward zero.

    Example:
    >>> [round_down(a) for a in [-1.5, -1.1, -0.5, 0.5, 1.1, 1.5]]
    [-1.0, -1.0, -0.0, 0.0, 1.0, 1.0]

    >>> [round_down(a, 1) for a in [-1.25, -1.15, 1.15, 1.25]]
    [-1.2, -1.1, 1.1, 1.2]

    Args:
        value: Un-rounded value
        precision: Precision of un-rounded value to consider when rounding

    Returns:
        rounded value to given precision toward 0
    """
    return float(
        decimal.Decimal(float(value) * 10 ** precision).to_integral_value(rounding=decimal.ROUND_DOWN)) / 10 ** precision
