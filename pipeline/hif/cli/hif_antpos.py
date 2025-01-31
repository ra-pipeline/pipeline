import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.antpos.antpos.AntposInputs.__init__
@utils.cli_wrapper
def hif_antpos(vis=None, caltable=None, hm_antpos=None, antenna=None, offsets=None, antposfile=None):

    """Derive an antenna position calibration table

    Derive the antenna position calibration for list of MeasurementSets.

    The hif_antpos task corrects the antenna positions recorded in the ASDMs using
    updated antenna position calibration information determined after the
    observation was taken.

    Corrections can be input by hand, read from a file on disk, or in the future
    by querying an ALMA database service.

    The antenna positions file is in 'csv' format containing 6 comma-delimited
    columns as shown below. The default name of this file is 'antennapos.csv'.

    Contents of example 'antennapos.csv' file::

        ms,antenna,xoffset,yoffset,zoffset,comment
        uid___A002_X30a93d_X43e.ms,DV11,0.000,0.010,0.000,"No comment"
        uid___A002_X30a93d_X43e.dup.ms,DV11,0.000,-0.010,0.000,"No comment"

    The corrections are used to generate a calibration table which is recorded
    in the pipeline context and applied to the raw visibility data, on the fly to
    generate other calibration tables, or permanently to generate calibrated
    visibilities for imaging.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Correct the position of antenna 5 for all the visibility files in a single
        pipeline run:

        >>> hif_antpos(antenna='DV05', offsets=[0.01, 0.02, 0.03])

        2. Correct the position of antennas for all the visibility files in a single
        pipeline run using antenna positions files on disk. These files are assumed
        to conform to a default naming scheme if ``antposfile`` is unspecified by the
        user:

        >>> hif_antpos(hm_antpos='file', antposfile='myantposfile.csv')

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
