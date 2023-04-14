import sys

import pipeline.h.cli.utils as utils


def hsd_exportdata(pprfile=None,targetimages=None, products_dir=None,
    pipelinemode=None, dryrun=None, acceptresults=None):

    """
    hsd_exportdata ---- Prepare single dish data for export

    
    The hsd_exportdata task exports the data defined in the pipeline context
    and exports it to the data products directory, converting and or packing
    it as necessary.
    
    The current version of the task exports the following products
    
    o a FITS image for each selected science target source image
    o a tar file per ASDM containing the final flags version and blparam
    o a tar file containing the file web log
    
    TBD
    o a file containing the line feature table(frequency, width, spatial distribution)
    o a file containing the list of identified transitions from line catalogs
    
    Output:
    
    results -- If pipeline mode is 'getinputs' then None is returned. Otherwise
    the results object for the pipeline task is returned.

    --------- parameter descriptions ---------------------------------------------

    pprfile       Name of the pipeline processing request to be exported. Defaults
                  to a file matching the template 'PPR_*.xml'.
                  Parameter is not available when pipelinemode='automatic'.
                  example: pprfile=['PPR_GRB021004.xml']
    targetimages  List of science target images to be exported. Defaults to all
                  science target images recorded in the pipeline context.
                  Parameter is not available when pipelinemode='automatic'.
                  example: targetimages=['r_aqr.CM02.spw5.line0.XXYY.sd.im', 'r_aqr.CM02.spw5.XXYY.sd.cont.im']
    products_dir  Name of the data products subdirectory. Defaults to './'
                  Parameter is not available when pipelinemode='automatic'.
                  example: products_dir='../products'
    pipelinemode  The pipeline operating mode. In 'automatic' mode the pipeline
                  determines the values of all context defined pipeline inputs automatically.
                  In 'interactive' mode the user can set the pipeline context defined
                  parameters manually.  In 'getinputs' mode the user can check the settings
                  of all pipeline parameters without running the task.
    dryrun        Run the task (False) or display task command (True).
                  Only available when pipelinemode='interactive'.
    acceptresults Add the results of the task to the pipeline context (True) or
                  reject them (False). Only available when pipelinemode='interactive'.

    --------- examples -----------------------------------------------------------

    
    1. Export the pipeline results for a single session to the data products
    directory
    
    !mkdir ../products
    hsd_exportdata (products_dir='../products')


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
