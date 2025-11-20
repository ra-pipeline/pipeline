import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.spwphaseup.spwphaseup.SpwPhaseupInputs.__init__
@utils.cli_wrapper
def hifa_spwphaseup(vis=None, caltable=None, field=None, intent=None, spw=None, hm_spwmapmode=None, maxnarrowbw=None,
                    minfracmaxbw=None, samebb=None, phasesnr=None, intphasesnr=None, intphasesnrmin=None,
                    phaseupmaxsolint=None, bwedgefrac=None, hm_nantennas=None, maxfracflagged=None, combine=None,
                    refant=None, minblperant=None, minsnr=None, unregister_existing=None):
    """Compute phase calibration spw map and per spw phase offsets

    The spw map for phase calibration is computed. Phase offsets as a function of
    spectral window are computed using high signal-to-noise calibration observations.

    Previous calibrations are applied on the fly.

    hifa_spwphaseup performs two functions:

    - Determines the spectral window mapping or combination mode, gaintype and
      solint, for each independent bandpass, amplitude, diffgain, phase and check
      source, to use when solving the phaseup (phase as a function of time) in
      subsequent stages (mapping mode and gaintype in gfluxscaleflag, all
      parameters for gfluxscale and timegaincal), and when applying those solutions
      to targets.
    
    - Computes the per-spectral-window phase offset table that will be applied
      to the data to remove mean phase differences between the spectral windows.

    If ``hm_spwmapmode`` = 'auto', then the spectral window map is computed for
    each SpectralSpec and each calibrator source, using the following algorithm:

    - Estimate the per-spectral-window (spw) signal-to-noise ratio based on
      catalog flux densities, Tsys, number of antennas, and integration scan time.
      These estimates are shown in the weblog.
    
    - Compute the per-spw signal-to-noise for each above mentioned intent based
      on an temporary phaseup gain calibration using solint ``inf`` for the PHASE
      and CHECK intents, and ``int`` otherwise. These computed signal-to-noise
      values override the use of the estimated values unless none are found.

    - If SNR calculation fails, then subsequent heuristics are skipped, warnings
      printed, and mapping falls back to narrow-to-wide.
    
    - If the signal-to-noise of all spws is greater than ``phasesnr`` for a 
      PHASE or CHECK intent, or greater than ``intphasesnr'' for the other 
      intents, then if SNR is high enough to keep solint='int', then
      no mapping is used (each spw is used to calibrate itself).  If the calculated
      solint is >'int' then mapping and combine are attempted, to favor a
      short solint over keeping the spws independent.

    - If the signal-to-noise of only some spws are greater than the value of
      ``phasesnr`` for the PHASE or CHECK intent, or ``intphasesnr`` for the 
      other intents, then each lower-SNR spw is mapped to the highest SNR spw
      in the same SpectralSpec.
    
    - If all spws have low SNR (or all spws in a given SpectraSpec for
      multi-SpectralSpec observations), then spws are combined.

    - The time solint is calculated and stored for phaseup in subsequent stages. 
      If ``hm_spwmapmode`` is not 'combine' then there is at least one high
      signal-to-noise spw, then by definition that has a solint = 'int'. For
      ``hm_spwmapmode`` = 'combine', the computed signal-to-noise is used 
      in conjunction with ``phasesnr'' for the phase and check intents, or 
      ``intphasesnr'' for the other intents.  First the gaintype is changed
      from G to T (combine polarization) and thereafter solint is increased
      from 'int' up to the limits of 1/2 scan for the phase or check intent, or
      to the input ``maxphaseupsolint`` for the other intents

    - If ``hm_spwmapmode'' is combine and no SNRs are found, the PHASE and CHECK
      intents will default to a solint of 1/4 scan.

    - If the intent is AMPLITUDE, and gaintype was changed from 'G' to 'T',
      the signal-to-noise required to be met before increasing solint > 'int' 
      is reduced to ``intphasesnrmin``

    If ``hm_spwmapmode`` = 'combine', hifa_spwphaseup maps all the science windows
    to a single science spectral window. For example, if the list of science
    spectral windows is [9, 11, 13, 15] then all the science spectral windows
    in the data will be combined and mapped to the science window 9 in the
    combined phase vs time calibration table.

    If ``hm_spwmapmode`` = 'simple', a mapping from narrow science to wider
    science spectral windows is computed using the following algorithm:

    - Construct a list of the bandwidths of all the science spectral windows.

    - Determine the maximum bandwidth in this list as 'maxbandwidth'

    - For each science spectral window with bandwidth less than 'maxbandwidth'
      construct a list of spectral windows with bandwidths greater than
      ``minfracmaxbw`` * 'maxbandwidth', then select the spectral window in this
      list whose band center most closely matches the band center of the narrow
      spectral window, and preferentially match within the same baseband if
      ``samebb`` = True.

    If ``hm_spwmapmode`` = 'default' the spw mapping is assumed to be one to one.



    After determining the combine and mapping parameters and time solints, 
    phase offsets per spectral window are determined by computing a phase only gain
    calibration on the selected data, normally the high signal-to-noise bandpass
    calibrator observations, using the solution interval 'inf'.

    At the end of the task the spectral window map, solint and gaintype along 
    with the phase offset calibration table(s) in the pipeline are stored in
    the context for use by later tasks.
    
    Finally, the SNR of the calibration solutions are inspected and if the median
    value on a per-spw basis does not reach specific thresholds, a warning is
    issued with a reduced QA score.  For PHASE intent, blue, yellow, and red QA
    result if the achieved SNR is less than 0.75, 0.5, and 0.33 times ``phasesnr``,
    respectively.  For BANDPASS, AMPLITUDE, and DIFFGAIN intent, QA messages are
    based on 0.75, 0.5, and 0.33 times ``intphasesnr`` (unless ``intphasesnrmin``
    was used for BANDPASS or AMPLITUDE).  Finally, for CHECK intent the QA score
    is always blue, but scales depending on achieved SNR relative to ``phasesnr``.


    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Compute the default spectral window map and the per spectral window phase
        offsets:

        >>> hifa_spwphaseup()

        2. Compute the default spectral window map and the per spectral window phase
        offsets set the spectral window mapping mode to 'combine':

        >>> hifa_spwphaseup(hm_spwmapmode='combine')

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
