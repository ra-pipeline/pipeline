import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from h.tasks.exportdata.exportdata.ExportDataInputs.__init__
@utils.cli_wrapper
def hsd_exportdata(pprfile=None, targetimages=None, products_dir=None):
    """Prepare single dish data for export.

    The hsd_exportdata task exports the data defined in the pipeline context
    and exports it to the data products directory, converting and or packing
    it as necessary.

    The current version of the task exports the following products

    - a FITS image for each selected science target source image
    - a tar file per ASDM containing the final flags version and blparam
    - a tar file containing the file web log

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Export the pipeline results for a single session to the data products
        directory

        >>> !mkdir ../products
        >>> hsd_exportdata (products_dir='../products')

    """
