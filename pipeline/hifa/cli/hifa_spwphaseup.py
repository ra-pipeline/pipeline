import sys

from casatasks import casalog

import pipeline.h.cli.utils as utils


def hifa_spwphaseup(vis=None, caltable=None, field=None, intent=None, spw=None, hm_spwmapmode=None, maxnarrowbw=None,
                    minfracmaxbw=None, samebb=None, phasesnr=None, bwedgefrac=None, hm_nantennas=None,
                    maxfracflagged=None, combine=None, refant=None, minblperant=None, minsnr=None,
                    unregister_existing=None, pipelinemode=None, dryrun=None, acceptresults=None):

    """
    hifa_spwphaseup ---- Compute phase calibration spw map and per spw phase offsets

    
    The spw map for phase calibration is computed. Phase offsets as a function of
    spectral window are computed using high signal to noise calibration observations.
    
    Previous calibrations are applied on the fly.
    
    hifa_spwphaseup performs two functions:
    
    o determines the spectral window mapping or combination mode, for each phase and
    check source, to use when solving for phase as a function of time (gfluxscale
    and timegaincal), and when applying those solutions to targets.
    
    o computes the per spectral window phase offset table that will be applied to the
    data to remove mean phase differences between the spectral windows
    
    If hm_spwmapmode = 'auto' the spectral window map is computed for each spectralSpec
    and each source with phase or check intent, using the following algorithm:
    
    o estimate the per spectral window (spw) per scan signal to noise ratio for each
    phase and check source based on catalog flux densities, Tsys, number of
    antennas, and integration scan time
    
    o if the signal to noise of all spws is greater than 'phasesnr', then
    hm_spwmapmode='default' mapping is used in which each spw is used
    to calibrate itself.
    
    o if the signal to noise of only some spws are greater than the value of
    'phasesnr', then each lower-SNR spw is mapped to the highest SNR
    one in the same spectralSpec
    
    o if all spws have low SNR, or SNR cannot be computed for any reason,
    for example there is no flux information, then hm_spwmapmode='combine'
    
    
    If hm_spwmapmode = 'combine', hifa_spwphaseup maps all the science windows
    to a single science spectral window. For example if the list of science
    spectral windows is [9, 11, 13, 15] then all the science spectral windows
    in the data will be combined and mapped to the science window 9 in the
    combined phase vs time calibration table.
    
    If hm_spwmapmode = 'simple', a mapping from narrow science to wider science
    spectral windows is computed using the following algorithm:
    
    o construct a list of the bandwidths of all the science spectral windows
    o determine the maximum bandwidth in this list maxbandwidth
    o for each science spectral window  with bandwidth less than maxbandwidth
    o construct a list of spectral windows with bandwidths greater than
    minfracmaxbw * maxbandwidth
    o select the spectral window in this list whose band center most closely
    matches the band center of the narrow spectral window
    o preferentially match within the same baseband if samebb is True
    
    If hm_spwmapmode = 'default' the spw mapping is assumed to be one to one.
    
    Phase offsets per spectral window are determined by computing a phase only gain
    calibration on the selected data, normally the high signal to noise bandpass
    calibrator observations, using the solution interval 'inf'.
    
    At the end of the task the spectral window map and the phase offset calibration
    table in the pipeline are stored in the context for use by later tasks.
    
    Finally, the SNR of the calibration solutions are inspected and if the median value
    on a per-spw basis does not reach specific thresholds, then issue a warning and reduced
    QA score, with thresholds at phasesnr*0.75 (blue), *0.5 (yellow) and *0.33 (red).
    
    
    Output
    
    results -- If pipeline mode is 'getinputs' then None is returned. Otherwise
    the results object for the pipeline task is returned.

    --------- parameter descriptions ---------------------------------------------

    vis                 The list of input MeasurementSets. Defaults to the list of
                        MeasurementSets specified in the pipeline context.
                        
                        example: vis=['M82A.ms', 'M82B.ms']
    caltable            The list of output calibration tables. Defaults to the standard
                        pipeline naming convention.
                        
                        example: caltable=['M82.gcal', 'M82B.gcal']
    field               The list of field names or field ids for which phase offset solutions
                        are to be computed. Defaults to all fields with the default intent.
                        
                        example: field='3C279', field='3C279, M82'
    intent              A string containing a comma delimited list of intents against
                        which the selected fields are matched. Defaults to the BANDPASS
                        observations.
                        
                        example: intent='PHASE'
    spw                 The list of spectral windows and channels for which gain solutions are
                        computed. Defaults to all the science spectral windows.
                        
                        example: spw='13,15'
    hm_spwmapmode       The spectral window mapping mode. The options are: 'auto',
                        'combine', 'simple', and 'default'. In 'auto' mode hifa_spwphaseup
                        estimates the SNR of the phase calibrator observations and uses these
                        estimates to choose between 'combine' mode (low SNR) and 'default' mode
                        (high SNR). In combine mode all spectral windows are combined and mapped to
                        one spectral window. In 'simple' mode narrow spectral windows are mapped to
                        wider ones using an algorithm defined by 'maxnarrowbw', 'minfracmaxbw', and
                        'samebb'. In 'default' mode the spectral window map defaults to the
                        standard one to one mapping.
                        
                        example: hm_spwmapmode='combine'
    maxnarrowbw         The maximum bandwidth defining narrow spectral windows. Values
                        must be in CASA compatible frequency units.
                        
                        example: maxnarrowbw=''
    minfracmaxbw        The minimum fraction of the maximum bandwidth in the set of
                        spws to use for matching.
                        
                        example: minfracmaxbw=0.75
    samebb              Match within the same baseband if possible.
                        
                        example: samebb=False
    phasesnr            The required gaincal solution signal to noise.
                        
                        example: phaseupsnr=20.0
    bwedgefrac          The fraction of the bandwidth edges that is flagged.
                        
                        example: bwedgefrac=0.0
    hm_nantennas        The heuristics for determines the number of antennas to use
                        in the signal to noise estimate. The options are 'all' and 'unflagged'.
                        The 'unflagged' options is not currently supported.
                        
                        example: hm_nantennas='unflagged'
    maxfracflagged      The maximum fraction of an antenna that can be flagged
                        before it is excluded from the signal to noise estimate.
                        
                        example: maxfracflagged=0.80
    combine             Data axes to combine for solving. Options are '', 'scan', 'spw',
                        'field' or any comma-separated combination.
                        
                        example: combine=''
    refant              Reference antenna name(s) in priority order. Defaults to most recent
                        values set in the pipeline context.  If no reference antenna is defined in
                        the pipeline context the CASA defaults are used.
                        
                        example: refant='DV01', refant='DV05,DV07'
    minblperant         Minimum number of baselines required per antenna for each solve.
                        Antennas with fewer baselines are excluded from solutions.
                        
                        example: minblperant=2
    minsnr              Solutions below this SNR are rejected.
    unregister_existing Unregister previous spwphaseup calibrations from the pipeline context
                        before registering the new calibrations from this task.
    pipelinemode        The pipeline operating mode. In 'automatic' mode the pipeline
                        determines the values of all context defined pipeline inputs automatically.
                        In interactive mode the user can set the pipeline context defined
                        parameters manually.  In 'getinputs' mode the user can check the settings
                        of all pipeline parameters without running the task.
    dryrun              Run the commands (True) or generate the commands to be run but
                        do not execute (False).
    acceptresults       Add the results of the task to the pipeline context (True) or
                        reject them (False).

    --------- examples -----------------------------------------------------------

    
    Examples
    
    1. Compute the default spectral window map and the per spectral window phase
    offsets:
    
    hifa_spwphaseup()
    
    2. Compute the default spectral window map and the per spectral window phase
    offsets set the spectral window mapping mode to 'simple':
    
    hifa_spwphaseup(hm_spwmapmode='simple')


    """


    ##########################################################################
    #                                                                        #
    #  CASA task interface boilerplate code starts here. No edits should be  #
    #  needed beyond this point.                                             #
    #                                                                        #
    ##########################################################################

    # create a dictionary containing all the arguments given in the
    # constructor
    all_inputs = vars()

    # get the name of this function for the weblog, eg. 'hif_flagdata'
    task_name = sys._getframe().f_code.co_name

    # get the context on which this task operates
    context = utils.get_context()

    # execute the task
    results = utils.execute_task(context, task_name, all_inputs)

    return results
