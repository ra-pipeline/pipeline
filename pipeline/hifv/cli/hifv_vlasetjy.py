import sys

from casatasks import casalog

import pipeline.h.cli.utils as utils


def hifv_vlasetjy(vis=None, field=None, intent=None, spw=None, model=None, reffile=None, fluxdensity=None, spix=None,
                  reffreq=None, scalebychan=None, standard=None, dryrun=None, acceptresults=None):

    """
    hifv_vlasetjy ---- Sets flux density scale and fills calibrator model to measurement set

    --------- parameter descriptions ---------------------------------------------

    vis           List of visibility data files. These may be ASDMs, tar files of ASDMs,
                  MSes, or tar files of MSes, If ASDM files are specified, they will be
                  converted  to MS format.
                  example: vis=['X227.ms', 'asdms.tar.gz']
    field         List of field names or ids.
    intent        Observing intent of flux calibrators.
    spw           List of spectral window ids.
    model         File location for field model.
    reffile       Path to file with fluxes for non-solar system calibrators.
    fluxdensity   Specified flux density [I,Q,U,V]; -1 will lookup values
    spix          Spectral index of fluxdensity.  Can be set when fluxdensity is not -1
    reffreq       Reference frequency for spix.  Can be set when fluxdensity is not -1
    scalebychan   Scale the flux density on a per channel basis or else on a per spw basis
    standard      Flux density standard
    dryrun        Run the commands (True) or generate the commands to be run but
                  do not execute (False).  This is a pipeline task execution mode.
    acceptresults Add the results of the task to the pipeline context (True) or
                  reject them (False).  This is a pipeline task execution mode.

    --------- examples -----------------------------------------------------------

    
    The hifv_vlasetjy task does an initial run of setjy on the vis
    
    
    Output:
    
    results -- The results object for the pipeline task is returned.
    
    standard -- Flux density standard
    default: ''
    
    Examples
    
    1. Initial run of setjy:
    
    hifv_vlasetjy()


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
