import sys

import pipeline.h.cli.utils as utils


def hsd_atmcor(atmtype=None, dtem_dh=None, h0=None, pipelinemode=None,
               infiles=None, antenna=None, field=None, spw=None, pol=None,
               dryrun=None, acceptresults=None, parallel=None):

    """
    hsd_atmcor ---- Apply offline ATM correction to the data.

    --------- parameter descriptions ---------------------------------------------

    atmtype       Type of atmospheric transmission model represented as an integer.
                  Available options are as follows. Integer values can be given as
                  either integer or string, i.e. both 1 and '1' are acceptable.
                  
                    'auto': perform heuristics to choose best model (default)
                         1: tropical
                         2: mid latitude summer
                         3: mid latitude winter
                         4: subarctic summer
                         5: subarctic winter
                  
                  If list of integer is given, it also performs heuristics using the
                  provided values instead of default, [1, 2, 3, 4], which is used
                  when 'auto' is provided. List input should not contain 'auto'.
                  
                  Default: 'auto'
    dtem_dh       temperature gradient [K/km], e.g. -5.6. ("" = Tool default)
                  
                  The value is directly passed to initialization method for ATM model.
                  Float and string types are acceptable. Float value is interpreted as
                  the value in K/km. String value should be the numeric value with unit
                  such as '-5.6K/km'. When list of values are given, it will
                  trigger heuristics to choose best model from the provided value.
                  
                  Default: '' (tool default, -5.6K/km, is used)
    h0            scale height for water [km], e.g. 2.0. ("" = Tool default)
                  
                  The value is directly passed to initialization method for ATM model.
                  Float and string types are acceptable. Float value is interpreted as
                  the value in kilometer. String value should be the numeric value with
                  unit compatible with length, such as '2km' or '2000m'.
                  When list of values are given, it will trigger heuristics to
                  choose best model from the provided value.
                  
                  Default: '' (tool default, 2.0km, is used)
    pipelinemode  The pipeline operating mode. In 'automatic' mode the
                  pipeline determines the values of all context defined
                  pipeline inputs automatically.  In interactive mode
                  the user can set the pipeline context defined parameters
                  manually. In 'getinputs' mode  the user can check the
                  settings of all pipeline parameters without running
                  the task.
    infiles       ASDM or MS files to be processed. This parameter behaves
                  as data selection parameter. The name specified by
                  infiles must be registered to context before you run
                  hsd_atmcor.
    antenna       Data selection by antenna names or ids.
                  example: 'PM03,PM04'
                           '' (all antennas)
    field         Data selection by field names or ids.
                  example: '*Sgr*,M100'
                           '' (all fields)
    spw           Data selection by spw ids.
                  example: '3,4' (spw 3 and 4)
                           '' (all spws)
    pol           Data selection by polarizations.
                  example: 'XX,YY' (correlation XX and YY)
                           '' (all polarizations)
    dryrun        Run the commands (True) or generate the commands to be
                  run but do not execute (False).
    acceptresults Add the results of the task to the pipeline context (True)
                  or reject them (False).
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
