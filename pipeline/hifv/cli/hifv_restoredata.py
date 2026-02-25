import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.restoredata.vlarestoredata.VLARestoreDataInputs.__init__
@utils.cli_wrapper
def hifv_restoredata(vis=None, session=None, products_dir=None, copytoraw=None, rawdata_dir=None, lazy=None,
                     bdfflags=None, ocorr_mode=None, gainmap=None, asis=None):
    """Restore flagged and calibration interferometry data from a pipeline run.

    ``hifv_restoredata`` restores flagged and calibrated data from archived
    ASDMs and pipeline flagging and calibration data products.

    hifv_restoredata assumes that the ASDMs to be restored are present in the
    directory specified by the ``rawdata_dir`` (default: '../rawdata').

    By default (``copytoraw`` = True), hifv_restoredata assumes that for each
    ASDM in the input list, the corresponding pipeline flagging and calibration
    data products (in the format produced by the hifv_exportdata task) are
    present in the directory specified by ``products_dir`` (default: '../products').
    At the start of the task, these products are copied from the ``products_dir``
    to the ``rawdata_dir``.

    If ``copytoraw`` = False, hifv_restoredata assumes that these products are
    to be found in ``rawdata_dir`` along with the ASDMs.

    The expected flagging and calibration products (for each ASDM) include:

        - a compressed tar file of the final flagversions file, e.g.
          uid___A002_X30a93d_X43e.ms.flagversions.tar.gz

        - a text file containing the applycal instructions, e.g.
          uid___A002_X30a93d_X43e.ms.calapply.txt

        - a compressed tar file containing the caltables for the parent session,
          e.g. uid___A001_X74_X29.session_3.caltables.tar.gz

    hifv_restoredata performs the following operations:

    - imports the ASDM(s)
    - runs the hanning smoothing task
    - removes the default MS.flagversions directory created by the filler
    - restores the final MS.flagversions directory stored by the pipeline
    - restores the final set of pipeline flags to the MS
    - restores the final calibration state of the MS
    - restores the final calibration tables for each MS
    - applies the calibration tables to each MS

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Restore the pipeline results for a single ASDM in a single session:

        >>> hifv_restoredata (vis=['myVLAsdm'], session=['session_1'], ocorr_mode='ca')

    """
