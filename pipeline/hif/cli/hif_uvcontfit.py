import sys

from casatasks import casalog

import pipeline.h.cli.utils as utils


def hif_uvcontfit(vis=None, caltable=None, contfile=None, field=None, intent=None, spw=None, combine=None, solint=None,
                  fitorder=None, pipelinemode=None, dryrun=None, acceptresults=None):

    """
    hif_uvcontfit ---- Fit the continuum in the UV plane

    
    This task estimates the continuum emission by fitting polynomials to the real and
    imaginary parts of the spectral windows and frequency ranges selected by the spw
    parameter and specified in the contfile. This fit represents a model of the continuum
    in all channels. Fit orders less than 2 are strongly recommended. Spw window
    combination is not currently supported.

    --------- parameter descriptions ---------------------------------------------

    vis           The list of input MeasurementSets. Defaults to the list of
                  MeasurementSets specified in the h_init or hif_importdata task.
                  '': use all MeasurementSets in the context
                  Examples: 'ngc5921.ms', ['ngc5921a.ms', ngc5921b.ms', 'ngc5921c.ms']
    caltable      The list of output Mueller matrix calibration tables one per
                  input MS. 
                  '': The output names default to the standard pipeline name
                      scheme
    contfile      Name of the input file of per source / spw continuum regions
                  '': Defaults first to the file named in the context, next to a
                      file called 'cont.dat' in the pipeline working directory.
    field         The list of field names or field ids for which UV continuum
                  fits are computed. Defaults to all fields.
                  Eexamples: '3C279', '3C279, M82'
    intent        A string containing a comma delimited list of intents against
                  which the selected fields are matched.
                  '': Defaults to all data with TARGET intent.
    spw           The list of spectral windows and channels for which uv
                  continuum fits are computed.
                  '', Defaults to all science spectral windows.
                  Example: '11,13,15,17'
    combine       Data axes to be combined for solving. Axes are 'scan', 'spw',
                  or ''.
                  This option is currently not supported.
    solint        Time scale for the continuum fit
    fitorder      Polynomial order for the continuum fits
    pipelinemode  The pipeline operating mode.
                  In 'automatic' mode the pipeline determines the values of all
                  context defined pipeline inputs automatically.
                  In 'interactive' mode the user can set the pipeline context
                  defined parameters manually.
                  In 'getinputs' mode the user can check the settings of all
                  pipeline parameters without running the task.
    dryrun        Run the task (False) or just display the command (True)
    acceptresults Add the results of the task to the pipeline context (True) or
                  reject them (False).

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
