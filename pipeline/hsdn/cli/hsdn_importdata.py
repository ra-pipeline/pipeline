import sys

import pipeline.h.cli.utils as utils


def hsdn_importdata(vis=None, session=None, hm_rasterscan=None, pipelinemode=None, datacolumns=None,
                    overwrite=None, nocopy=None, createmms=None, dryrun=None,
                    acceptresults=None):

    """
    hsdn_importdata ---- Imports Nobeyama data into the single dish pipeline

    
    Imports Nobeyama data into the single dish pipeline.
    The hsdn_importdata task loads the specified visibility data into the pipeline
    context unpacking and / or converting it as necessary.
    
    If the 'overwrite' input parameter is set to False and the task is asked to
    convert an input ASDM input to an MS, then when the output MS already exists in
    the output directory, the importasdm conversion step is skipped, and the
    existing MS will be imported instead.
    
    Output
    
    results -- If pipeline mode is 'getinputs' then None is returned. Otherwise
    the results object for the pipeline task is returned.

    --------- parameter descriptions ---------------------------------------------

    vis           List of visibility data files. These may be ASDMs, tar files of ASDMs,
                  MSes, or tar files of MSes, If ASDM files are specified, they will be
                  converted to MS format.
                  example: vis=['X227.ms', 'asdms.tar.gz']
    session       List of sessions to which the visibility files belong. Defaults
                  to a single session containing all the visibility files, otherwise
                  a session must be assigned to each vis file.
                  example: session=['Session_1', 'Sessions_2']
    hm_rasterscan Heuristics method for raster scan analysis. Two analysis modes,
                  time-domain analysis ('time') and direction analysis ('direction'), are available.
                  Default is 'time'.
    pipelinemode  The pipeline operating mode. In 'automatic' mode the pipeline
                  determines the values of all context defined pipeline inputs
                  automatically.  In 'interactive' mode the user can set the pipeline
                  context defined parameters manually.  In 'getinputs' mode the user
                  can check the settings of all pipeline parameters without running
                  the task.
    datacolumns   Dictionary defining the data types of
                  existing columns. The format is:
                  
                  {'data': 'data type 1'}
                  or
                  {'data': 'data type 1', 'corrected': 'data type 2'}
                  
                  For ASDMs the data type can only be RAW and one
                  can only specify it for the data column.
                  
                  For MSes one can define two different data types
                  for the DATA and CORRECTED_DATA columns and they
                  can be any of the known data types (RAW,
                  REGCAL_CONTLINE_ALL, REGCAL_CONTLINE_SCIENCE,
                  SELFCAL_CONTLINE_SCIENCE, REGCAL_LINE_SCIENCE,
                  SELFCAL_LINE_SCIENCE, BASELINED, ATMCORR). The
                  intent selection strings _ALL or _SCIENCE can be
                  skipped. In that case the task determines this
                  automatically by inspecting the existing intents
                  in the dataset.
                  
                  Usually, a single datacolumns dictionary is used
                  for all datasets. If necessary, one can define a
                  list of dictionaries, one for each EB, with
                  different setups per EB.
                  
                  If no type is specified, {'data':'raw'} will
                  be assumed.
    overwrite     Overwrite existing files on import.
                  Can only be set in pipelinemode='interactive'.
                  When converting ASDM to MS, if overwrite=False and the MS already
                  exists in output directory, then this existing MS dataset will be used
                  instead.
    nocopy        Disable copying of MS to working directory.
                  Parameter is not available when pipelinemode='automatic'.
    createmms     Create an MMS
    dryrun        Run the task (False) or display task command (True).
                  Parameter is available only when pipelinemode='interactive'.
    acceptresults results of the task to the pipeline context (True) or reject them (False).
                  Parameter is available only when pipelinemode='interactive'.

    --------- examples -----------------------------------------------------------

    
    1. Load an ASDM list in the ../rawdata subdirectory into the context:
    
    hsdn_importdata (vis=['../rawdata/uid___A002_X30a93d_X43e',
    '../rawdata/uid_A002_x30a93d_X44e'])
    
    2. Load an MS in the current directory into the context:
    
    hsdn_importdata (vis=[uid___A002_X30a93d_X43e.ms])
    
    3. Load a tarred ASDM in ../rawdata into the context:
    
    hsdn_importdata (vis=['../rawdata/uid___A002_X30a93d_X43e.tar.gz'])
    
    4. Check the hsdn_importdata inputs, then import the data:
    
    myvislist = ['uid___A002_X30a93d_X43e.ms', 'uid_A002_x30a93d_X44e.ms']
    hsdn_importdata(vis=myvislist, pipelinemode='getinputs')
    hsdn_importdata(vis=myvislist)
    
    5. Load an ASDM but check the results before accepting them into the context:
    
    results = hsdn_importdata(vis=['uid___A002_X30a93d_X43e.ms'],
    acceptresults=False)
    results.accept()
    
    6. Run in dryrun mode before running for real:
    results = hsdn_importdata(vis=['uid___A002_X30a93d_X43e.ms'], dryrun=True)
    results = hsdn_importdata(vis=['uid___A002_X30a93d_X43e.ms'])


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
