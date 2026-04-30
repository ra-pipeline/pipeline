from __future__ import annotations

from typing import TYPE_CHECKING

import pipeline.infrastructure as infrastructure

if TYPE_CHECKING:
    from pipeline.domain import MeasurementSet

LOG = infrastructure.logging.get_logger(__name__)


def get_antenna_names(ms: MeasurementSet) -> tuple[dict[int, str], list[int]]:
    """Get antenna names.
    """
    antenna_ids = sorted([antenna.id for antenna in ms.antennas])
    antenna_name = {}
    for antenna_id in antenna_ids:
        antenna_name[antenna_id] = [antenna.name for antenna in ms.antennas
                                    if antenna.id == antenna_id][0]

    return antenna_name, antenna_ids


def get_corr_products(ms: MeasurementSet, spwid: int) -> str:
    """Get names of corr products stored in ms.
    """
    # get names of correlation products
    datadescs = [dd for dd in ms.data_descriptions if dd.spw.id == spwid]
    polarization = ms.polarizations[datadescs[0].pol_id]
    corr_type = polarization.corr_type_string

    return corr_type


def get_corr_axis(ms: MeasurementSet, spwid: int) -> list[str]:
    """Get names of polarizations
    """
    # get names of the polarizations
    datadescs = [dd for dd in ms.data_descriptions if dd.spw.id == spwid]
    # return datadescs[0].corr_axis
    return datadescs[0].polarizations


def get_pol_id(ms: MeasurementSet, spwid: int, corr: str) -> int:
    """Get polarization ID for given MS, SpW id, and correlation type.
    """
    datadesc = ms.get_data_description(id=spwid)
    pol_id = datadesc.get_polarization_id(corr)
    return pol_id
