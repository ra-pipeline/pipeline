import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from h.tasks.exportdata.exportdata.ExportDataInputs.__init__
@utils.cli_wrapper
def hsdn_exportdata(pprfile=None,targetimages=None, products_dir=None):

    """Prepare single dish data for export.

    The hsdn_exportdata task exports the data defined in the pipeline context
    and exports it to the data products directory, converting and or packing
    it as necessary.

    The current version of the task exports the following products

    - a FITS image for each selected science target source image
    - a tar file per MS containing the final flags version and blparam
    - a tar file containing the file web log

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Export the pipeline results for a single session to the data products
        directory

        >>> !mkdir ../products
        >>> hsdn_exportdata (products_dir='../products')

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
