import sys

import pipeline.h.cli.utils as utils

def hifv_flagdata(vis=None, autocorr=None, shadow=None, scan=None,
                  scannumber=None, quack=None, clip=None, baseband=None,
                  intents=None, edgespw=None, fracspw=None,
                  online=None, fileonline=None, template=None,
                  filetemplate=None, hm_tbuff=None, tbuff=None,
                  pipelinemode=None, flagbackup=None, dryrun=None,
                  acceptresults=None):

    """
    hifv_flagdata ---- Do basic deterministic flagging of a list of MeasurementSets

    The hifv_flagdata task performs basic flagging operations on a list of
    MeasurementSets.
    
    The hifv_flagdata task performs basic flagging operations on a list of measurements including:
    
    o autocorrelation data flagging
    o shadowed antenna data flagging
    o scan based flagging
    o edge channel flagging
    o baseband edge flagging
    o applying online flags
    o applying a flagging template
    o quack, shadow, and basebands
    o Antenna not-on-source (ANOS)

    --------- parameter descriptions ---------------------------------------------

    vis           List of visibility data files. These may be ASDMs, tar files of ASDMs,
                  MSes, or tar files of MSes, If ASDM files are specified, they will be
                  converted  to MS format.
                  example: vis=['X227.ms', 'asdms.tar.gz']
    autocorr      Flag autocorrelation data
    shadow        Flag shadowed antennas
    scan          Flag specified scans
    scannumber    A string containing a  comma delimited list of scans to be flagged.
                  example: '3,5,6'
    quack         Quack scans
    clip          Clip mode
    baseband      Flag 20MHz of each edge of basebands
    intents       A string containing a comma delimited list of intents against
                  which the scans to be flagged are matched.
                  example: '*BANDPASS*'
    edgespw       Fraction of the baseline correlator TDM edge channels to be flagged.
    fracspw       Fraction of baseline correlator edge channels to be flagged
    online        Apply the online flags
    fileonline    File containing the online flags. These are computed by the
                  h_init or hif_importdata data tasks. If the online flags files
                  are undefined a name of the form 'msname.flagonline.txt' is assumed.
    template      Apply a flagging template
    filetemplate  The name of a text file that contains the flagging template
                  for RFI, birdies, telluric lines, etc.  If the template flags files
                  is undefined a name of the form 'msname.flagtemplate.txt' is assumed.
    hm_tbuff      The time buffer computation heuristic
    tbuff         List of time buffers (sec) to pad timerange in flag commands
    pipelinemode  The pipeline operating mode. In 'automatic' mode the pipeline
                  determines the values of all context defined pipeline inputs automatically.
                  In interactive mode the user can set the pipeline context defined parameters
                  manually.  In 'getinputs' mode the user can check the settings of all
                  pipeline parameters without running the task.
    flagbackup    Backup pre-existing flags before applying new ones. Only can be set in 
                  pipelinemode='interactive'.
    dryrun        Run the commands (True) or generate the commands to be run but
                  do not execute (False).  This is a pipeline task execution mode.
    acceptresults Add the results of the task to the pipeline context (True) or
                  reject them (False).  This is a pipeline task execution mode.

    --------- examples -----------------------------------------------------------

    
    Output:
    
    results -- If pipeline mode is 'getinputs' then None is returned. Otherwise
    the results object for the pipeline task is returned.
    
    Examples
    
    1. Do basic flagging on a MeasurementSet
    
    hifv_flagdata()
    
    2. Do basic flagging on a MeasurementSet as well as flag pointing and
    atmosphere data
    
    hifv_flagdata(scan=True intent='*BANDPASS*')


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
