import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hsd.tasks.restoredata.restoredata.SDRestoreDataInputs.__init__
@utils.cli_wrapper
def hsd_restoredata(vis=None, session=None, products_dir=None, copytoraw=None, rawdata_dir=None, lazy=None,
                    bdfflags=None, ocorr_mode=None, asis=None, hm_rasterscan=None):
    """Restore flagged and calibrated single-dish MeasurementSets from archived pipeline products.

    Restores flagged and calibrated MeasurementSets from archived ASDMs and pipeline flagging and
    calibration data products. This task is called at the beginning of single-dish imaging-only
    pipeline recipes.

    Assumes ASDMs are present in the directory given by ``rawdata_dir`` (default: ``'../rawdata'``).
    By default (``copytoraw=True``), the pipeline products are copied from ``products_dir``
    (default: ``'../products'``) to ``rawdata_dir`` at the start of the task. If
    ``copytoraw=False``, the products are expected to already be in ``rawdata_dir``.

    When converting an ASDM to MS, if the output MS already exists in the output directory,
    the ``importasdm`` step is skipped and the existing MS is imported instead.

    The expected products per ASDM are:

    - a compressed tar file of the final flag versions, e.g.
      ``uid___A002_X30a93d_X43e.ms.flagversions.tar.gz``
    - a text file with applycal instructions, e.g.
      ``uid___A002_X30a93d_X43e.ms.calapply.txt``
    - a compressed tar file with session caltables, e.g.
      ``uid___A001_X74_X29.session_3.caltables.tar.gz``

    The task performs the following operations:

    1. Imports the ASDM(s) to MS.
    2. Removes the default MS.flagversions directory created by the filler.
    3. Restores the final MS.flagversions directory stored by the pipeline.
    4. Restores the final set of pipeline flags to the MS.
    5. Restores the final calibration state of the MS.
    6. Restores the final calibration tables for each MS.
    7. Applies the calibration tables to each MS.

    Examples:
        1. Restore pipeline results for a single ASDM in a single session:

        >>> hsd_restoredata(vis=['uid___A002_X30a93d_X43e'], session=['session_1'], ocorr_mode='ao')

    """
