import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hsdn.tasks.restoredata.restoredata.NRORestoreDataInputs.__init__
@utils.cli_wrapper
def hsdn_restoredata(vis=None, caltable=None, reffile=None,
                     products_dir=None, copytoraw=None, rawdata_dir=None, hm_rasterscan=None):
    """Restore flagged and calibration single dish data from a pipeline run.

    The hsdn_restoredata task restores flagged and calibrated data from archived
    MeasurementSets (MSes) and pipeline flagging and calibration data products.

    hsdn_restoredata assumes that the MSes to be restored are present in the
    directory specified by the ``rawdata_dir`` (default: '../rawdata').

    By default (``copytoraw`` = True), hsdn_restoredata assumes that for each
    MS in the input list, the corresponding pipeline flagging and calibration
    data products (in the format produced by the hsdn_exportdata task) are
    present in the directory specified by ``products_dir`` (default: '../products').
    At the start of the task, these products are copied from the ``products_dir``
    to the ``rawdata_dir``.

    If ``copytoraw`` = False, hsdn_restoredata assumes that these products are
    to be found in ``rawdata_dir`` along with the MSes.

    The expected flagging and calibration products (for each MS) include:

        - a compressed tar file of the final flagversions file, e.g.
          uid___A002_X30a93d_X43e.ms.flagversions.tar.gz

        - a text file containing the applycal instructions, e.g.
          uid___A002_X30a93d_X43e.ms.calapply.txt

        - a compressed tar file containing the caltables for the parent session,
          e.g. uid___A001_X74_X29.session_3.caltables.tar.gz


    hsdn_restoredata performs the following operations:

    - imports the MS(s)
    - removes the default MS.flagversions directory created by the filler
    - restores the final MS.flagversions directory stored by the pipeline
    - restores the final set of pipeline flags to the MS
    - restores the final calibration state of the MS
    - restores the final calibration tables for each MS
    - applies the calibration tables to each MS

    When importing the MS, if the output MS already exists in the output directory,
    the existing MS will be imported instead.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Restore the pipeline results for a single MS in a single session

        >>> hsdn_restoredata (vis=['mg2-20181016165248-190320.ms'], reffile='nroscalefactor.csv')

    """
