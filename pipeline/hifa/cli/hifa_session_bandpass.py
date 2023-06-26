import sys

from casatasks import casalog

import pipeline.h.cli.utils as utils


def hifa_session_bandpass(vis=None, caltable=None, field=None, intent=None, spw=None, antenna=None, hm_phaseup=None,
                          phaseupsolint=None, phaseupbw=None, phaseupsnr=None, phaseupnsols=None, hm_bandpass=None,
                          solint=None, maxchannels=None, evenbpints=None, bpsnr=None, minbpsnr=None, bpnsols=None,
                          hm_bandtype=None, combine=None, refant=None, solnorm=None, minblperant=None, minsnr=None,
                          degamp=None, degphase=None, pipelinemode=None, dryrun=None, acceptresults=None,
                          parallel=None):

    """
    hifa_session_bandpass ---- Compute bandpass calibration solutions (Experimental)

    
    (Experimental)
    
    Compute amplitude and phase as a function of frequency for each spectral
    window in each MeasurementSet.
    
    Previous calibration can be applied on the fly.
    
    hifa_session_bandpass computes a bandpass solution for every specified science
    spectral window. By default a 'phaseup' pre-calibration is performed
    and applied on the fly to the data, before the bandpass is computed.
    
    The hif_refant task may be used to precompute a prioritized list of
    reference antennas.
    
    
    Output
    
    results -- If pipeline mode is 'getinputs' then None is returned. Otherwise
    the results object for the pipeline task is returned.
    
    
    Issues
    
    The specified minsnr parameter is currently applied to the bandpass
    solution computation but not the 'phaseup' computation. Some noisy
    solutions in the phaseup may not be properly rejected.

    --------- parameter descriptions ---------------------------------------------

    vis           The list of input MeasurementSets. Defaults to the list of
                  MeasurementSets specified in the pipeline context.
                  
                  example: vis=['M51.ms']
    caltable      The list of output calibration tables. Defaults to the standard
                  pipeline naming convention.
                  
                  example: caltable=['M51.bcal']
    field         The list of field names or field ids for which bandpasses are
                  computed. Defaults to all fields.
                  
                  example: field='3C279', field='3C279, M82'
    intent        A string containing a comma delimited list of intents against
                  which the selected fields are matched. Defaults to all data
                  with bandpass intent.
                  
                  example: intent='*PHASE*'
    spw           The list of spectral windows and channels for which bandpasses are
                  computed. Defaults to all science spectral windows.
                  
                  example: spw='11,13,15,17'
    antenna       The selection of antennas for which bandpasses are computed. Defaults to all.
    hm_phaseup    The pre-bandpass solution phaseup gain heuristics. The options
                  are 'snr' (compute solution required to achieve the specified SNR),
                  'manual' (use manual solution parameters), and '' (none).
                  
                  example: hm_phaseup='manual'
    phaseupsolint The phase correction solution interval in CASA syntax.
                  Used when hm_phaseup='manual' or as a default if the hm_phaseup='snr'
                  heuristic computation fails.
                  
                  example: phaseupsolint='300s'
    phaseupbw     Bandwidth to be used for phaseup. Defaults to 500MHz.
                  Used when hm_phaseup='manual'.
                  
                  example: phaseupbw='' to use entire bandpass, phaseupbw='500MHz' to use
                                           central 500MHz
    phaseupsnr    The required SNR for the phaseup solution. Used only if
                  hm_phaseup='snr'.
                  
                  example: phaseupsnr=10.0
    phaseupnsols  The minimum number of phaseup gain solutions. Used only if
                  hm_phaseup='snr'.
                  
                  example: phaseupnsols=4
    hm_bandpass   The bandpass solution heuristics. The options are 'snr'
                  (compute the solution required to achieve the specified SNR),
                  'smoothed' (simple smoothing heuristics), and 'fixed' (use
                  the user defined parameters for all spws).
    solint        Time and channel solution intervals in CASA syntax.
                  default: 'inf' Used for hm_bandpass='fixed', and as a default
                  for the 'snr' and 'smoothed' options.
                  
                  default: 'inf,7.8125MHz'
                  example: solint='inf,10ch', solint='inf'
    maxchannels   The bandpass solution smoothing factor in channels. The
                  solution interval is bandwidth / 240. Set to 0 for no smoothing.
                  Used if hm_bandpass='smoothed".
                  
                  example: 0
    evenbpints    Force the per spw frequency solint to be evenly divisible
                  into the spw bandpass if hm_bandpass='snr'.
                  
                  example: evenbpints=False
    bpsnr         The required SNR for the bandpass solution. Used only if
                  hm_bandpass='snr'
                  
                  example: bpsnr=30.0
    minbpsnr      The minimum required SNR for the bandpass solution
                  when strong atmospheric lines exist in Tsys spectra.
                  Used only if hm_bandpass='snr'.
                  
                  example: minbpsnr=10.0
    bpnsols       The minimum number of bandpass solutions. Used only if
                  hm_bandpass='snr'.
    hm_bandtype   The type of bandpass. The options are 'channel' and
                  'polynomial' for CASA bandpass types = 'B' and 'BPOLY' respectively.
    combine       Data axes to combine for solving. Axes are '', 'scan', 'spw',
                  'field' or any comma-separated combination.
                  
                  example: combine='scan,field'
    refant        Reference antenna names. Defaults to the value(s) stored in the
                  pipeline context. If undefined in the pipeline context defaults to
                  the CASA reference antenna naming scheme.
                  
                  example: refant='DV01', refant='DV06,DV07'
    solnorm       Normalise the bandpass solutions.
    minblperant   Minimum number of baselines required per antenna for each solve
                  Antennas with fewer baselines are excluded from solutions. Used for
                  hm_bandtype='channel' only.
    minsnr        Solutions below this SNR are rejected. Used for hm_bandtype=
                  'channel' only.
    degamp        
    degphase      
    pipelinemode  The pipeline operating mode. In 'automatic' mode the pipeline
                  determines the values of all context defined pipeline inputs automatically.
                  In interactive mode the user can set the pipeline context defined
                  parameters manually. In 'getinputs' mode the user can check the settings of
                  all pipeline parameters without running the task.
    dryrun        Run the commands (True) or generate the commands to be run but
                  do not execute (False).
    acceptresults Add the results of the task to the pipeline context (True) or
                  reject them (False).
    parallel      Execute using CASA HPC functionality, if available.

    --------- examples -----------------------------------------------------------

    
    1. Compute a channel bandpass for all visibility files in the pipeline
    context using the CASA reference antenna determination scheme:
    
    hifa_session_bandpass()
    
    2. Same as the above but precompute a prioritized reference antenna list:
    
    hif_refant()
    hifa_session_bandpass()


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
