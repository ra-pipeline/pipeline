import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.importdata.almaimportdata.ALMAImportDataInputs.__init__
@utils.cli_wrapper
def hifa_importdata(vis=None, session=None, asis=None, process_caldevice=None, overwrite=None, nocopy=None,
                    bdfflags=None, datacolumns=None, lazy=None, dbservice=None, ocorr_mode=None, createmms=None,
                    minparang=None, parallel=None):
    """Imports data into the interferometry pipeline

    The hifa_importdata task loads the specified visibility data into the pipeline
    context unpacking and / or converting it as necessary.

    If the ``overwrite`` input parameter is set to False and the task is asked
    to convert an input ASDM input to an MS, then when the output MS already
    exists in the output directory, the importasdm conversion step is skipped,
    and the existing MS will be imported instead.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Load an ASDM list in the ../rawdata subdirectory into the context:

        >>> hifa_importdata(vis=['../rawdata/uid___A002_X30a93d_X43e', '../rawdata/uid_A002_x30a93d_X44e'])

        2. Load an MS in the current directory into the context:

        >>> hifa_importdata(vis=['uid___A002_X30a93d_X43e.ms'])

        3. Load a tarred ASDM in ../rawdata into the context:

        >>> hifa_importdata(vis=['../rawdata/uid___A002_X30a93d_X43e.tar.gz'])

        4. Import a list of MeasurementSets:

        >>> myvislist = ['uid___A002_X30a93d_X43e.ms', 'uid_A002_x30a93d_X44e.ms']
        >>> hifa_importdata(vis=myvislist)

        5. Run with explicit setting of data column types:

        >>> hifa_importdata(vis=['uid___A002_X30a93d_X43e_targets.ms'], datacolumns={'data': 'regcal_contline'})
        >>> hifa_importdata(vis=['uid___A002_X30a93d_X43e_targets_line.ms'], datacolumns={'data': 'regcal_line', 'corrected': 'selfcal_line'})

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
