import sys

import pipeline.h.cli.utils as utils


@utils.cli_wrapper
def hsdn_restoredata(vis=None, caltable=None, reffile=None,
                     products_dir=None, copytoraw=None, rawdata_dir=None, hm_rasterscan=None,
                     dryrun=False, acceptresults=None):

    """
    hsdn_restoredata ---- Restore flagged and calibration single dish data from a pipeline run

    
    The hsdn_restoredata task restores flagged and calibrated MeasurementSets
    from archived ASDMs and pipeline flagging and calibration date products.

    The hsdn_restoredata task restores flagged and calibrated data from archived
    ASDMs and pipeline flagging and calibration data products. Pending archive
    retrieval support hsdn_restoredata assumes that the required products
    are available in the rawdata_dir in the format produced by the
    hifa_exportdata task.
    
    hsdn_restoredata assumes that the following entities are available in the raw
    data directory:
    
    o the ASDMs to be restored
    o for each ASDM in the input list:
    o a compressed tar file of the final flagversions file, e.g.
    uid___A002_X30a93d_X43e.ms.flagversions.tar.gz
    o a text file containing the applycal instructions, e.g.
    uid___A002_X30a93d_X43e.ms.calapply.txt
    o a compressed tar file containing the caltables for the parent session,
    e.g. uid___A001_X74_X29.session_3.caltables.tar.gz
    
    hsdn_restoredata performs the following operations:
    
    o imports the ASDM(s)
    o removes the default MS.flagversions directory created by the filler
    o restores the final MS.flagversions directory stored by the pipeline
    o restores the final set of pipeline flags to the MS
    o restores the final calibration state of the MS
    o restores the final calibration tables for each MS
    o applies the calibration tables to each MS
    
    When importing the ASDM and converting it to a Measurement Set (MS), if the
    output MS already exists in the output directory, then the importasdm
    conversion step is skipped, and the existing MS will be imported instead.
    
    Output:
    
    results -- The results object for the pipeline task is returned.

    --------- parameter descriptions ---------------------------------------------

    vis           List of raw visibility data files to be restored. Assumed to be
                  in the directory specified by rawdata_dir.
                  
                  example: vis=['uid___A002_X30a93d_X43e']
    caltable      Name of output gain calibration tables.
                  
                  example: caltable='ngc5921.gcal'
    reffile       Path to a file containing scaling factors between beams.
                  The format is equals to jyperk.csv with five fields:
                  MS name, beam name (instead of antenna name), spectral window id,
                  polarization string, and the scaling factor.
                  Example for the file is as follows:
                  
                  #MS,Beam,Spwid,Polarization,Factor
                  mg2-20181016165248-181017.ms,NRO-BEAM0,0,I,1.000000000
                  mg2-20181016165248-181017.ms,NRO-BEAM0,1,I,1.000000000
                  mg2-20181016165248-181017.ms,NRO-BEAM0,2,I,1.000000000
                  mg2-20181016165248-181017.ms,NRO-BEAM0,3,I,1.000000000
                  mg2-20181016165248-181017.ms,NRO-BEAM1,0,I,3.000000000
                  mg2-20181016165248-181017.ms,NRO-BEAM1,1,I,3.000000000
                  mg2-20181016165248-181017.ms,NRO-BEAM1,2,I,3.000000000
                  mg2-20181016165248-181017.ms,NRO-BEAM1,3,I,3.000000000
                  mg2-20181016165248-181017.ms,NRO-BEAM2,0,I,0.500000000
                  mg2-20181016165248-181017.ms,NRO-BEAM2,1,I,0.500000000
                  mg2-20181016165248-181017.ms,NRO-BEAM2,2,I,0.500000000
                  mg2-20181016165248-181017.ms,NRO-BEAM2,3,I,0.500000000
                  mg2-20181016165248-181017.ms,NRO-BEAM3,0,I,2.000000000
                  mg2-20181016165248-181017.ms,NRO-BEAM3,1,I,2.000000000
                  mg2-20181016165248-181017.ms,NRO-BEAM3,2,I,2.000000000
                  mg2-20181016165248-181017.ms,NRO-BEAM3,3,I,2.000000000
                  
                  If no file name is specified or specified file doesn't exist,
                  all the factors are set to 1.0.
                  
                  example: reffile='', reffile='nroscalefactor.csv'
    products_dir  Name of the data products directory. Currently not
                  used.
                  
                  example: products_dir='myproductspath'
    copytoraw     Copy calibration and flagging tables to raw data directory.
                  
                  example: copytoraw=False
    rawdata_dir   Name of the raw data directory.
                  
                  example: rawdata_dir='myrawdatapath'
    hm_rasterscan Heuristics method for raster scan analysis. Two analysis modes,
                  time-domain analysis ('time') and direction analysis ('direction'), are available.
                  Default is 'time'.
    dryrun        Run the commands (True) or generate the commands to be run but
                  do not execute (False).
    acceptresults Add the results of the task to the pipeline context (True) or
                  reject them (False).

    --------- examples -----------------------------------------------------------

    
    1. Restore the pipeline results for a single ASDM in a single session
    
    hsdn_restoredata (vis=['mg2-20181016165248-190320.ms'], reffile='nroscalefactor.csv')


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
