import collections
import decimal

import pipeline.domain.measures as measures
import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.utils as utils
from pipeline.domain import SpectralWindow
from pipeline.infrastructure import casa_tools

LOG = infrastructure.logging.get_logger(__name__)

IntentField = collections.namedtuple('IntentField', 'intent field')
SpwMapping = collections.namedtuple('SpwMapping', 'combine spwmap snr_info snr_threshold_used solint gaintype calc_snr_info')


def combine_spwmap(scispws: list[SpectralWindow]) -> list:
    """
    Returns a spectral window map where each science spectral window is mapped
    to the lowest science spectral window ID that matches its Spectral Spec.

    Args:
        scispws: List of spectral window objects for science spectral windows.

    Returns:
        List of spectral window IDs, representing the spectral window map.
    """
    # Create dictionary of spectral specs and their corresponding science
    # spectral window ids.
    spspec_to_spwid_map = utils.get_spectralspec_to_spwid_map(scispws)

    # Identify highest science spw id, and initialize the spwmap for every
    # spectral window id through the max science spectral window id.
    max_scispwid = max([spw.id for spw in scispws])
    combinespwmap = list(range(max_scispwid + 1))

    # Make a reference copy for comparison.
    refspwmap = list(combinespwmap)

    # For each spectral spec, map corresponding science spws to the lowest
    # spw id of the same spectral spec.
    for spspec_spwids in spspec_to_spwid_map.values():
        combine_spwid = min(spspec_spwids)
        for spwid in spspec_spwids:
            combinespwmap[spwid] = combine_spwid

    # Return the new map
    if combinespwmap == refspwmap:
        return []
    else:
        return combinespwmap


def snr_n2wspwmap(scispws: list[SpectralWindow], snrs: list, snrlimit: float) -> tuple[bool, list]:
    """
    Compute a spectral window map based on signal-to-noise information.

    This will group input spectral windows into Spectral Specs, then loop over
    Spectral Specs, and identify within each Spectral Spec the SpW with the best
    SNR above the input minimum SNR limit. Finally, a spectral window maps is
    created, where each SpW is mapped to:
     - itself if its SNR is good enough, or
     - a good-SNR SpW within the same Spectral Spec, or
     - itself if there is no good-SNR SpW within the same Spectral Spec.

    If all spectral specs have at least one good SpW to re-map to, then all SpWs
    will have a good mapping and therefore the returned goodmap = True.
    Otherwise, goodmap is returned as False.

    Args:
        scispws: List of spectral window objects for science spectral windows.
        snrs: List of snr values for scispws
        snrlimit: Minimum SNR a SpW needs to exceed to be considered good enough
            for SpWs to be mapped to.

    Returns:
        Two-tuple containing:
        * Boolean declaring if a good mapping was found for all SpWs.
        * List of spectral window IDs representing the spectral window map.
    """
    # Create dictionary of spectral specs and their corresponding science
    # spectral window ids.
    spspec_to_spwid_map = utils.get_spectralspec_to_spwid_map(scispws)
   
    # For each spectral spec, find the SpW with highest SNR above the threshold.
    snrdict = {spspec: {'snr': 0.0, 'spwid': None} for spspec in spspec_to_spwid_map.keys()}
    for scispw, snr in zip(scispws, snrs):
        if snr < snrlimit:
            continue
        if snr > snrdict[scispw.spectralspec]['snr']:
            snrdict[scispw.spectralspec] = {'snr': snr, 'spwid': scispw.id}
    LOG.debug('Maximum SNR per spectral spec dictionary %s' % snrdict)

    # Initialize output SpW map, sized to fit all science SpWs.
    phasespwmap = list(range(max(spw.id for spw in scispws) + 1))

    # Within each spectral spec, find a matching spw for each science spw.
    # Track whether a good mapping is found for all SpWs.
    goodmap = True
    for spspec, spwids in spspec_to_spwid_map.items():
        for scispw, snr in zip(scispws, snrs):
            if scispw.id in spwids:
                LOG.debug('Looking for match to spw id %s' % scispw.id)
                # If the highest SNR within this spectral spec is at or below
                # the limit, then there is no good SpW to re-map to, so instead
                # match SpW to itself.
                if snrdict[spspec]['snr'] <= snrlimit:
                    phasespwmap[scispw.id] = scispw.id
                    LOG.debug('No good SNR spw in spectral spec so match spw id %s to itself' % scispw.id)
                    goodmap = False
                    continue 

                # Good SNR so match spw to itself regardless of any other criteria
                if snr > snrlimit:
                    phasespwmap[scispw.id] = scispw.id
                    LOG.debug('Good SNR so matched spw id %s to itself' % scispw.id)
                # Otherwise, match SpW to highest SNR SpW within spectral spec.
                else:
                    phasespwmap[scispw.id] = snrdict[spspec]['spwid']
                    LOG.debug('Matched spw id %s to highest SNR spw %s' % (scispw.id, snrdict[spspec]['spwid']))

    return goodmap, phasespwmap


def simple_n2wspwmap(scispws: list[SpectralWindow], maxnarrowbw: str, maxbwfrac: float, samebb: bool) -> list:
    """
    Compute a simple phase up wide to narrow spectral window map.

    Args:
        scispws: List of spectral window objects for science spectral windows.
        maxnarrowbw: Maximum narrow bandwidth, e.g. '300MHz'
        maxbwfrac: Width must be > maxbwfrac * maximum bandwidth for a match
        samebb: If possible match within a baseband

    Returns:
        List of spectral window IDs, representing the spectral window map.
    """
    quanta = casa_tools.quanta

    # Find the maximum science spw bandwidth for each science receiver band.
    bwmaxdict = {}
    for scispw in scispws:
        bandwidth = scispw.bandwidth
        if scispw.band in bwmaxdict:
            if bandwidth > bwmaxdict[scispw.band]:
                bwmaxdict[scispw.band] = bandwidth
        else:
            bwmaxdict[scispw.band] = bandwidth

    # Convert the maximum narrow bandwidth to the correct format
    maxnbw = quanta.convert(quanta.quantity(maxnarrowbw), 'Hz')
    maxnbw = measures.Frequency(quanta.getvalue(maxnbw).item(), measures.FrequencyUnits.HERTZ)

    # Find a matching spw each science spw
    matchedspws = []
    failedspws = []
    for scispw in scispws:

        #  Wide spw, match spw to itself.
        if scispw.bandwidth > maxnbw:
            matchedspws.append(scispw)
            LOG.debug('Matched spw id %s to itself' % scispw.id)
            continue

        # Loop through the other science
        # windows looking for a match
        bestspw = None
        for matchspw in scispws:

            # Skip self
            if matchspw.id == scispw.id:
                LOG.debug('Skipping match with self for spw id %s' % matchspw.id)
                continue

            # Don't match across receiver bands
            if matchspw.band != scispw.band:
                LOG.debug('Skipping bad receiver band match for spw id %s' % matchspw.id)
                continue

            # Skip if the match window is narrower than the window in question
            # or narrower than a certain fraction of the maximum bandwidth. 
            if matchspw.bandwidth <= scispw.bandwidth or \
                    matchspw.bandwidth < decimal.Decimal(str(maxbwfrac)) * bwmaxdict[scispw.band]:
                LOG.debug('Skipping bandwidth match condition spw id %s' % matchspw.id)
                continue

            # First candidate match
            if bestspw is None:
                bestspw = matchspw

            # Find the spw with the closest center frequency
            elif not samebb:
                if abs(scispw.centre_frequency.value - matchspw.centre_frequency.value) < \
                        abs(scispw.centre_frequency.value - bestspw.centre_frequency.value):
                    bestspw = matchspw

            else:
                # If the candidate match is in the same baseband as the science spw but the current best
                # match is not then switch matches.
                if matchspw.baseband == scispw.baseband and bestspw.baseband != scispw.baseband:
                    bestspw = matchspw
                else:
                    if abs(scispw.centre_frequency.value - matchspw.centre_frequency.value) < \
                            abs(scispw.centre_frequency.value - bestspw.centre_frequency.value):
                        bestspw = matchspw

        # Append the matched spw to the list
        if bestspw is None:
            LOG.debug('    Simple spw mapping failed for spw id %s' % scispw.id)
            matchedspws.append(scispw)
            failedspws.append(scispw)
        else:
            matchedspws.append(bestspw)

    # Issue a warning if any spw failed spw mapping
    if len(failedspws) > 0:
        LOG.warning('Cannot map narrow spws %s to wider ones - defaulting these to standard mapping' %
                    [spw.id for spw in failedspws])

    # Find the maximum science spw id
    max_spwid = 0
    for scispw in scispws:
        if scispw.id > max_spwid:
            max_spwid = scispw.id

    # Initialize the spwmap. All spw ids up to the maximum science spw id must be
    # defined in the map passed to CASA.
    phasespwmap = []
    for i in range(max_spwid + 1):
        phasespwmap.append(i)

    # Make a reference copy for comparison
    refphasespwmap = list(phasespwmap)

    # Set the science window spw map using the matching spw ids
    for scispw, matchspw in zip(scispws, matchedspws):
        phasespwmap[scispw.id] = matchspw.id

    # Return the new map
    if phasespwmap == refphasespwmap:
        return []
    else:
        return phasespwmap


def update_spwmap_for_band_to_band(spwmap: list[int], dg_refspws: list[SpectralWindow],
                                   dg_srcspws: list[SpectralWindow], combine: bool = False) -> list[int]:
    """
    This method updates the input SpW mapping to remap diffgain on-source SpWs to
    associated diffgain reference SpWs within the same baseband, and returns the
    updated SpW mapping.

    Args:
        spwmap: SpW mapping to update
        dg_refspws: diffgain reference SpWs
        dg_srcspws: diffgain on-source SpWs
        combine: boolean declaring whether the SpW mapping uses SpW combination.

    Returns:
        List representing the updated SpW mapping.
    """
    # Ensure that the length of the input SpW map is sufficient to include all
    # diffgain SpWs; if necessary, add the missing SpWs, where each missing SpW
    # is mapped to itself.
    max_spw_id = max(spw.id for spw in dg_refspws + dg_srcspws)
    if len(spwmap) < max_spw_id + 1:
        spwmap.extend(list(range(len(spwmap), max_spw_id + 1)))

    # Modify the SpW mapping to ensure that diffgain on-source SpWs are remapped
    # to an appropriate diffgain reference SpW.
    if combine:
        # PIPE-2499: in case of SpW combination, map all diffgain on-source SpWs
        # to the diffgain reference SpW with the lowest ID.
        min_dg_refspw_id = min(spw.id for spw in dg_refspws)
        for dg_srcspw in dg_srcspws:
            spwmap[dg_srcspw.id] = min_dg_refspw_id
    else:
        # Otherwise, assuming narrow-to-wide SpW mapping, map each diffgain
        # on-source SpW to a diffgain reference SpW with the same baseband.
        # PIPE-2059: this mapping can in principle be to any diffgain reference
        # SpW that matches the baseband, but here it will preferentially match
        # to the diffgain reference SpW with the highest ID.
        for dg_srcspw in dg_srcspws:
            max_dg_refspw_id = max(spw.id for spw in dg_refspws if
                                   spw.baseband == dg_srcspw.baseband)
            spwmap[dg_srcspw.id] = spwmap[max_dg_refspw_id]
    return spwmap
