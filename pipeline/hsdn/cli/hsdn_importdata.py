import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hsdn.tasks.importdata.importdata.NROImportDataInputs.__init__
@utils.cli_wrapper
def hsdn_importdata(vis=None, session=None, hm_rasterscan=None, datacolumns=None,
                    overwrite=None, nocopy=None, createmms=None):

    """Imports Nobeyama data into the single dish pipeline.

    Imports Nobeyama data into the single dish pipeline.
    The hsdn_importdata task loads the specified visibility data into the pipeline
    context unpacking and / or converting it as necessary.

    If the ``overwrite`` input parameter is set to False, then when the output MS
    already exists in the output directory, the existing MS will be imported instead.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Load MS list in the ../rawdata subdirectory into the context:

        >>> hsdn_importdata (vis=['../rawdata/mg2-1.ms', '../rawdata/mg2-2.ms'])

        2. Load an MS in the current directory into the context:

        >>> hsdn_importdata (vis=['mg2.ms'])

        3. Load a tarred MS in ../rawdata into the context:

        >>> hsdn_importdata (vis=['../rawdata/mg2.tar.gz'])

        4. Import a list of MeasurementSets:

        >>> myvislist = ['mg2-1.ms', 'mg2-2.ms']
        >>> hsdn_importdata(vis=myvislist)

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
