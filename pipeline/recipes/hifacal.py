# General imports

import os
import sys
import traceback
import inspect

# Pipeline imports
from pipeline.infrastructure import casa_tools

IMPORT_ONLY = 'Import only'


# Run the procedure
def hifacal(vislist, importonly=True, dbservice=True, pipelinemode='automatic',
            interactive=True):

    echo_to_screen = interactive
    casa_tools.post_to_log("Beginning ALMA calibration pipeline run ...")

    try:
        # Initialize the pipeline
        h_init()

        # Load the data
        hifa_importdata(vis=vislist, dbservice=dbservice, pipelinemode=pipelinemode)
        if importonly:
            raise Exception(IMPORT_ONLY)

        # Flag known bad data
        hifa_flagdata(pipelinemode=pipelinemode)

        # Flag lines in solar system calibrators and compute the default
        # reference spectral window map.
        hifa_fluxcalflag(pipelinemode=pipelinemode)

        # Flag bad channels in the raw data
        hif_rawflagchans(pipelinemode=pipelinemode)

        # Compute the prioritized lists of reference antennas
        hif_refant(pipelinemode=pipelinemode)

        # Compute the system temperature calibration
        h_tsyscal(pipelinemode=pipelinemode)

        # Flag system temperature calibration
        hifa_tsysflag(pipelinemode=pipelinemode)

        # Flag system temperature calibration
        hifa_antpos(pipelinemode=pipelinemode)

        # Compute the WVR calibration, flag and interpolate over bad antennas
        hifa_wvrgcalflag(pipelinemode=pipelinemode)

        # Flag antennas with low gain
        hif_lowgainflag(pipelinemode=pipelinemode)

        # Set the flux calibrator model
        hif_setmodels(pipelinemode=pipelinemode)

        # Derive and temporarily apply a preliminary bandpass calibration,
        # and flag outliers in corrected - model amplitudes for bandpass
        # calibrator.
        hifa_bandpassflag(pipelinemode=pipelinemode)

        # Compute the bandpass calibration.
        hifa_bandpass(pipelinemode=pipelinemode)

        # Compute phase calibration spw map and per spw phase offsets.
        hifa_spwphaseup(pipelinemode=pipelinemode)

        # Derive the flux density scale from standard calibrators, and flag
        # outliers in corrected - model amplitudes for flux and phase
        # calibrators.
        hifa_gfluxscaleflag(pipelinemode=pipelinemode)

        # Determine flux values for the bandpass and gain calibrators
        # assuming point sources and set their model fluxes
        hifa_gfluxscale(pipelinemode=pipelinemode)

        # Compute the time dependent gain calibration
        hifa_timegaincal(pipelinemode=pipelinemode)

        # Flag ultrahigh calibrated target data
        hifa_targetflag(pipelinemode=pipelinemode)

        # Apply the calibrations
        hif_applycal(pipelinemode=pipelinemode)

        # Make a list of expected point source calibrators to be cleaned
        hif_makeimlist(intent='PHASE,BANDPASS,AMPLITUDE', pipelinemode=pipelinemode)

        # Make clean images for the selected calibrators
        hif_makeimages(pipelinemode=pipelinemode)

        # Make a list of check source calibrators to be cleaned
        hif_makeimlist(intent='CHECK', per_eb=True, pipelinemode=pipelinemode)

        # Make clean images for the selected calibrators
        hif_makeimages(pipelinemode=pipelinemode)

        # Check imaging parameters against PI specified values
        hifa_imageprecheck(pipelinemode=pipelinemode)

        # Check product size limits and mitigate imaging parameters
        hif_checkproductsize(maxcubesize=40.0, maxcubelimit=60.0, maxproductsize=500.0)

        # Run renormalization and apply correction
        hifa_renorm(apply=True, atm_auto_exclude=True)

        # Export the data
        hifa_exportdata(pipelinemode=pipelinemode)

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
