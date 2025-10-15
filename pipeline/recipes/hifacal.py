# General imports

import os
import sys
import traceback
import inspect
from prefect import flow

# Pipeline imports
import pipeline
from pipeline.infrastructure import casa_tools

# Make pipeline tasks available in local name space
pipeline.initcli(locals())

IMPORT_ONLY = 'Import only'


# Run the procedure
@flow
def hifacal(vislist, importonly=True, dbservice=True, interactive=True):

    echo_to_screen = interactive
    casa_tools.post_to_log("Beginning ALMA calibration pipeline run ...")

    try:
        # Initialize the pipeline
        results = h_init()

        # Load the data
        results = hifa_importdata(results, vis=vislist, dbservice=dbservice)
        if importonly:
            raise Exception(IMPORT_ONLY)

        # Flag known bad data
        results = hifa_flagdata(results)

        # Flag lines in solar system calibrators and compute the default
        # reference spectral window map.
        results = hifa_fluxcalflag(results)

        # Flag bad channels in the raw data
        results = hif_rawflagchans(results)

        # Compute the prioritized lists of reference antennas
        results = hif_refant(results)

        # Compute the system temperature calibration
        results = h_tsyscal(results)

        # Flag system temperature calibration
        results = hifa_tsysflag(results)

        # flag line contamination
        results = hifa_tsysflagcontamination(results)

        # Flag system temperature calibration
        results = hifa_antpos(results)

        # Compute the WVR calibration, flag and interpolate over bad antennas
        results = hifa_wvrgcalflag(results)

        # Flag antennas with low gain
        results = hif_lowgainflag(results)

        # Set the flux calibrator model
        results = hif_setmodels(results)

        # Derive and temporarily apply a preliminary bandpass calibration,
        # and flag outliers in corrected - model amplitudes for bandpass
        # calibrator.
        results = hifa_bandpassflag(results)

        # Compute the bandpass calibration.
        results = hifa_bandpass(results)

        # Compute phase calibration spw map and per spw phase offsets.
        results = hifa_spwphaseup(results)

        # Derive the flux density scale from standard calibrators, and flag
        # outliers in corrected - model amplitudes for flux and phase
        # calibrators.
        results = hifa_gfluxscaleflag(results)

        # Determine flux values for the bandpass and gain calibrators
        # assuming point sources and set their model fluxes
        results = hifa_gfluxscale(results)

        # Compute the time dependent gain calibration
        results = hifa_timegaincal(results)

        # Run renormalization
        results = hifa_renorm(results, createcaltable=True, atm_auto_exclude=True)

        # Flag ultrahigh calibrated target data
        results = hifa_targetflag(results)

        # Apply the calibrations
        results = hif_applycal(results)

        # Make a list of expected point source calibrators to be cleaned
        results = hif_makeimlist(results, intent='PHASE,BANDPASS,AMPLITUDE')

        # Make clean images for the selected calibrators
        results = hif_makeimages(results)

        # Make a list of check source calibrators to be cleaned
        results =  hif_makeimlist(results, intent='CHECK', per_eb=True)

        # Make clean images for the selected calibrators
        results = hif_makeimages(results)

        # Check imaging parameters against PI specified values
        results = hifa_imageprecheck(results)

        # Check product size limits and mitigate imaging parameters
        results = hif_checkproductsize(results, maxcubesize=40.0, maxcubelimit=60.0, maxproductsize=500.0)

        # Export the data
        results = hifa_exportdata(results)

    except Exception as e:
        if str(e) == IMPORT_ONLY:
            casa_tools.post_to_log("Exiting after import step ...", echo_to_screen=echo_to_screen)
        else:
            casa_tools.post_to_log("Error in procedure execution ...", echo_to_screen=echo_to_screen)
            errstr = traceback.format_exc()
            casa_tools.post_to_log(errstr, echo_to_screen=echo_to_screen)

    finally:

        # Save the results to the context
        h_save()

        casa_tools.post_to_log("Terminating procedure execution ...", echo_to_screen=echo_to_screen)

if __name__ == '__main__':
    hifacal('./uid___A002_X1181695_X1c6a4_8ant.ms', importonly=False)
