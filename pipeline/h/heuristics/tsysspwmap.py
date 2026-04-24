#!/usr/bin/env python
#
# tsysspwmap.py
#
# History:
#  v1.0 (scorder, gmoellen, jkern; 2012Apr26) == initial version
#  v1.1 (gmoellen; 2013Mar07) Lots of improvements from Eric Villard
#  v1.2 (ldavis; 2013May15) Ported to pipeline
#
# This script defines several functions useful for ALMA Tsys processing.
#
# tsysspwmap  - generate an "applycal-ready" spwmap for TDM to FDM
#                 transfer of Tsys
#
from __future__ import annotations

from typing import TYPE_CHECKING

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.utils as utils
from pipeline.infrastructure import casa_tools

if TYPE_CHECKING:
    from pipeline.domain.measurementset import MeasurementSet

LOG = infrastructure.get_logger(__name__)


def trim_spw_map(spw_map: list[int]) -> list[int]:
    """
    Trim a spw map (list of SpW IDs) to remove tail end where SpWs are mapped to
    themselves.

    E.g.
        [0, 1, 2, 2, 4, 4, 6, 7, 8, 9]
    gets trimmed to:
        [0, 1, 2, 2, 4, 4]

    This assumes that CASA will by default map SpWs to themselves if they do not
    appear in the spw map.

    Args:
        spw_map: SpW map to trim.

    Returns:
        Trimmed SpW map.
    """
    for i in reversed(range(len(spw_map))):
        if spw_map[i] != i:
            return spw_map[:i + 1]
    return []


def tsysspwmap(ms: MeasurementSet, tsystable: str | None = None, channel_tolerance: int = 1, trim: bool = True)\
        -> tuple[list[int], list[int]]:
    """
    Generate default spectral window map for ALMA Tsys, including TDM->FDM
    associations.

    This function generates an "applycal-ready" SpW-to-Tsys-SpW mapping that
    provides the appropriate information regarding the transfer of the Tsys
    calibration from TDM spectral windows to FDM spectral windows.

    If provided a Tsys Caltable that you wish to apply to a MeasurementSet, then
    it filters to only use Tsys SpW(s) that appear in the caltable; otherwise,
    it will use all Tsys SpWs present in MS and assume these are present in the
    caltable.

    The resulting tsys spwmap can then be supplied to the applycal spwmap
    parameter to ensure proper Tsys calibration application.

    Args:
        ms: The measurement set (object) to process.
        tsystable: Optional, the input Tsys caltable (w/ TDM Tsys measurements),
            used to identify which Tsys SpW(s) are available.
        channel_tolerance: Frequency tolerance in number of channels to use in
            matching Tsys SpW freq. range to SpW freq. range.
        trim: If True (the default), return minimum-length spwmap; otherwise the
            spwmap will be exhaustive and include the high-numbered (and usually
            irrelevant) WVR SpWs.

    Returns:
        2-tuple containing:
        - list of unmatched SpW IDs.
        - list representing the SpW-to-Tsys-SpW mapping.
    """
    # Case of Nobeyama(=NRO) data
    if ms.antenna_array.name == "NRO":
        LOG.debug('Mapping process between Tsys windows and Science windows is not specially needed.')
        spw_mapping = [spw.id for spw in ms.get_spectral_windows()]
        return [], spw_mapping

    # Retrieve all spectral windows.
    spectral_windows = ms.get_spectral_windows(science_windows_only=False)

    # Identify the Tsys spectral windows.
    #
    # If a Tsys caltable is provided, then select spectral windows with entries
    # in the Tsys solutions table.
    if tsystable is not None:
        with casa_tools.TableReader(tsystable) as table:
            spwids_in_tsyscaltable = set(table.getcol("SPECTRAL_WINDOW_ID"))
        tsys_spectral_windows = [spw for spw in spectral_windows if spw.id in spwids_in_tsyscaltable]
    # Otherwise, select spectral windows in MS that cover ATMOSPHERE intent and
    # are of type "TDM".
    else:
        tsys_spectral_windows = [spw for spw in spectral_windows if 'ATMOSPHERE' in spw.intents and spw.type == 'TDM']

    # Precompute frequency tolerance bounds for each Tsys SpW.
    tsys_bounds = {
        spw.id: (
            spw.min_frequency - channel_tolerance * spw.channels[0].getWidth(),
            spw.max_frequency + channel_tolerance * spw.channels[-1].getWidth()
        )
        for spw in tsys_spectral_windows
    }

    # Initialize SpW-to-Tsys-Spw-mapping with one-to-one mapping as default.
    spw_mapping = list(range(len(spectral_windows)))
    unmatched_spws = []

    # Match each SpW to a suitable Tsys SpW with matching frequency range, same
    # baseband, and same spectral spec.
    for spw in spectral_windows:
        for tsys_spw in tsys_spectral_windows:
            min_bound, max_bound = tsys_bounds[tsys_spw.id]
            if (
                    spw.baseband == tsys_spw.baseband
                    and spw.spectralspec == tsys_spw.spectralspec
                    and spw.min_frequency >= min_bound
                    and spw.max_frequency <= max_bound
            ):
                spw_mapping[spw.id] = tsys_spw.id
                break
        else:
            unmatched_spws.append(spw.id)

    # Log in case any science SpWs had no matching Tsys SpW.
    unmatched_scispws = [spw.id for spw in ms.get_spectral_windows() if spw.id in unmatched_spws]
    if unmatched_scispws:
        LOG.info(f"No Tsys match found for science SpW(s) {utils.commafy(unmatched_scispws, False)}.")

    # Trim off "excess SpWs" (SpWs mapped to themselves) from map if asked.
    if trim:
        spw_mapping = trim_spw_map(spw_mapping)

    LOG.info(f"Computed tsysspwmap is: {spw_mapping}")

    return unmatched_scispws, spw_mapping
