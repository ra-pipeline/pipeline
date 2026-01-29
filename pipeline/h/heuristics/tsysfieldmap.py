from __future__ import annotations

import collections
from typing import TYPE_CHECKING

import pipeline.infrastructure as infrastructure
import pipeline.infrastructure.utils as utils

if TYPE_CHECKING:
    from pipeline.domain import MeasurementSet

LOG = infrastructure.get_logger(__name__)

# Holds an observing intent and the preferred/fallback gainfield args to be used for that intent
GainfieldMapping = collections.namedtuple('GainfieldMapping', 'intent preferred fallback')


def get_intent_to_tsysfield_map(ms: MeasurementSet, is_single_dish: bool) -> dict[str, str]:
    """
    Get the mapping of observing intent to gainfield parameter for a
    measurement set.

    The mapping follows the observing intent to gainfield intent defined in
    CAS-12213.

    Args:
        ms: MS to analyse.
        is_single_dish: boolean for if SD data or not.

    Returns:
        Dictionary of {observing intent: gainfield}.
    """
    soln_map = get_solution_map(ms, is_single_dish)
    final_map = {s.intent: s.preferred if s.preferred else s.fallback for s in soln_map}

    # Detect cases where there's no preferred or fallback gainfield mapping,
    # e.g., if there are no Tsys scans on a target or phase calibrator.
    undefined_intents = [k for k, v in final_map.items()
                         if not v  # gainfield mapping is empty..
                         and k in ms.intents]  # ..for a valid intent in the MS
    if undefined_intents:
        msg = 'Undefined Tsys gainfield mapping for {} intents: {}'.format(ms.basename, undefined_intents)
        LOG.error(msg)
        raise AssertionError(msg)

    # convert magic string back to empty string
    converted = {k: v.replace('___EMPTY_STRING___', '') for k, v in final_map.items()}

    return converted


def get_tsys_fields_for_intent(ms: MeasurementSet, intent: str, exclude_intents: str | None = None) -> set[str]:
    """
    Returns the identity of the Tsys field(s) for an intent.

    Args:
        ms: MS to analyse.
        intent: Intent to retrieve fields for.
        exclude_intents: String of intent(s) (comma-separated) that should not
            be covered by the Tsys field.

    Returns:
        Set of field identifiers corresponding to given intent, while not
        associated with intents (optionally) given by ``exclude_intents``.
    """
    # In addition to the science intent scan, a field must also have a Tsys
    # scan observed for a Tsys solution to be considered present. The
    # exception is science mosaics, which are handled as a special case.

    # We need to know which science intent scans have Tsys scans; the ones
    # that don't will be checked for science mosaics separately. This lets
    # us handle single field, single pointing science targets alongside mosaic
    # targets mixed together in the same EB. Theoretically, at least...
    intent_fields = ms.get_fields(intent=intent)

    # PIPE-2394: If requested, avoid matching fields that cover any of the
    # intents that are to be excluded.
    if exclude_intents is not None:
        intent_fields = [f for f in intent_fields if f.intents.isdisjoint(set(exclude_intents.split(',')))]

    # contains fields of this intent that also have a companion Tsys scan
    intent_fields_with_tsys = [f for f in intent_fields if 'ATMOSPHERE' in f.intents]

    # contains fields without a companion Tsys scan. These might be science
    # mosaics.
    intent_fields_without_tsys = [f for f in intent_fields if f not in intent_fields_with_tsys]

    tsys_fields_for_mosaics = []
    if intent == 'TARGET':
        # In science mosaics, the fields comprising the TARGET pointings do
        # not have Tsys scans observed on those fields. Instead, there is a
        # Tsys-only field roughly at the centre of the mosaic that is
        # referenced by the same parent source as the TARGET pointing fields.

        # Double check that the fields without Tsys scans are indeed science
        # mosaics with a separate Tsys field. Note that a mosaic consisting of
        # a source with a single TARGET pointing and a single Tsys scan would
        # also be classified as a mosaic by this logic.
        mosaic_fields = [f for f in intent_fields_without_tsys if 'ATMOSPHERE' in f.source.intents]

        # Collect the Tsys fields referenced by the parent source of the
        # science mosaic fields missing Tsys scans.
        tsys_fields_for_mosaics = [f
                                   for pointing in mosaic_fields
                                   for f in pointing.source.fields if 'ATMOSPHERE' in f.intents]

    r = {field.id for field in intent_fields_with_tsys}
    r.update({field.id for field in tsys_fields_for_mosaics})

    # when field names are not unique, as is usually the case for science
    # mosaics, then we must reference the numeric field ID instead
    field_identifiers = utils.get_field_identifiers(ms)
    return {field_identifiers[i] for i in r}


def get_solution_map(ms: MeasurementSet, is_single_dish: bool) -> list[GainfieldMapping]:
    """
    Get gainfield solution map. Different solution maps are returned for
    single dish and interferometric data.

    Args:
        ms: MS to analyse.
        is_single_dish: True if MS is single dish data.

    Returns:
        List of GainfieldMappings.
    """
    # define function to get Tsys fields for intent
    def f(intent, exclude: str | None = None) -> str:
        if ',' in intent:
            head, tail = intent.split(',', 1)
            # the 'if o' test filters out results for intents that do not have
            # fields, e.g., PHASE for SD data
            # de-deuplicate list before joining as a string
            tsys_fields = utils.deduplicate(o for o in (f(head, exclude=exclude), f(tail, exclude=exclude)) if o)
            return ','.join(tsys_fields)
        return ','.join(str(s) for s in get_tsys_fields_for_intent(ms, intent, exclude_intents=exclude))

    # return different gainfield maps for single dish and interferometric
    if is_single_dish:
        # PIPE-2869: added fallback of ATMOSPHERE for TARGET intent
        #
        # Intent to be calibrated:
        # - BANDPASS cal
        #   * Preferred: all BANDPASS cals.
        #   * Fallback: 'nearest'.
        # - AMPLITUDE cal
        #   * Preferred: all AMPLITUDE cals.
        #   * Fallback: 'nearest'.
        # - TARGET
        #   * Preferred: TARGET and/or ATMOSPHERE sources.
        #   * Fallback: null fallback
        return [
            GainfieldMapping(intent='BANDPASS', preferred=f('BANDPASS'), fallback='nearest'),
            GainfieldMapping(intent='AMPLITUDE', preferred=f('AMPLITUDE'), fallback='nearest'),
            # non-empty magic string to differentiate between no field found and a null fallback
            GainfieldMapping(intent='TARGET', preferred=f('TARGET,ATMOSPHERE'), fallback='___EMPTY_STRING___')
        ]

    else:
        # CAS-12213: original intent mapping.
        # PIPE-2080: updated to add mapping for DIFFGAINREF, DIFFGAINSRC intent.
        # PIPE-2394: updated mapping for PHASE, TARGET, CHECK
        #
        # Intent to be calibrated:
        # - BANDPASS cal
        #   * Preferred: all BANDPASS cals.
        #   * Fallback: 'nearest'.
        # - AMPLITUDE cal
        #   * Preferred: all AMPLITUDE cals.
        #   * Fallback: 'nearest'.
        # - DIFFGAIN[REF|SRC]
        #   * Preferred: all DIFFGAIN cals.
        #   * Fallback to BANDPASS.
        # - PHASE cal
        #   * Preferred: ATMOSPHERE cals, but excluding AMP, BP, DIFFGAIN*, POL* cals, and TARGET.
        #   * Fallback: ATMOSPHERE cals, but excluding AMP, BP, DIFFGAIN*, POL* cals.
        # - TARGET
        #   * Preferred: ATMOSPHERE cals, but excluding AMP, BP, DIFFGAIN*, POL* cals, and PHASE.
        #   * Fallback: ATMOSPHERE cals, but excluding AMP, BP, DIFFGAIN*, POL* cals.
        # - CHECK_SOURCE
        #   * Preferred: ATMOSPHERE cals, but excluding AMP, BP, DIFFGAIN*, POL* cals, and PHASE.
        #   * Fallback: ATMOSPHERE cals, but excluding AMP, BP, DIFFGAIN*, POL* cals.

        # PIPE-2394: typical calibrator intents to avoid (all but PHASE)
        # matching searching for nearby Tsys field for PHASE, TARGET, and/or
        # CHECK.
        exclude_intents = 'AMPLITUDE,BANDPASS,DIFFGAINREF,DIFFGAINSRC,POLARIZATION,POLANGLE,POLLEAKAGE'

        return [
            GainfieldMapping(intent='BANDPASS', preferred=f('BANDPASS'), fallback='nearest'),
            GainfieldMapping(intent='AMPLITUDE', preferred=f('AMPLITUDE'), fallback='nearest'),
            GainfieldMapping(intent='DIFFGAINREF', preferred=f('DIFFGAINREF'), fallback=f('BANDPASS')),
            GainfieldMapping(intent='DIFFGAINSRC', preferred=f('DIFFGAINSRC'), fallback=f('BANDPASS')),
            GainfieldMapping(intent='PHASE', preferred=f('ATMOSPHERE', exclude=f'{exclude_intents},TARGET'),
                             fallback=f('ATMOSPHERE', exclude=exclude_intents)),
            GainfieldMapping(intent='TARGET', preferred=f('ATMOSPHERE', exclude=f'{exclude_intents},PHASE'),
                             fallback=f('ATMOSPHERE', exclude=exclude_intents)),
            GainfieldMapping(intent='CHECK', preferred=f('ATMOSPHERE', exclude=f'{exclude_intents},PHASE'),
                             fallback=f('ATMOSPHERE', exclude=exclude_intents)),
        ]
