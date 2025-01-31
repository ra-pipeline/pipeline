import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.restoredata.almarestoredata.ALMARestoreDataInputs.__init__
@utils.cli_wrapper
def hifa_restoredata(vis=None, session=None, products_dir=None, copytoraw=None, rawdata_dir=None, lazy=None,
                     bdfflags=None, ocorr_mode=None, asis=None):
    """Restore flagged and calibration interferometry data from a pipeline run

    The hifa_restoredata task restores flagged and calibrated MeasurementSets
    from archived ASDMs and pipeline flagging and calibration data products.

    hifa_restoredata assumes that the ASDMs to be restored are present in the
    directory specified by the ``rawdata_dir`` (default: '../rawdata').

    By default (``copytoraw`` = True), hifa_restoredata assumes that for each
    ASDM in the input list, the corresponding pipeline flagging and calibration
    data products (in the format produced by the hifa_exportdata task) are
    present in the directory specified by ``products_dir`` (default: '../products').
    At the start of the task, these products are copied from the ``products_dir``
    to the ``rawdata_dir``.

    If ``copytoraw`` = False, hifa_restoredata assumes that these products are
    to be found in ``rawdata_dir`` along with the ASDMs.

    The expected flagging and calibration products (for each ASDM) include:

      - a compressed tar file of the final flagversions file, e.g.
        uid___A002_X30a93d_X43e.ms.flagversions.tar.gz

      - a text file containing the applycal instructions, e.g.
        uid___A002_X30a93d_X43e.ms.calapply.txt

      - a compressed tar file containing the caltables for the parent session,
        e.g. uid___A001_X74_X29.session_3.caltables.tar.gz

    hifa_restoredata performs the following operations:

    - imports the ASDM(s)
    - removes the default MS.flagversions directory created by the filler
    - restores the final MS.flagversions directory stored by the pipeline
    - restores the final set of pipeline flags to the MS
    - restores the final calibration state of the MS
    - restores the final calibration tables for each MS
    - applies the calibration tables to each MS

    When importing the ASDM and converting it to a Measurement Set (MS), if the
    output MS already exists in the output directory, then the importasdm
    conversion step is skipped, and instead the existing MS will be imported.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Restore the pipeline results for a single ASDM in a single session:

        >>> hifa_restoredata(vis=['uid___A002_X30a93d_X43e'], session=['session_1'], ocorr_mode='ca')

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
