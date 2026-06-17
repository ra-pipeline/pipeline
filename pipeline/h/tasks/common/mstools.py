from __future__ import annotations

import os
from typing import TYPE_CHECKING

import numpy

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.utils as utils
from pipeline.h.tasks.common.commonhelpermethods import get_corr_products
from pipeline.infrastructure import casa_tools

if TYPE_CHECKING:
    import casatools
    from pipeline.domain import MeasurementSet

LOG = infrastructure.logging.get_logger(__name__)


def read_channel_averaged_data_from_ms(ms: MeasurementSet,
                                       fieldid: str | int,
                                       spwid: str | int,
                                       intent: str,
                                       items: list[str],
                                       baseline_set: list | None = None,
                                       *,
                                       ms_handle: casatools.ms | None = None) -> dict:
    """Read the channel-averaged visibility data from a MS for the given field, spw, intent, and optionally a subset of baselines.

    Args:
        ms: MeasurementSet.
        fieldid: string or int representing the field ID.
        spwid: string or int representing the SPW ID.
        intent: intent or list of intents.
        items: List of data arrays to read, e.g., ['corrected_data', 'flag', 'antenna1', 'antenna2'].
        baseline_set: List of baselines (default: all).
        ms_handle: Optional already-open CASA ms tool (casatools.ms). When provided the MS is not
            opened/closed by this function, allowing callers to amortise the
            (potentially expensive) open cost across many calls. The caller is
            responsible for the lifetime of the handle.

    Returns:
        A dict with the data array for each element in items.
    """
    # Identify scans for given data selection.
    scans_with_data = ms.get_scans(scan_intent=intent, field=str(fieldid), spw=str(spwid))
    if not scans_with_data:
        LOG.info('No data expected for %s %s intent, field %s, spw %s. Continuing...',
                 ms.basename, intent, fieldid, spwid)
        return {}

    # Initialize data selection.
    data_selection = {'field': str(fieldid),
                      'scanintent': '*%s*' % utils.to_CASA_intent(ms, intent),
                      'spw': str(spwid)}

    # Add baseline set to data selection if provided; log selection.
    if baseline_set:
        LOG.info('Reading data for {}, intent {}, field {}, spw {}, and {} baselines ({})'.
                 format(os.path.basename(ms.name), intent, fieldid, spwid, baseline_set[0], baseline_set[1]))
        data_selection['baseline'] = baseline_set[1]
    else:
        LOG.info('Reading data for {}, intent {}, field {}, spw {}, and all baselines'.
                 format(os.path.basename(ms.name), intent, fieldid, spwid))

    # Get number of channels for this spw.
    nchans = ms.get_all_spectral_windows(str(spwid))[0].num_channels

    def _do_read(openms):
        try:
            # Clear any prior selection, then apply new data and channel selection.
            openms.reset()
            openms.msselect(data_selection)
            openms.selectchannel(1, 0, nchans, 1)

            # Extract data from MS.
            return openms.getdata(items)
        except Exception:
            LOG.warning('Unable to read data for intent %s, field %s, spw %s', intent, fieldid, spwid)
            return {}

    # If an open MS handle was supplied by the caller, reuse it to avoid the
    # overhead of opening/closing the MS file on every call (which is especially
    # costly for lazy-import MSes whose DATA column is ASDM-backed).
    if ms_handle is not None:
        data = _do_read(ms_handle)
    else:
        with casa_tools.MSReader(ms.name) as openms:
            data = _do_read(openms)

    return data


def compute_mean_flux(ms: MeasurementSet,
                      fieldid: str | int,
                      spwid: str | int,
                      intent: str,
                      *,
                      ms_handle: casatools.ms | None = None) -> tuple[float, float]:
    """Compute the mean flux and its standard deviation (averaged across available polarizations) for the given MS, field, spw and intent.

    Args:
        ms: MeasurementSet.
        fieldid: string or int representing the field ID.
        spwid: string or int representing the SPW ID.
        intent: intent or list of intents.
        ms_handle: Optional already-open CASA ms tool (casatools.ms), passed through to
            read_channel_averaged_data_from_ms (see that function for details).

    Returns:
        A tuple of (mean_flux, std_flux) -- mean flux and its standard deviation, or
        (0.0, 0.0) if data is not available.
    """
    # Read in data from the MS, for specified intent, field, and spw.
    try:
        data = read_channel_averaged_data_from_ms(
            ms, fieldid, spwid, intent, ['corrected_data', 'flag', 'antenna1', 'antenna2', 'weight'],
            ms_handle=ms_handle)
    except Exception as ex:
        LOG.warning('Cannot retrieve data for MS %s, field %s, spw %s, intent %s: %s',
                    ms.basename, fieldid, spwid, intent, ex)
        data = {}

    # Return zero if no valid data were read.
    if not data:
        return 0.0, 0.0

    # Get number of correlations for this spw.
    corr_type = get_corr_products(ms, int(spwid))
    ncorrs = len(corr_type)

    # Select which correlations to consider for computing the mean
    # visibility flux:
    #  - for single and dual pol, consider all correlations.
    #  - for ncorr == 4 with linear correlation products (XX, XY, etc)
    #    select the XX and YY columns.
    #  - for other values of ncorrs, or e.g. circular correlation (LL, RL)
    #    raise a warning that these are not handled.
    if ncorrs in [1, 2]:
        columns_to_select = range(ncorrs)
    elif ncorrs == 4 and set(corr_type) == {'XX', 'XY', 'YX', 'YY'}:
        columns_to_select = [corr_type.index('XX'), corr_type.index('YY')]
    else:
        LOG.warning('Unexpected polarisations found for MS %s, unable to compute mean visibility fluxes.',
                    ms.basename)
        columns_to_select = []

    # Derive mean flux and variance for each polarisation.
    mean_fluxes = []
    variances = []
    for col in columns_to_select:
        # Select data for current polarisation.
        ampdata = numpy.squeeze(data['corrected_data'], axis=1)[col]
        flagdata = numpy.squeeze(data['flag'], axis=1)[col]
        weightdata = data['weight'][col]

        # Select for non-flagged data and non-NaN data.
        id_nonbad = numpy.where(numpy.logical_and(numpy.logical_not(flagdata), numpy.isfinite(ampdata)))
        amplitudes = ampdata[id_nonbad]
        weights = weightdata[id_nonbad]

        # If no valid data are available, skip to the next polarisation.
        if len(amplitudes) == 0:
            continue

        # Determine number of non-flagged antennas, baselines, and
        # integrations.
        ant1 = data['antenna1'][id_nonbad]
        ant2 = data['antenna2'][id_nonbad]
        n_ants = len(set(ant1) | set(ant2))
        n_baselines = n_ants * (n_ants - 1) // 2
        n_ints = len(amplitudes) // n_baselines

        # PIPE-644: Determine scale factor for variance.
        var_scale = numpy.mean([len(amplitudes), n_ints * n_ants])

        # Compute mean flux and stdev for current polarisation.
        mean_flux = numpy.abs(numpy.average(amplitudes, weights=weights))
        variance = numpy.average((numpy.abs(amplitudes) - mean_flux)**2, weights=weights) / var_scale

        # Store for this polarisation.
        mean_fluxes.append(mean_flux)
        variances.append(variance)

    # Compute mean flux and mean stdev for all polarisations.
    if mean_fluxes:
        mean_flux = numpy.mean(mean_fluxes)
        std_flux = numpy.mean(variances)**0.5
    # If no valid data was found for any polarisation, then set flux and
    # uncertainty to zero.
    else:
        LOG.debug('No valid data found for MS %s, field %s, spw %s, unable to compute mean visibility flux;'
                  ' flux and uncertainty will be set to zero.', ms.basename, fieldid, spwid)
        mean_flux = 0.0
        std_flux = 0.0

    return mean_flux, std_flux
