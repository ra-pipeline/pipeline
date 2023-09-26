import sys

import pipeline.h.cli.utils as utils


@utils.cli_wrapper
def hifa_renorm(vis=None, apply=None, threshold=None, correctATM=None, spw=None,
                excludechan=None, atm_auto_exclude=None, bwthreshspw=None,
                dryrun=None, acceptresults=None, parallel=None):

    """
    hifa_renorm ---- Base renorm task

    --------- parameter descriptions ---------------------------------------------

    vis              List of input visibility data

    apply            Apply renormalization correction

    threshold        Apply correction if max correction is above threshold and apply=True. 
                     Default is 1.02 (i.e. 2%)

    correctATM       Use the ATM model transmission profiles to try and correct
                     for any ATM residual features that get into the scaling spectra

    spw              The list of real (not virtual - i.e. the actual spwIDs in the MS) spectral
                     windows to evaluate.
                     Set to spw='' by default, which means the task will select all relevant
                     (science FDM) spectral windows.
                     Note that for data with multiple MSs, a list with the correct spectral window
                     selection for each MS can be provided.
                     Examples: spw="11,13,15,17"
                               spw=["11,13,15,17", "5,7,11,13"]
    
    excludechan      Channels to exclude in either channel or frequency space (TOPO, GHz),
                     specifying the real (not virtual) spectral window per selection.
                     Note that for data with multiple MSs, a list of dictionaries with the
                     correct selection for each MS can be provided.
                     Examples: excludechan={'22':'100~150;800~850', '24':'100~200'}
                               excludechan={'22':'230.1GHz~230.2GHz'}
                               excludechan=[{'22':'100~150'}, {'15':'100~150'}]

    atm_auto_exclude Automatically find and exclude regions with atmospheric features.
                     Default is False

    bwthreshspw      bandwidth beyond which a SPW is split into chunks to fit separately.
                     The default value for all SPWs is 120e6, and this parameter allows one
                     to override it for specific SPWs, due to needing potentially various
                     'nsegments' when EBs have very different SPW bandwidths.
                     Example:  bwthreshspw={'16: 64e6, '22: 64e6}

    dryrun           Run the task (False) or display task command (True)

    acceptresults    Add the results into the pipeline context

    parallel         Execute using CASA HPC functionality, if available.

    --------- examples -----------------------------------------------------------

    


    """


    #                                                                        #
    #  CASA task interface boilerplate code starts here. No edits should be  #
    #  needed beyond this point.                                             #
    #                                                                        #

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
