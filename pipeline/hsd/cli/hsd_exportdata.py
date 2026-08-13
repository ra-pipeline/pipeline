import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from h.tasks.exportdata.exportdata.ExportDataInputs.__init__
@utils.cli_wrapper
def hsd_exportdata(pprfile=None, targetimages=None, products_dir=None):
    """Export single-dish pipeline products to the ``products/`` directory.

    Moves calibration tables, images (FITS format), and other pipeline products from the pipeline
    ``working/`` directory to the ``products/`` directory.

    The following products are exported:

    - FITS images for each selected science target source.
    - A tar file per ASDM containing the final flag versions and baseline parameter (``blparam``)
      tables.
    - A tar file containing the WebLog.

    Notes:
        QA = 1.0 if all products were successfully exported; QA = 0.0 otherwise.

    Examples:
        1. Export pipeline results to the data products directory:

        >>> import os; os.makedirs('../products', exist_ok=True)
        >>> hsd_exportdata(products_dir='../products')

    """
