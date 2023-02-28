import sys

from casatasks import casalog

import pipeline.h.cli.utils as utils


def hifa_gaincalsnr(vis=None, field=None, intent=None, spw=None, phasesnr=None, bwedgefrac=None, hm_nantennas=None,
                    maxfracflagged=None, pipelinemode=None, dryrun=None, acceptresults=None):

    """
    hifa_gaincalsnr ---- Compute gaincal signal to noise ratios per spw

    
    The gaincal solution signal to noise is determined as follows:
    
    o For each data set the list of source(s) to use for the per scan gaincal
    solution signal to noise estimation is compiled based on the values of the
    field, intent, and spw parameters.
    
    o Source fluxes are determined for each spw and source combination.
    o Fluxes in Jy are derived from the pipeline context.
    o Pipeline context fluxes are derived from the online flux calibrator
    catalog, the ASDM, or the user via the flux.csv file.
    o If no fluxes are available the task terminates.
    
    o Atmospheric calibration and observations scans are determined for each spw
    and source combination.
    o If intent is set to 'PHASE' are there are no atmospheric scans
    associated with the 'PHASE' calibrator, 'TARGET' atmospheric scans
    will be used instead.
    o If atmospheric scans cannot be associated with any of the spw and
    source combinations the task terminates.
    
    o Science spws are mapped to atmospheric spws for each science spw and
    source combinations.
    o If mappings cannot be determined for any of the spws the task
    terminates.
    
    o The median Tsys value for each atmospheric spw and source combination is
    determined from the SYSCAL table. Medians are computed first by channel,
    then by antenna, in order to reduce sensitivity to deviant values.
    
    o The science spw parameters, exposure time(s), and integration time(s) are
    determined.
    
    o The per scan sensitivity and signal to noise estimates are computed per
    science spectral window. Nominal Tsys and sensitivity values per receiver
    band provide by the ALMA project are used for this estimate.
    
    o The QA score is based on how many signal to noise estimates greater than the
    requested signal to noise ratio can be computed.
    
    
    Output
    
    results -- If pipeline mode is 'getinputs' then None is returned. Otherwise
    the results object for the pipeline task is returned.

    --------- parameter descriptions ---------------------------------------------

    vis            The list of input MeasurementSets. Defaults to the list of
                   MeasurementSets specified in the pipeline context.
                   
                   example: vis=['M82A.ms', 'M82B.ms']
    field          The list of field names of sources to be used for signal to noise
                   estimation. Defaults to all fields with the standard intent.
                   
                   example: field='3C279'
    intent         A string containing a comma delimited list of intents against which
                   the selected fields are matched. Defaults to 'PHASE'.
                   
                   example: intent='BANDPASS'
    spw            The list of spectral windows and channels for which gain solutions are
                   computed. Defaults to all the science spectral windows for which there are
                   both 'intent' and TARGET intents.
                   
                   example: spw='13,15'
    phasesnr       The required gaincal solution signal to noise.
                   
                   example: phasesnr=20.0
    bwedgefrac     The fraction of the bandwidth edges that is flagged.
                   
                   example: bwedgefrac=0.0
    hm_nantennas   The heuristics for determines the number of antennas to use
                   in the signal to noise estimate. The options are 'all' and 'unflagged'.
                   The 'unflagged' options is not currently supported.
                   
                   example: hm_nantennas='unflagged'
    maxfracflagged The maximum fraction of an antenna that can be flagged
                   before it is excluded from the signal to noise estimate.
                   
                   example: maxfracflagged=0.80
    pipelinemode   The pipeline operating mode. In 'automatic' mode the pipeline
                   determines the values of all context defined pipeline inputs
                   automatically. In interactive mode the user can set the pipeline
                   context defined parameters manually. In 'getinputs' mode the user
                   can check the settings of all pipeline parameters without running
                   the task.
    dryrun         Run the commands (True) or generate the commands to be run but
                   do not execute (False).
    acceptresults  ults of the task to the pipeline context (True) or
                   reject them (False).

    --------- examples -----------------------------------------------------------

    
    1. Estimate the per scan gaincal solution sensitivities and signal to noise
    ratios for all the science spectral windows:
    
    hifa_gaincalsnr()


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
