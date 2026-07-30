import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.exportdata.almaexportdata.ALMAExportDataInputs.__init__
@utils.cli_wrapper
def hifa_exportdata(vis=None, session=None, imaging_products_only=None, exportmses=None, tarms=None,
                    pprfile=None, calintents=None,
                    calimages=None, targetimages=None, products_dir=None):
    """Export pipeline data products to the ``products/`` directory.

    Moves calibration tables, calibrator images (FITS format), and other pipeline products from the
    pipeline ``working/`` directory to the ``products/`` directory. For combined calibration and
    imaging runs, an intermediate calibration-only WebLog tar file is also created.

    If the :py:func:`hifa_polcal <hifa_polcal>` recipe is not specified in the pipeline context in ``casa_pipescript.py``,
    the polarization calibrator image FITS files are not exported in this step.

    The following products are exported:

    - an XML file containing the pipeline processing request
    - a tar file per ASDM/MS containing the final flags version
    - a text file per ASDM/MS containing the final calibration apply list
    - a FITS image for each selected calibrator source image
    - a FITS image for each selected science target source image (imaging runs only)
    - a ``cont.dat`` file from :py:func:`hif_findcont <hif_findcont>` (imaging runs only)
    - a tar file per session containing the caltables for that session
    - a tar file containing the WebLog
    - a text file containing the final list of CASA commands
    - an XML ``manifest`` file listing all products
    - an XML ``aquareport`` file listing QA scores, sub-scores, image sensitivities, and other
      numerical information

    Notes:
        QA = 1.0 if all standard products were successfully copied to the ``products/`` directory;
        QA = 0.0 otherwise.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Export the pipeline results for a single session:

        >>> import os; os.makedirs('../products', exist_ok=True)
        >>> hifa_exportdata(products_dir='../products')

        2. Export results saving only gain calibrator images:

        >>> import os; os.makedirs('../products', exist_ok=True)
        >>> hifa_exportdata(products_dir='../products', calintents='*PHASE*')

    """
