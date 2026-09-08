import pipeline.infrastructure as infrastructure

LOG = infrastructure.logging.get_logger(__name__)


def uvrange(setjy_results, field_id: int) -> str:
    """Construct UV range constraint string from flux calibration results.

    Extracts uvmin and uvmax from the flux calibration domain object and
    formats them as a UV range constraint string in lambda units.

    Args:
        setjy_results: Flux domain object read from import stage.
        field_id: Field ID as integer.

    Returns:
        UV range constraint string in lambda units. Examples: '500~5000lambda',
        '>500lambda', or empty string if both uvmin and uvmax are zero.
    """
    try:
        spw_index = 0
        uvmin_val = float(setjy_results[0].measurements[field_id][spw_index].uvmin)
        uvmax_val = float(setjy_results[0].measurements[field_id][spw_index].uvmax)
    except (IndexError, AttributeError, TypeError, ValueError):
        LOG.info('No UV range available for field_id=%d. Using default (empty) constraint.', field_id)
        return ''

    if uvmin_val == 0.0 and uvmax_val == 0.0:
        LOG.info('Field %d: UV range constraint: empty (both uvmin and uvmax are zero)', field_id)
        return ''

    if uvmin_val != 0.0 and uvmax_val == 0.0:
        uvrange_str = f'>{uvmin_val}lambda'
        LOG.info('Field %d: UV range constraint: %s', field_id, uvrange_str)
        return uvrange_str

    if uvmin_val != 0.0 and uvmax_val != 0.0:
        uvrange_str = f'{uvmin_val}~{uvmax_val}lambda'
        LOG.info('Field %d: UV range constraint: %s', field_id, uvrange_str)
        return uvrange_str

    LOG.info('Field %d: UV range constraint: empty (default case)', field_id)
    return ''
