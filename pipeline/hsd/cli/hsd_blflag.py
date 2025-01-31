'''
Created on 2013/06/23

@author: kana
'''
import sys

import pipeline.h.cli.utils as utils

# docstring and type hints: inherits from hsd.tasks.baselineflag.baselineflag.SDBLFlagInputs.__init__
@utils.cli_wrapper
def hsd_blflag(iteration=None, edge=None, flag_tsys=None, tsys_thresh=None,
                 flag_prfre=None, prfre_thresh=None,
                 flag_pofre=None, pofre_thresh=None,
                 flag_prfr=None, prfr_thresh=None,
                 flag_pofr=None, pofr_thresh=None,
                 flag_prfrm=None, prfrm_thresh=None, prfrm_nmean=None,
                 flag_pofrm=None, pofrm_thresh=None, pofrm_nmean=None,
                 plotflag=None, parallel=None,
                 infiles=None, antenna=None,
                 field=None, spw=None, pol=None):

    """Flag spectra based on predefined criteria of single dish pipeline.

    Data are flagged based on several flagging rules. Available rules are:
    expected rms, calculated rms, and running mean of both pre-fit and
    post-fit spectra. Tsys flagging is also available.

    In addition, the heuristics script creates many plots for each stage.
    Those plots are included in the weblog.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. flagging with all rules

        >>> hsd_blflag()

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
