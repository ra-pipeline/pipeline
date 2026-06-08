# - functions to measure parallactic angle coverage of calibrators
# Do not evaluate type annotations at definition time.
from __future__ import annotations

from typing import TYPE_CHECKING

from pipeline import infrastructure
from pipeline.infrastructure import casa_tools, utils

if TYPE_CHECKING:
    from collections.abc import Callable

    from pipeline.domain import MeasurementSet, Field

LOG = infrastructure.logging.get_logger(__name__)

__all__ = ['ous_parallactic_range']

# Type aliases for the parallactic angle computations.
ParallacticAngle = float
SignedAngle = float
PositiveDefiniteAngle = float


def ous_parallactic_range(
        mses: list[MeasurementSet],
        field_name: str,
        intent: str
        ) -> tuple[float, float] | None:
    """
    Get the parallactic angle range across all measurement sets for field when observed with the specified intent.

    Args:
        mses: MeasurementSets to process
        field_name: Field to inspect
        intent: observing intent to consider

    Returns:
        angular range expressed as (min angle, max angle) tuple or None
    """
    angles = []
    for ms in mses:
        fields = ms.get_fields(task_arg=field_name, intent=intent)
        if not fields:
            LOG.error('No field found for for field: %s intent: %s in ms: %s; cannot determine '
                      'parallactic angle.', field_name, intent, ms.basename)
            continue
        if len(fields) > 1:
            LOG.warning('Multiple fields found for field: %s intent: %s in ms: %s; using first one for '
                        'the parallactic angle range calculation.', field_name, intent, ms.basename)
        field = fields[0]

        try:
            angles.extend(_parallactic_range_for_field(ms, field, intent))
        except ValueError as e:
            LOG.exception('Could not determine parallactic angle', exc_info=e)
            continue

    if not angles:
        return

    signed_range = _range_after_processing(angles, _to_signed)
    pd_range = _range_after_processing(angles, _to_positive_definite)

    return min((signed_range, pd_range))


def _parallactic_range_for_field(ms: MeasurementSet, f: Field, intent: str) -> tuple[float, float]:
    """
    Get the parallactic angle range for field f when observed with the specified intent.

    Args:
        ms: MeasurementSet to process
        f: Field to inspect
        intent: observing intent to consider

    Returns:
        angular range expressed as (min angle, max angle) tuple

    Raises:
        ValueError: if no scans are found in the MS for specified field and intent
    """
    # get the scans when the field was observed with the required intent
    scans = ms.get_scans(field=f.id, scan_intent=intent)
    if not scans:
        raise ValueError(f'No scans detected for field {f} with intent {intent}')

    # This uses the earliest start and latest end times of the scan domain
    # objects. In theory, times within a scan can be field and spw dependent so
    # they may not exactly match those of the field in question, but they
    # should be accurate enough for our purposes
    min_utc = min([s.start_time for s in scans], key=utils.get_epoch_as_datetime)
    max_utc = max([s.end_time for s in scans], key=utils.get_epoch_as_datetime)

    observatory = ms.antenna_array.name
    min_pa = _parallactic_angle_at_epoch(f, min_utc, observatory)
    max_pa = _parallactic_angle_at_epoch(f, max_utc, observatory)

    if min_pa > max_pa:
        min_pa, max_pa = max_pa, min_pa

    return min_pa, max_pa


def _parallactic_angle_at_epoch(f: Field, e: dict, observatory: str) -> float:
    """
    Get the instantaneous parallactic angle for field f at epoch e.

    Args:
        f: Field domain object
        e: CASA epoch

    Returns
        angular separation in degrees
    """
    me = casa_tools.measures
    qa = casa_tools.quanta

    try:
        me.doframe(me.observatory(observatory))
        me.doframe(e)

        pole_direction = me.direction('J2000', '0deg', '+90deg')
        pole_azel = me.measure(pole_direction, 'AZEL')
        field_azel = me.measure(f.mdirection, 'AZEL')

        separation = me.posangle(field_azel, pole_azel)
        sep_degs = qa.convert(separation, 'deg')

        return sep_degs['value']

    finally:
        me.done()


def _range_after_processing(fs: list[float], g: Callable[[float], float]):
    """
    Get the range of a list of floats (fs) once processed by function g.
    """
    processed = [g(f) for f in fs]
    return max(processed) - min(processed)


def _to_signed(angle: ParallacticAngle) -> SignedAngle:
    if angle > 180:
        return angle - 360
    return angle


def _to_positive_definite(angle: ParallacticAngle) -> PositiveDefiniteAngle:
    if angle < 0:
        return angle + 360
    return angle
