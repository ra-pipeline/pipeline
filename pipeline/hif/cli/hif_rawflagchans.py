import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.rawflagchans.rawflagchans.RawflagchansInputs.__init__
@utils.cli_wrapper
def hif_rawflagchans(vis=None, spw=None, intent=None,
  flag_hilo=None, fhl_limit=None, fhl_minsample=None,
  flag_bad_quadrant=None, fbq_hilo_limit=None,
  fbq_antenna_frac_limit=None, fbq_baseline_frac_limit=None):

    """Flag deviant baseline/channels in raw data

    hif_rawflagchans flags deviant baseline/channels in the raw data.

    The flagging views used are derived from the raw data for the specified
    intent - default is BANDPASS.

    Bad baseline/channels are flagged for all intents, not just the
    one that is the basis of the flagging views.

    For each spectral window the flagging view is a 2d image with axes
    'channel' and 'baseline'. The pixel for each channel, baseline is the
    time average of the underlying unflagged raw data.

    The baseline axis is labeled by numbers of form id1.id2 where id1 and id2
    are the IDs of the baseline antennas. Both id1 and id2 run over all
    antenna IDs in the observation. This means that each baseline is shown
    twice but has the benefit that 'bad' antennas are easily identified by
    eye.

    Three flagging methods are available:

    If parameter ``flag_hilo`` is set True then outliers from the median
    of each flagging view will be flagged.

    If parameter ``flag_bad_quadrant`` is set True then a simple 2 part
    test is used to check for bad antenna quadrants and/or bad baseline
    quadrants. Here a 'quadrant' is defined simply as one quarter of the
    channel axis. The first part of the test is to note as 'suspect' those
    points further from the view median than ``fbq_hilo_limit`` * MAD.
    The second part is to flag entire antenna/quadrants if their
    fraction of suspect points exceeds ``fbq_antenna_frac_limit``.
    Failing that, entire baseline/quadrants may be flagged if their
    fraction of suspect points exceeds ``fbq_baseline_frac_limit``.
    Suspect points are not flagged unless as part of a bad antenna or
    baseline quadrant.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Flag bad quadrants and wild outliers, default method:

        >>> hif_rawflagchans()

        equivalent to:

        >>> hif_rawflagchans(flag_hilo=True, fhl_limit=20, flag_bad_quadrant=True, fbq_hilo_limit=8,
        ...                  fbq_antenna_frac_limit=0.2, fbq_baseline_frac_limit=1.0)

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
