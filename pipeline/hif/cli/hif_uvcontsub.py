import sys

import pipeline.h.cli.utils as utils


@utils.cli_wrapper
def hif_uvcontsub(vis=None, field=None, intent=None, spw=None, fitorder=None, dryrun=None, acceptresults=None,
                  parallel=None):
    """
    hif_uvcontsub ---- Subtract the fitted continuum from the data


    hif_uvcontsub applies the precomputed uv continuum fit tables stored in the
    pipeline context to the set of visibility files using predetermined field and
    spectral window maps and default values for the interpolation schemes.

    Users can interact with the pipeline calibration state using the tasks
    h_export_calstate and h_import_calstate.

    results -- The results object for the pipeline task is returned

    --------- parameter descriptions ---------------------------------------------

    vis           The list of input MeasurementSets. Defaults to the list of
                  MeasurementSets specified in the h_init or hif_importdata task.
                  '': use all MeasurementSets in the context

                  Examples: 'ngc5921.ms', ['ngc5921a.ms', ngc5921b.ms', 'ngc5921c.ms']
    field         The list of field names or field ids for which UV continuum
                  fits are computed. Defaults to all fields.
                  Examples: '3C279', '3C279, M82'
    intent        A string containing a comma delimited list of intents against
                  which the selected fields are matched.
                  '': Defaults to all data with TARGET intent.
    spw           The list of spectral windows and channels for which uv
                  continuum fits are computed.
                  '', Defaults to all science spectral windows.

                  Example: '11,13,15,17'
    fitorder      Polynomial order for the continuum fits per source and spw.
                  Defaults to {} which means fit order 1 for all sources and
                  spws. If an explicit dictionary is given then all unspecified
                  selections still default to 1.

                  Example: {'3C279': {'15': 1, '17': 2}, 'M82': {'13': 2}}
    dryrun        Run the task (False) or just display the command (True)
    acceptresults Add the results of the task to the pipeline context (True) or
                  reject them (False).
    parallel      Execute using CASA HPC functionality, if available.

    --------- examples -----------------------------------------------------------




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
