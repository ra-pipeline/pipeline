from __future__ import annotations

import numpy as np
from typing import TYPE_CHECKING

from pipeline.domain.measures import FrequencyUnits

if TYPE_CHECKING:
    from pipeline.domain import MeasurementSet

# List of SSO objects
SSOfieldnames = {
    "Callisto",
    "Ceres",
    "Europa",
    "Ganymede",
    "Juno",
    "Jupiter",
    "Mars",
    "Neptune",
    "Pallas",
    "Titan",
    "Uranus",
    "Venus",
    "Vesta",
}

UnitFactorType = dict[int, dict[str, float]]


def get_intents_to_process(ms: MeasurementSet, intents: list[str]) -> list[str]:
    """
    Optimise a list of intents so that scans with multiple intents are only
    processed once.

    Returns an improved, though not necessarily globally optimal, ordering of
    intents for processing. The effectiveness of the optimisation is
    influenced by the sequence in which MSes and their associated intents are
    evaluated, and may not guarantee minimal total processing due to this
    ordering dependency.

    :param ms: MeasurementSet domain object
    :param intents: list of intents to consider for processing
    :return: optimised list of intents to process
    """
    intents_to_process = []
    for intent in intents:
        for scan in ms.get_scans(scan_intent=intent):
            scan_included_via_other_intent = any(
                i in scan.intents for i in intents_to_process
            )
            field_is_not_sso = SSOfieldnames.isdisjoint(
                {field.name for field in scan.fields}
            )

            if not scan_included_via_other_intent and field_is_not_sso:
                intents_to_process.append(intent)

    return intents_to_process


def get_unit_factor(ms: MeasurementSet) -> UnitFactorType:
    """
    Calculate unit factors for amplitude and phase slopes and intercepts.

    These factors are used to convert the slope and intercept values to
    the correct units for plotting.

    :param ms: MeasurementSet domain object
    :return: dictionary of unit factors per spectral window
    """
    unit_factor = {}
    for spw in ms.spectral_windows:
        bandwidth = spw.bandwidth
        bandwidth_ghz = float(bandwidth.to_units(FrequencyUnits.GIGAHERTZ))

        # plot factors to get the right units, frequencies in GHz:
        unit_factor[spw.id] = {
            "amp_slope": 1.0 / bandwidth_ghz,
            "amp_intercept": 1.0,
            "phase_slope": (180.0 / np.pi) / bandwidth_ghz,
            "phase_intercept": (180.0 / np.pi),
        }

    return unit_factor
