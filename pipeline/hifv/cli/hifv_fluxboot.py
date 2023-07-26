import sys

from casatasks import casalog

import pipeline.h.cli.utils as utils


def hifv_fluxboot(vis=None, caltable=None, fitorder=None, dryrun=None, acceptresults=None,
                   refantignore=None):

    """
    hifv_fluxboot ---- Fluxboot

    Determine flux density bootstrapping for gain calibrators relative to flux calibrator.

    --------- parameter descriptions ---------------------------------------------

    vis           List of visibility data files. These may be ASDMs, tar files of ASDMs,
                  MSes, or tar files of MSes, If ASDM files are specified, they will be
                  converted  to MS format.
                  example: vis=['X227.ms', 'asdms.tar.gz']
    caltable      String name of the flagged caltable
    fitorder      Polynomial order of the spectral fitting for valid flux densities
                  with multiple spws.  The default value of -1 means that the heuristics determine the fit order based on
                  fractional bandwidth and receiver bands present in the observation.
                  An override value of 1,2,3 or 4 may be specified by the user.
                  Spectral index (1) and, if applicable, curvature (2) are reported in the weblog.
                  If no determination can be made by the heuristics, a fitorder of 1 will be used.
    dryrun        Run the commands (True) or generate the commands to be run but
                  do not execute (False).  This is a pipeline task execution mode.
    acceptresults Add the results of the task to the pipeline context (True) or
                  reject them (False).  This is a pipeline task execution mode.
    refantignore  String list of antennas to ignore
                  Example:  refantignore='ea02,ea03'

    --------- examples -----------------------------------------------------------

    
    Output:
    
    results -- The results object for the pipeline task is returned.
    
    
    Examples
    
    1. VLA CASA pipeline flux density bootstrapping.
    
    hifv_fluxboot()


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
