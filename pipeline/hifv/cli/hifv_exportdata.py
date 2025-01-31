import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.exportdata.vlaexportdata.VLAExportDataInputs.__init__
@utils.cli_wrapper
def hifv_exportdata(vis=None, session=None, imaging_products_only=None, exportmses=None, tarms=None, exportcalprods=None,
    pprfile=None, calintents=None, calimages=None, targetimages=None, products_dir=None,
    gainmap=None):

    """Prepare and export interferometry and imaging data.

    The hifv_exportdata task for the VLA CASA pipeline exports the data defined
    in the pipeline context and exports it to the data products directory,
    converting and or packing it as necessary.

    The current version of the task exports the following products

    - an XML file containing the pipeline processing request
    - a tar file per ASDM / MS containing the final flags version OR the MS if tarms is False
    - a text file per ASDM / MS containing the final calibration apply list
    - a FITS image for each selected calibrator source image
    - a FITS image for each selected science target source image
    - a tar file per session containing the caltables for that session
    - a tar file containing the file web log
    - a text file containing the final list of CASA commands

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Export the pipeline results for a single session to the data products
        directory:

        >>> !mkdir ../products
        >>> hifv_exportdata (products_dir='../products')

        2. Export the pipeline results to the data products directory specify that
        only the gain calibrator images be saved:

        >>> !mkdir ../products
        >>> hifv_exportdata (products_dir='../products', calintents='*PHASE*')

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
