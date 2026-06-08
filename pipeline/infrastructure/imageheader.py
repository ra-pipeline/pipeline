from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

import pipeline
from pipeline import environment, infrastructure
from pipeline.infrastructure import casa_tools
from textwrap import wrap

if TYPE_CHECKING:
    from pipeline.domain import DataType
    from pipeline.infrastructure.launcher import Context

LOG = infrastructure.logging.get_logger(__name__)


# utility to make miscinfo clean
def clean_extendable_keys(data: dict, key: str, num_keys: int | None = None) -> dict:
    """
    Remove extra entries in data. Logic is as follows:

        1. if num_keys is not given, take the number
           from the data using key ("n{key}")
        2. check if the entry whose keyword is "{key}X"
           where X denotes any integer
        3. remove the entry if X > num_keys

    Arguments:
        data {dict} -- Dictionary to be processed
        key {str} -- Key for the dictionary

    Keyword Arguments:
        num_keys {int} -- Number of expected entries for
                          given key. If not given (None),
                          get the number from data.
                          (default: {None})

    Returns:
        dict -- Reference to the data
    """
    if num_keys is None:
        number_key = 'n{}'.format(key)
        num_keys = data[number_key]

    # remove extra entries of "filnam0X"
    # it typically requires for single dish pipeline
    for k in list(data.keys()):
        if re.match(r'^{}[0-9]+$'.format(key), k):
            n = int(re.sub(r'^[a-zA-Z]+', '', k))
            if n > num_keys:
                data.pop(k, None)
    return data


def wrap_key(data: dict, key: str, value: str) -> dict:
    """
    FITS string header keyword content is limited to 68 characters.
    Longer content needs to be written to multiple keywords.
    The "long string" convention is not supported by CASA's
    exportfits.

    Arguments:
        data {dict} -- Dictionary to be processed
        key {str}   -- Key for the dictionary
        value {str} -- Value for the dictionary

    Returns:
        dict -- Reference to the data

    """
    key_len = len(key)
    if key_len > 6:
        raise ValueError('Wrapped keyword basename must be <=6 characters')

    value_components = wrap(value, 68)
    vc_len = len(value_components)
    if vc_len > 99:
        raise ValueError(f'Too many wrap elements for {key}XX keywords')
    data[f'n{key}'] = vc_len
    for i, value_component in enumerate(value_components):
        data[f'{key}{(i+1):02d}'] = value_component

    return data


# Add information to image header
def set_miscinfo(
        name,
        spw: str | None = None,
        virtspw: bool = True,
        field: str | None = None,
        nfield: int | None = None,
        datatype: DataType | None = None,
        type: str | None = None,
        iter: int | None = None,
        intent: str | None = None,
        specmode: str | None = None,
        robust: float | None = None,
        weighting: str | None = None,
        is_per_eb: bool | None = None,
        context: Context | None = None,
        ) -> None:
    """
    Defines miscellaneous image information and updates the image header using the built-in CASA function setmiscinfo.

    Args:
        name: Name of the image to be modified.
        spw: A comma-delimited string containing the relevant spw IDs.
        virtspw: Signifies whether the spw IDs should be mapped to real or virtual spws
        field: The field name associated with the image.
        nfield: The number of fields present in the image.
        datatype: A DataType object that signifies the type of data used to create the image.
        type: The image type, typically appended to the end of the image name (i.e. 'model', 'residual', etc.).
        iter: The current clean iteration of the image.
        intent: The intent of the data used to create the image (i.e. 'TARGET').
        specmode: The spectral definition mode of the image (i.e. 'mfs', 'cube', etc.).
        robust: The robust weighting of the image.
        weighting: The weighting scheme used to create the image (i.e. 'briggs').
        is_per_eb: Signifies whether the data used to create the image was from a single EB or from multiple EBs.
        context: The Context object that contains information about the current pipeline run.
    """
    if name == '':
        return

    with casa_tools.ImageReader(name) as image:
        info = image.miscinfo()
        if name is not None:
            # PIPE-533, limiting 'filnamXX' keyword length to 68 characters
            # due to FITS header keyword string length limit.
            info = wrap_key(info, 'filnam', os.path.basename(name))

            # clean up extra "filnamX" entries
            info = clean_extendable_keys(info, 'filnam')

        if spw is not None:
            unique_spws = ','.join(map(str, sorted({int(s) for s in spw.split(',') if s})))
            if context is not None and context.observing_run is not None:
                spw_names = [
                    context.observing_run.virtual_science_spw_ids.get(int(spw_id), 'N/A')
                    for spw_id in unique_spws.split(',')
                ]
            else:
                spw_names = ['N/A']
            # Write spw IDs. For some observatories these are virtual IDs because of
            # changing real IDs for the same frequency setup between MSes. In that case
            # we also write the "virtspw" and "spwisvrt" keywords.
            info['spw'] = unique_spws
            if virtspw:
                info['virtspw'] = unique_spws
                info['spwisvrt'] = True
            else:
                info['spwisvrt'] = False
            info['nspwnam'] = len(spw_names)
            for i, spw_name in enumerate(spw_names):
                info['spwnam{:02d}'.format(i+1)] = spw_name

            # clean up extra "spwnamX" entries
            info = clean_extendable_keys(info, 'spwnam')

        if field is not None:
            # TODO: Find common key calculation. Long VLASS lists cause trouble downstream.
            #       Truncated list may cause duplicates.
            #       Temporarily (?) remove any '"' characters
            tmpfield = field.split(',')[0].replace('"', '')
            info['field'] = tmpfield

        if nfield is not None:
            info['nfield'] = nfield

        if context is not None:
            # TODO: Use more generic approach like in the imaging heuristics
            if context.project_summary.telescope == 'ALMA':
                info['npol'] = len(context.observing_run.measurement_sets[0].get_alma_corrstring().split(','))
            elif context.project_summary.telescope in ('VLA', 'EVLA'):
                info['npol'] = len(context.observing_run.measurement_sets[0].get_vla_corrstring().split(','))
            else:
                info['npol'] = -999

        if datatype is not None:
            info['datatype'] = datatype

        if type is not None:
            info['type'] = type

        if iter is not None:
            info['iter'] = iter

        if intent is not None:
            info['intent'] = intent

        if specmode is not None:
            info['specmode'] = specmode

        if robust is not None:
            info['robust'] = robust

        if weighting is not None:
            info['weight'] = weighting

        if is_per_eb is not None:
            info['per_eb'] = is_per_eb

        # Pipeline / CASA information
        pipever = pipeline.revision
        if len(pipever) > 68:
            pipever = pipever[0:67]
            LOG.info(f'Truncated pipeline revision to 68 characters: was "{pipeline.revision}"; now "{pipever}"')
        info['pipever'] = pipever
        info['casaver'] = environment.casa_version_string

        # Project information
        if context is not None:
            info['propcode'] = context.project_summary.proposal_code
            info['group'] = 'N/A'
            info['member'] = context.project_structure.ousstatus_entity_id
            info['sgoal'] = 'N/A'

        # Some keywords should be present but are filled only
        # for other modes (e.g. single dish).
        info['offra'] = -999.0
        info['offdec'] = -999.0

        image.setmiscinfo(info)
