def uvrange(setjy_results, field_id: int, spw_id: int = 2) -> str:
    """Construct UV range constraint string from flux calibration results.

    Extracts uvmin and uvmax from the flux calibration domain object and
    formats them as a UV range constraint string in lambda units.

    Args:
        setjy_results: Flux domain object read from import stage.
        field_id: Field ID as integer.
        spw_id: Spectral window ID (default: 2 for VLASS). Currently unused;
            always uses first measurement (spw_index=0).

    Returns:
        UV range constraint string in lambda units. Examples: '500~5000lambda',
        '>500lambda', or empty string if both uvmin and uvmax are zero.
    """
    try:
        spw_index = 0
        uvmin_val = float(setjy_results[0].measurements[field_id][spw_index].uvmin)
        uvmax_val = float(setjy_results[0].measurements[field_id][spw_index].uvmax)
    except (IndexError, AttributeError, TypeError, ValueError):
        uvmin_val = 0.0
        uvmax_val = 0.0

    if uvmin_val == 0.0 and uvmax_val == 0.0:
        return ''

    if uvmin_val != 0.0 and uvmax_val == 0.0:
        return f'>{uvmin_val}lambda'

    if uvmin_val != 0.0 and uvmax_val != 0.0:
        return f'{uvmin_val}~{uvmax_val}lambda'

    return ''
