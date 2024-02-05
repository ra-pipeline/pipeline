import os
import re

import numpy as np

import pipeline as pipeline
import pipeline.infrastructure as infrastructure
from pipeline import environment
from pipeline.infrastructure import casa_tools

LOG = infrastructure.get_logger(__name__)


# utility to make miscinfo clean
def clean_extendable_keys(data, key, num_keys=None):
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


# Add information to image header
def set_miscinfo(name, spw=None, virtspw=True, field=None, nfield=None, datatype=None, type=None, iter=None,
                 intent=None, specmode=None, robust=None, weighting=None, is_per_eb=None, context=None):
    """Define miscellaneous image information."""
    if name == '':
        return

    with casa_tools.ImageReader(name) as image:
        info = image.miscinfo()
        if name is not None:
            filename_components = os.path.basename(name).split('.')
            info['nfilnam'] = len(filename_components)
            for i, filename_component in enumerate(filename_components):
                info['filnam{:02d}'.format(i+1)] = filename_component

            # clean up extra "filnamX" entries
            info = clean_extendable_keys(info, 'filnam')

        if spw is not None:
            unique_spws = ','.join(np.unique(spw.split(',')))
            if context is not None and context.observing_run is not None:
                spw_names = [
                    context.observing_run.virtual_science_spw_shortnames.get(
                        context.observing_run.virtual_science_spw_ids.get(int(spw_id), 'N/A'), 'N/A')
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
            info['propcode'] = str(context.project_summary.proposal_code).strip()
            info['group'] = 'N/A'
            info['member'] = context.project_structure.ousstatus_entity_id
            info['sgoal'] = 'N/A'

        # Some keywords should be present but are filled only
        # for other modes (e.g. single dish).
        info['offra'] = -999.0
        info['offdec'] = -999.0

        image.setmiscinfo(info)
