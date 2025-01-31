import sys

import pipeline.h.cli.utils as utils

# docstring and type hints: inherits from hsd.tasks.baseline.baseline.SDBaselineInputs.__init__
@utils.cli_wrapper
def hsd_baseline(fitfunc=None, fitorder=None, switchpoly=None,
                 linewindow=None, linewindowmode=None, edge=None, broadline=None,
                 clusteringalgorithm=None, deviationmask=None, parallel=None,
                 infiles=None, field=None, antenna=None, spw=None, pol=None):

    """Detect and validate spectral lines, subtract baseline by masking detected lines.

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

    >>> hsd_baseline(spw='0')
    >>> hsd_baseline(spw='1')
    >>> hsd_blflag()
    >>> hsd_imaging()

    Since the second run of hsd_baseline overwrites the result for
    spw 0 with the data before baseline subtraction, this will not
    produce correct result for spw 0. Proper sequence for this use
    case is to process each spw to the imaging stage separately,
    which looks like as follows:

    >>> hsd_baseline(spw='0')
    >>> hsd_blflag(spw='0')
    >>> hsd_imaging(spw='0'))
    >>> hsd_baseline(spw='1')
    >>> hsd_blflag(spw='1')
    >>> hsd_imaging(spw='1')

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Basic usage with automatic line detection and validation

        >>> hsd_baseline(antenna='PM03', spw='17,19')

        2. Using pre-defined line windows without automatic line detection
           and edge channels

        >>> hsd_baseline(linewindow=[[100, 200], [1200, 1400]],
                         linewindowmode='replace', edge=[10, 10])

        3. Using per spw pre-defined line windows with automatic line detection

        >>> hsd_baseline(linewindow={19: [[390, 550]], 23: [[100, 200], [1200, 1400]]},
                         linewindowmode='merge')

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
