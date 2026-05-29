# Luke Maud - ESO new module for separation angle calculations at importdata

# Do not evaluate type annotations at definition time.
from __future__ import annotations

import collections
import itertools
from typing import TYPE_CHECKING
import numpy as np
from pipeline import infrastructure
from pipeline.infrastructure import casa_tools


if TYPE_CHECKING:
    from pipeline.domain import MeasurementSet
    from pipeline.infrastructure.basetask import Results
    from pipeline.infrastructure.launcher import Context
    
LOG = infrastructure.logging.get_logger(__name__)

__all__ = ['ms_separation_angles']

def ms_separation_angles(
        mses: list[MeasurementSet]
    ) -> dict:  

    """
    Use the ms object imported and compute the separation angle
    of the fields and provide a result dictionary back
    """
    cme = casa_tools.measures
    cqa = casa_tools.quanta # convers the positions
    
    sep_dict = {}  # should this be a collections.dict ? 
    main_intent = 'TARGET'

    LOG.info('Computing the separaton angles of fields with the TARGET(s)')
    
    for msuse in mses:

        phase_target_check_pairing = local_derive_phase_to_target_check_mapping(msuse) 
        # returns a dict that is formatted as {PHASENAME: {TARGETNAME, TARGET2NAME, CHECKNAME}}, ie. names are a set

        
        field_dict = {}  # dict per ms
        mosaic_dict = {}
        ephemeris_dict = {}
        field_tars = [field for field in msuse.get_fields(intent=main_intent)]
        # object will continually list ALL fields even if the same name (mosaic)

        # get the unique TARGET names and test if they are part of a mosaic
        field_name_unique = np.unique([field.name for field in field_tars])
        for field_unq in field_name_unique:
            mosaic_target =  is_mosaic(msuse, field_unq)
            mosaic_dict[field_unq]=mosaic_target
            ephemeris_target = is_eph_obj(msuse, field_unq)
            ephemeris_dict[field_unq]=ephemeris_target
            
        # generally have only one PHASE and one CHECK
        # but lists allow to loop if otherwise (rare case but does happen)
        field_phase = [field for field in msuse.get_fields(intent='PHASE')]
        field_check =  [field for field in msuse.get_fields(intent='CHECK')]
        
        
        for field_use in field_tars:  # this will still loop all fields - same name etc
            if mosaic_dict[field_use.name]:
                # check if the field_dict is filled - dont do same field again
                if field_dict.keys():
                    # there is a key, get back the list of names
                    names_to_match = [keyt[2] for keyt in field_dict.keys()]
                    if field_use.name in names_to_match:
                        #LOG.info('did this field its a mosaic - skipping out of loop') # testing only 
                        continue  # don't define any more fields
                        
                fieldid_in = 'mosaic'
                # we later will loop all fields (ids)
                # by the name and match all separations
            elif ephemeris_dict[field_use.name]:  # bool 
                #LOG.info('Is an ephemeris - using source direction') # testing only
                refdir = cme.getref(field_use.source.direction)                
                # calculate the positons
                if refdir == 'B1950' or refdir == 'J2000':
                    main_intent_dir = cme.measure(field_use.source.direction, 'ICRS') # this converts
                elif refdir == 'ICRS':
                    main_intent_dir = field_use.source.direction # dont need to convert ICRS already and cme takes ages
                else:
                    main_intent_dir = field_use.source.direction # this appears to work directly

                fieldid_in = field_use.id
                    

            else:    
                refdir = cme.getref(field_use.mdirection)
                if refdir == 'B1950' or refdir == 'J2000':
                    main_intent_dir = cme.measure(field_use.mdirection, 'ICRS') # this converts
                elif refdir == 'ICRS':
                    main_intent_dir = field_use.mdirection # dont need to conver ICRS already and cme takes ages
                else:
                    main_intent_dir = field_use.mdirection # dont convert anything

                fieldid_in = field_use.id

                
            # set the field name and id (non mosaic)
            fieldname_in = field_use.name
            if '"' in fieldname_in:
                fieldname_in = fieldname_in.replace('"','')
                
            # technically should be only one phase - the way the loop is written for each target we 're-get' the
            # phase values again - the other coding alternative is loop TAR, PH, CH separate then loop over the
            # stored value. This is anyway fast enuigh (seconds) that I don't believe the investment of
            # and alternative logic loop is required
            
            phcount=0
            for phfield_use in field_phase:
                # now we can use the dict return from the spwphaseup mapping
                # to check if the TARGET is paired with the phase cal
                match_allowed = phase_target_check_pairing[phfield_use.name]
                
                if field_use.name in match_allowed:  
                    phcount+=1
                    refdir = cme.getref(phfield_use.mdirection)
                    if refdir == 'B1950' or refdir == 'J2000':
                        phase_intent_dir = cme.measure(phfield_use.mdirection, 'ICRS') # this converts
                    elif refdir == 'ICRS':
                        phase_intent_dir = phfield_use.mdirection # dont need to conver ICRS already and cme takes ages
                    else:
                        phase_intent_dir = phfield_use.mdirection # dont convert, it is what it is

                    if mosaic_target:
                        # do the mosaic calc
                        cal_sep = get_median_separation(msuse, field_use.name, phase_intent_dir, ephemeris_dict[field_use.name])
                    else:    
                        cal_sep = cme.separation(main_intent_dir, phase_intent_dir)  # measures dict with a 'value' and 'unit' (deg)
                      
                    field_dict[(main_intent,fieldid_in,fieldname_in)] = {('PHASE', phfield_use.id, phfield_use.name): cal_sep}

                else:
                    continue # next one in the phase loop
                
                if phcount > 1:   # shoudlnt happen but add this log for now
                    LOG.info('There is more than one Phase cal for the allowed fields') # testing only - need to check with a multi-phasecal PL-able project


        # check here how many targets we have, don't print all if there are many (can be changed as require/harcode)

        # field dict is for this MS only
        if len(field_dict.keys()) > 4:  # ok for 5 or more we filter as explained in the mako if <5 we show, otherwise max and min separations
            min_sep = 99.0 # start high and we go below
            max_sep = 0.0  # start low and we go above
            for primary, secondaries in field_dict.items():
                intent2 = [(fld2,id2,nm2,ang['unit'],ang['value']) for (fld2,id2,nm2),ang in secondaries.items()][0] # only item per secondary                     
                if intent2[4]<min_sep:
                    min_holder=[primary,secondaries]  # do we need to copy, command line test shows a tuple is writen fully not a pointer?
                    #LOG.info(f'min is currently {min_holder}') # testing
                    min_sep = intent2[4]
                if intent2[4]>max_sep:
                    max_holder = [primary,secondaries]
                    #LOG.info(f'max is currently {max_holder}')  # testing 
                    max_sep = intent2[4]
                       

           
            # once we completed the loop we have min and max, so repopulate the field_dict
            # currently if there is >1 phase cal, this will find a global min and max for TAR to PH, irrespective of
            # if those are paired to be used (or not), can happen same spectral spec, different field pairs
            # does a dataset like that exist ? 
            field_dict = {}
            field_dict[min_holder[0]] = min_holder[1]
            field_dict[max_holder[0]] = max_holder[1]

                    

        # then outside above loops also want PHASE vs CHECK
        # useful for quality of check source
        # this could be used to do a QA score ? 
        chkcount=0
        for chkfield_use in field_check:          
            chkcount+=1
            refdir = cme.getref(chkfield_use.mdirection)
            if refdir == 'B1950' or refdir == 'J2000':
                check_intent_dir = cme.measure(chkfield_use.mdirection, 'ICRS') # this converts
            elif refdir == 'ICRS':
                check_intent_dir = chkfield_use.mdirection # dont need to conver ICRS already and cme takes ages
            else:
                check_intent_dir = chkfield_use.mdirection # dont convert, it is what it is

            if chkcount > 1:
                LOG.info('There is more than one Check source')
                
            phcount=0
            for phfield_use in field_phase:
                # check also the check to phase matching
                match_allowed = phase_target_check_pairing[phfield_use.name]
                if chkfield_use.name in match_allowed:                  
                    phcount+=1
                    refdir = cme.getref(phfield_use.mdirection)
                    if refdir == 'B1950' or refdir == 'J2000':
                        phase_intent_dir = cme.measure(phfield_use.mdirection, 'ICRS') # this converts
                    elif refdir == 'ICRS':
                        phase_intent_dir = phfield_use.mdirection # dont need to conver ICRS already and cme takes ages
                    else:
                        phase_intent_dir = phfield_use.mdirection # dont convert, it is what it is     
                    cal_sep = cme.separation(check_intent_dir, phase_intent_dir)  # measures dict with a 'value' and 'unit' (deg)
                    field_dict[('CHECK',chkfield_use.id,chkfield_use.name)] = {('PHASE', phfield_use.id, phfield_use.name): cal_sep}
                else:
                    continue # dont match this check and phase 
        print(msuse.name, field_dict)         
                
        # get directions and separations, dict is keyed by ms name
        sep_dict[msuse.name] = field_dict 
        
        
    return sep_dict

def is_mosaic(
        ms,
        field_name) -> bool:
    """ 
    Code based loosly on imageparams_base
    that used two small functions in a class to define if
    a field/intent was a mosaic and its own defined 'field' 
    parameter to get a list. Here we can do more simply
    as we are dealing only with the TARGET and we 
    passed a single field name, check if
    there are multiple ids for it

    ms is the measurement set object 
    field is the field name
    
    """
    is_f_mosaic = False
    field_str_list = []
    
    # technically should raise an error if no field passed
    # but we do


    # converting field to ids
    fld_obj = ms.get_fields(intent='TARGET')
    field_str_list = [fld.id for fld in fld_obj if
                      field_name.replace(' ', '') == fld.name.replace(' ','')]
                     # note matching string used fromm imageparams_base code

    field_str_list = ','.join(str(fld_id) for fld_id in field_str_list)

    # again following imageparams_base
    # because a string chain was now made, if there is a ','
    # it means there is more than one field ID for the field name
    # i.e. a mosaic (is there a caveat clause?)
    for field_str in field_str_list:
        if ',' in field_str:
            is_f_mosaic = True

    return is_f_mosaic


def is_eph_obj(msin, field_name):
    """ Method to check if the field object is an ephemeris or not
    as this needs a different extraction of the coordinates"""
    is_eph_obj = False
    #LOG.info('testing if ephem') # testing only 
    # can simply pass name to get fields and check the source property
    is_eph_obj = msin.get_fields(field_name)[0].source.is_eph_obj  # just get first field with that name - if a mosaic there can be many 'field' objects

    
    return is_eph_obj


def get_median_separation(msin, fieldname, phasedir, eph_field):
    """
    To get all separation angles for a mosaic field
    and simply use the median - this is sufficent
    for the phase referencing table

    NOTE - in comparing with methods in "imageparams_base.py"
    there is a much longer loop to get all positions, the 
    phase centre, then the differences of all positions with 
    the phase centre...which is also noted there as a bit crude
    
    """

    cme = casa_tools.measures
    # get the field object here for the field name
    fld_from_name = msin.get_fields(name=fieldname)
    cal_seps = []
    cal_unit = []
    for fldu in fld_from_name:
        if not eph_field:
            # easy just to so all the time but technically should be the same?
            refdir = cme.getref(fldu.mdirection)

            if refdir == 'B1950' or refdir == 'J2000':
                main_intent_dir = cme.measure(fldu.mdirection, 'ICRS') # this converts
            elif refdir == 'ICRS':
                main_intent_dir = fldu.mdirection # dont need to conver ICRS already and cme takes ages
            else:
                main_intent_dir = fldu.mdirection # dont convert, it is what it is
        else:  # is a mosaic of an ephemeris 
            LOG.info('Is an ephemeris mosaic - using source direction')
            refdir = cme.getref(fldu.source.direction)
            
            # calcalte the positons
            if refdir == 'B1950' or refdir == 'J2000':
                main_intent_dir = cme.measure(fldu.source.direction, 'ICRS') # this converts
            elif refdir == 'ICRS':
                main_intent_dir = fldu.source.direction # dont need to conver ICRS already and cme takes ages
            else:
                main_intent_dir = fldu.source.direction # dont convert, it is what it is
                    
        cal_sep = cme.separation(main_intent_dir, phasedir)  # measures dict with a 'value' and 'unit' (deg)
        cal_seps.append(cal_sep['value'])
        cal_unit.append(cal_sep['unit'])

    unit_use = np.unique(cal_unit) # should all be the same, could use [0] also
    if len(unit_use) > 1:
        LOG.warn('There is more than one unit used for the separation of fields')
        # we don't want to give anything back
        med_sepangle={'unit':'n/a', 'value':'n/a'}  # is there a better way to deal with this? 
       
    else:
        cal_sep_use = np.median(cal_seps)
        med_sepangle={'unit':unit_use[0], 'value':cal_sep_use}

    return med_sepangle


## PIPE-65 required the moving of this code from a
## static function associated only with spwphaseup
## to a common function 

def derive_phase_to_target_check_mapping(ms: MeasurementSet) -> Dict[str, Set]:
    """
    Derive mapping between PHASE calibrator fields (by name) and
    corresponding fields (by name) with TARGET / CHECK intent that these
    PHASE calibrators should calibrate.

    PIPE-1154: This heuristic is intended for ALMA observing, and assumes
    that the first scan of a TARGET / CHECK field is always preceded by a
    scan of the corresponding PHASE calibrator. This method further assumes
    that scan IDs increase sequentially with observing time.

    Args:
        ms: MeasurementSet to derive mapping for.

    Returns:
        Dictionary of PHASE field names (key) and set of names of
        corresponding TARGET/CHECK fields (value).
    """
    # Get the PHASE field names.
    phase_fields = [f.name for f in ms.get_fields(intent='PHASE')]

    # Initialize the mapping for each PHASE calibrator field.
    mapping = {f: set() for f in phase_fields}

    # Get IDs of PHASE intent scans.
    phase_scan_ids = [s.id for s in ms.get_scans(scan_intent='PHASE')]

    for intent in ['CHECK', 'TARGET']:
        # Get field names for current intent.
        fields = [f.name for f in ms.get_fields(intent=intent)]

        for field in fields:
            # Get ID of first scan for current field with current intent.
            first_scan_id = ms.get_scans(field=field, scan_intent=intent)[0].id

            # PIPE-1154: in standard ALMA observing, each first scan of a
            # field with TARGET or CHECK intent should be preceded by a
            # scan of its corresponding PHASE calibrator.
            # Identify PHASE intent scans that preceded the first scan.
            preceding_phase_scan_ids = [i for i in phase_scan_ids if i < first_scan_id]
            if preceding_phase_scan_ids:
                # Pick nearest in time PHASE intent scan as the match, and
                # identify name of corresponding field.
                matching_phase_scan_id = max(preceding_phase_scan_ids)
            else:
                # Identify PHASE intent scans that followed the first scan.
                following_phase_scan_ids = [i for i in phase_scan_ids if i > first_scan_id]
                if following_phase_scan_ids:
                    # As a fall-back, pick nearest in time PHASE intent
                    # scan after first field scan, but raise warning.
                    matching_phase_scan_id = min(following_phase_scan_ids)
                    LOG.warning(f"{ms.basename}: no PHASE scans found prior to the first scan for field {field}"
                                f" ({intent}), will match nearest PHASE scan that was taken after.")
                else:
                    matching_phase_scan_id = None
                    LOG.warning(f"{ms.basename}: no PHASE scans found prior or after first scan for field {field}"
                                f" ({intent}).")

            # If a matching PHASE scan was found, then update mapping to
            # link the corresponding PHASE field to current field.
            if matching_phase_scan_id:
                matching_phase_field = [f.name for f in ms.get_scans(scan_id=matching_phase_scan_id)[0].fields][0]
                mapping[matching_phase_field].add(field)

    return mapping
