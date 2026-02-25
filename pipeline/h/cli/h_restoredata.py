from . import utils


# docstring and type hints: inherits from h.tasks.restoredata.restoredata.RestoreDataInputs.__init__
@utils.cli_wrapper
def h_restoredata(vis=None, session=None, products_dir=None, copytoraw=None, rawdata_dir=None, lazy=None, bdfflags=None,
                  ocorr_mode=None, asis=None):
    """Restore flags and calibration state from a pipeline run.

    The h_restoredata restores flagged and calibrated data from archived ASDMs and
    pipeline flagging and calibration data products. Pending archive retrieval
    support h_restoredata assumes that the required products are available in the
    rawdata_dir in the format produced by the h_exportdata task.

    h_restoredata assumes that the following entities are available in the
    rawdata_dir directory:

    - the ASDMs to be restored
    - for each ASDM in the input list:

        - a compressed tar file of the final flagversions file, e.g.,
          uid___A002_X30a93d_X43e.ms.flagversions.tar.gz
        - a text file containing the applycal instructions, e.g.,
          uid___A002_X30a93d_X43e.ms.calapply.txt
        - a compressed tar file containing the caltables for the parent
          session, e.g., uid___A001_X74_X29.session_3.caltables.tar.gz

    h_restore data performs the following operations:

    - imports the ASDM(s)
    - removes the default MS.flagversions directory created by the filler
    - restores the final MS.flagversions directory stored by the pipeline
    - restores the final set of pipeline flags to the MS
    - restores the final calibration state of the MS
    - restores the final calibration tables for each MS
    - applies the calibration tables to each MS

    When importing the ASDM and converting it to a MeasurementSet (MS), if the
    output MS already exists in the output directory, then the importasdm
    conversion step is skipped, and the existing MS will be imported instead.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Restore the pipeline results for a single ASDM in a single session

        >>> h_restoredata (vis=['uid___A002_X30a93d_X43e'], session=['session_1'], ocorr_mode='ca')

    """
