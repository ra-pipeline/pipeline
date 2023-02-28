import sys

import pipeline.h.cli.utils as utils


def hsd_baseline(fitfunc=None, fitorder=None, switchpoly=None,
                 linewindow=None, linewindowmode=None, edge=None, broadline=None,
                 clusteringalgorithm=None, deviationmask=None, pipelinemode=None,
                 infiles=None, field=None, antenna=None, spw=None, pol=None,
                 dryrun=None, acceptresults=None, parallel=None):

    """
    hsd_baseline ---- Detect and validate spectral lines, subtract baseline by masking detected lines

    The hsd_baseline task subtracts baseline from calibrated spectra.
    By default, the task tries to find spectral line feature using
    line detection and validation algorithms. Then, the task puts a
    mask on detected lines and perform baseline subtraction.
    The user is able to turn off automatic line masking by setting
    linewindow parameter, which specifies pre-defined line window.
    
    Fitting order is automatically determined by default. It can be
    disabled by specifying fitorder as non-negative value. In this
    case, the value specified by fitorder will be used.
    
    ***WARNING***
    Currently, hsd_baseline overwrites the result obtained by the
    previous run. Due to this behavior, users need to be careful
    about an order of the task execution when they run hsd_baseline
    multiple times with different data selection. Suppose there are
    two spectral windows (0 and 1) and hsd_baseline is executed
    separately for each spw as below,
    
    hsd_baseline(pipelinemode="interactive", spw="0")
    hsd_baseline(pipelinemode="interactive", spw="1")
    hsd_blflag(pipelinemode="automatic")
    hsd_imaging(pipelinemode="automatic")
    
    Since the second run of hsd_baseline overwrites the result for
    spw 0 with the data before baseline subtraction, this will not
    produce correct result for spw 0. Proper sequence for this use
    case is to process each spw to the imaging stage separately,
    which looks like as follows:
    
    hsd_baseline(pipelinemode="interactive", spw="0")
    hsd_blflag(pipelinemode="interactive", spw="0")
    hsd_imaging(pipelinemode="interactive", spw="0"))
    hsd_baseline(pipelinemode="interactive", spw="1")
    hsd_blflag(pipelinemode="interactive", spw="1")
    hsd_imaging(pipelinemode="interactive", spw="1")
    
    Output:
    results -- If pipeline mode is 'getinputs' then None is returned.
    Otherwise the results object for the pipeline task is
    returned.

    --------- parameter descriptions ---------------------------------------------

    fitfunc             fitting function for baseline subtraction. You can only
                        choose cubic spline ('spline' or 'cspline')
    fitorder            Fitting order for polynomial. For cubic spline, it is used
                        to determine how much the spectrum is segmented into.
                        Default (-1) is to determine the order automatically.
    switchpoly          If True, switch to 1st or 2nd order polynomial fit when
                        large mask exists at edge regardless of whatever fitfunc
                        or fitorder are specified. Condition for switching is as
                        follows:
                            if nmask > nchan/2      => 1st order polynomial
                            else if nmask > nchan/4 => 2nd order polynomial
                            else                    => use fitfunc and fitorder
                        where nmask is a number of channels for mask at edge while
                        nchan is a number of channels of entire spectral window.
    linewindow          Pre-defined line window. If this is set, specified line
                                          windows are used as a line mask for baseline subtraction
                                           instead to determine masks based on line detection and
                                           validation stage. Several types of format are acceptable.
                                           One is channel-based window,
                                               [min_chan, max_chan]
                                           where min_chan and max_chan should be an integer. For
                                           multiple  windows, nested list is also acceptable,
                                               [[min_chan0, max_chan0], [min_chan1, max_chan1], ...]
                                           Another way is frequency-based window,
                                               [min_freq, max_freq]
                                           where min_freq and max_freq should be either a float or
                                           a string. If float value is given, it is interpreted as
                                           a frequency in Hz. String should be a quantity consisting
                                           of "value" and "unit",
                                           e.g., '100GHz'. Multiple windows are also supported.
                                               [[min_freq0, max_freq0], [min_freq1, max_freq1], ...]
                                           Note that the specified frequencies are assumed to be
                                           the value in LSRK frame. Note also that there is a
                                           limitation when multiple MSes are processed.
                                           If native frequency frame of the data is not LSRK
                                           (e.g. TOPO), frequencies need to be converted to that
                                           frame. As a result, corresponding channel range may vary
                                           between MSes. However, current implementation is not
                                           able to handle such case. Frequencies are converted to
                                           desired frame using representative MS (time, position,
                                           direction).
                        
                                           In the above cases, specified line windows are applied
                                           to all science spws. In case when line windows vary with
                                           spw, line windows can be specified by a dictionary whose
                                           key is spw id while value is line window.
                                           For example, the following dictionary gives different
                                           line windows to spws 17 and 19. Other spws, if available,
                                           will have an empty line window.
                                               {17: [[100, 200], [1200, 1400]], 19: ['112115MHz', '112116MHz']}
                                           Furthermore, linewindow accepts MS selection string.
                                           The following string gives [[100,200],[1200,1400]] for
                                           spw 17 while [1000,1500] for spw 21.
                                               "17:100~200;1200~1400,21:1000~1500"
                                           The string also accepts frequency with units. Note,
                                           however, that frequency reference frame in this case is
                                           not fixed to LSRK. Instead, the frame will be taken from
                                           the MS (typically TOPO for ALMA).
                                           Thus, the following two frequency-based line windows
                                           result different channel selections.
                                               {19: ['112115MHz', '112116MHz']} # frequency frame is LSRK
                                               "19:11215MHz~11216MHz" # frequency frame is taken from the data
                                                                                # (TOPO for ALMA)
                        
                        example: [100,200] (channel), [115e9, 115.1e9] (frequency in Hz)
                                 ['115GHz', '115.1GHz'], see above for more examples
    linewindowmode      Merge or replace given manual line window with line
                        detection/validation result. If 'replace' is given, line
                        detection and validation will not be performed.
                        On the other hand, when 'merge' is specified, line
                        detection/validation will be performed and manually
                        specified line windows are added to the result.
                        Note that this has no effect when linewindow for target
                        spw is empty. In that case, line detection/validation
                        will be performed regardless of the value of
                        linewindowmode.
    edge                Number of edge channels to be dropped from baseline
                        subtraction. The value must be a list with length of 2,
                        whose values specify left and right edge channels,
                        respectively.
                        
                        example: [10,10]
    broadline           Try to detect broad component of spectral line if True.
    clusteringalgorithm Selection of the algorithm used in the clustering
                         analysis to check the validity of detected line features.
                        'kmean' algorithm and hierarchical clustering algorithm
                        'hierarchy', and their combination ('both') are so far
                        implemented.
    deviationmask       Apply deviation mask in addition to masks determined by
                        the automatic line detection.
    pipelinemode        The pipeline operating mode. In 'automatic' mode the
                        pipeline determines the values of all context defined
                        pipeline inputs  automatically.  In 'interactive' mode
                        the user can set the pipeline context defined parameters
                        manually.  In 'getinputs' mode the user can check the
                        settings of all pipeline parameters without running the
                        task.
    infiles             List of data files. These must be a name of
                        MeasurementSets that are registered to context via
                        hsd_importdata task.
                        
                        example: vis=['X227.ms', 'X228.ms']
    field               Data selection by field.
                        example: '1' (select by FIELD_ID)
                                 'M100*' (select by field name)
                                 '' (all fields)
    antenna             Data selection by antenna.
                        example: '1' (select by ANTENNA_ID)
                                 'PM03' (select by antenna name)
                                 '' (all antennas)
    spw                 Data selection by spw.
                        example: '3,4' (generate caltable for spw 3 and 4)
                                 ['0','2'] (spw 0 for first data, 2 for second)
                                 '' (all spws)
    pol                 Data selection by polarizations.
                        example: '0' (generate caltable for pol 0)
                                 ['0~1','0'] (pol 0 and 1 for first data, only 0 for second)
                                 '' (all polarizations)
    dryrun              Run the commands (True) or generate the commands to be
                        run but do not execute (False).
    acceptresults       Add the results of the task to the pipeline context (True)
                        or reject them (False).
    parallel            Execute using CASA HPC functionality, if available.

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
