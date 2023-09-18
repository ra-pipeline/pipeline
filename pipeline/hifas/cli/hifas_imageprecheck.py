import sys

import pipeline.h.cli.utils as utils


@utils.cli_wrapper
def hifas_imageprecheck(vis=None, desired_angular_resolution=None, calcsb=None, parallel=None,
                        dryrun=None, acceptresults=None):

    """
    hifas_imageprecheck ---- Calculates the best robust value and Briggs weighting parameter to achieve sensitivity and angular resolution goals.

    
    In this task, the representative source and the spw containing the
    representative frequency selected by the PI in the OT are used to calculate
    the synthesized beam and to make sensitivity estimates for the aggregate
    bandwidth and representative bandwidth for several values of the robust parameter.
    This information is reported in a table in the weblog. If no representative
    target/frequency information is available, it defaults to the first target
    and center of first spw in the data (i.e. pre-Cycle 5 data does not have
    this information available). The best Briggs weighting parameter to achieve
    the PI's desired angular resolution is chosen automatically.
    See the User's guide for further details.
    
    results -- The results object for the pipeline task is returned.

    --------- parameter descriptions ---------------------------------------------

    vis                        The list of input MeasurementSets. Defaults to the list of
                               MeasurementSets specified in the h_init or hif_importdata task.
                               '': use all MeasurementSets in the context
                               
                               Examples: 'ngc5921.ms', ['ngc5921a.ms', ngc5921b.ms', 'ngc5921c.ms']
    desired_angular_resolution User specified angular resolution goal string.
                               '': automatic from performance parameters (default)
                               
                               Example: '1.0arcsec'
    calcsb                     Force (re-)calculation of sensitivities and beams
    parallel                   Use MPI cluster where possible
    dryrun                     Run the task (False) or just display the command (True)
    acceptresults              Add the results of the task to the pipeline context (True) or
                               reject them (False).

    --------- examples -----------------------------------------------------------

    


    """


    #                                                                        #
    #  CASA task interface boilerplate code starts here. No edits should be  #
    #  needed beyond this point.                                             #
    #                                                                        #

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
