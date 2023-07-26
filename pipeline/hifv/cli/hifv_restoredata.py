import sys

from casatasks import casalog

import pipeline.h.cli.utils as utils


def hifv_restoredata(vis=None, session=None, products_dir=None, copytoraw=None, rawdata_dir=None, lazy=None,
                     bdfflags=None, ocorr_mode=None, gainmap=None, asis=None, dryrun=None,
                     acceptresults=None):

    """
    hifv_restoredata ---- Restore flagged and calibration interferometry data from a pipeline run

    The hifv_restoredata restores flagged and calibrated data from archived
    ASDMs and pipeline flagging and calibration data products. Pending archive
    retrieval support hifv_restoredata assumes that the required products
    are available in the rawdata_dir in the format produced by the
    hifv_exportdata task.
    
    hifv_restoredata assumes that the following entities are available in the raw
    data directory
    
    o the ASDMs to be restored
    o for each ASDM in the input list
    o a compressed tar file of the final flagversions file, e.g.
    uid___A002_X30a93d_X43e.ms.flagversions.tar.gz
    o a text file containing the applycal instructions, e.g.
    uid___A002_X30a93d_X43e.ms.calapply.txt
    o a compressed tar file containing the caltables for the parent session,
    e.g. uid___A001_X74_X29.session_3.caltables.tar.gz
    
    hifv_restoredata performs the following operations
    
    o imports the ASDM(s))
    o removes the default MS.flagversions directory created by the filler
    o restores the final MS.flagversions directory stored by the pipeline
    o restores the final set of pipeline flags to the MS
    o restores the final calibration state of the MS
    o restores the final calibration tables for each MS
    o applies the calibration tables to each MS
    
    Output:
    
    results -- The results object for the pipeline task is returned.

    --------- parameter descriptions ---------------------------------------------

    vis           List of visibility data files. These may be ASDMs, tar files of ASDMs,
                  MSes, or tar files of MSes, If ASDM files are specified, they will be
                  converted  to MS format.
                  example: vis=['X227.ms', 'asdms.tar.gz']
    session       List of sessions one per visibility file.
                  Example: session=['session_3']
    products_dir  Name of the data products directory to copy calibration
                  products from. The parameter is effective only when copytoraw = True
                  When copytoraw = False, calibration products in rawdata_dir will be used.
                  example: products_dir='myproductspath'
    copytoraw     Copy calibration and flagging tables from products_dir to
                  rawdata_dir directory.
                  Example: copytoraw=False.
    rawdata_dir   The rawdata directory.
                  Example: rawdata_dir='myrawdatapath'
    lazy          Use the lazy filler option.
    bdfflags      Set the BDF flags.
    ocorr_mode    Correlation import mode
    gainmap       If True, map gainfields to a particular list of scans when
                  applying calibration tables.
    asis          List of tables to import asis.
    dryrun        Run the commands (True) or generate the commands to be run but
                  do not execute (False).  This is a pipeline task execution mode.
    acceptresults Add the results of the task to the pipeline context (True) or
                  reject them (False).  This is a pipeline task execution mode.

    --------- examples -----------------------------------------------------------

    
    Examples
    
    1. Restore the pipeline results for a single ASDM in a single session
    
    hifv_restoredata (vis=['myVLAsdm'], session=['session_1'], ocorr_mode='ca')


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
