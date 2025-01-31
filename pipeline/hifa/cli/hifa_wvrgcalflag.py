import sys

import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.wvrgcalflag.wvrgcalflag.WvrgcalflagInputs.__init__
@utils.cli_wrapper
def hifa_wvrgcalflag(vis=None, caltable=None, offsetstable=None, hm_toffset=None, toffset=None, segsource=None,
                     sourceflag=None, hm_tie=None, tie=None, nsol=None, disperse=None, wvrflag=None, hm_smooth=None,
                     smooth=None, scale=None, maxdistm=None, minnumants=None, mingoodfrac=None, refant=None,
                     flag_intent=None, qa_intent=None, qa_bandpass_intent=None, accept_threshold=None, flag_hi=None,
                     fhi_limit=None, fhi_minsample=None, ants_with_wvr_thresh=None):
    """Generate a gain table based on Water Vapor Radiometer data, interpolating over
    antennas with bad radiometers.

    This task will first identify for each vis whether it includes at least 3
    antennas with Water Vapor Radiometer (WVR) data, and that the fraction of
    WVR antennas / all antennas exceeds the minimum threshold
    (ants_with_wvr_thresh).

    If there are not enough WVR antennas by number and/or fraction, then no WVR
    caltable is created and no WVR calibration will be applied to the corresponding
    vis. If there are enough WVR antennas, then the task proceeds as follows for
    each valid vis:

    First, generate a gain table based on the Water Vapor Radiometer data for
    each vis.

    Second, apply the WVR calibration to the data specified by 'flag_intent',
    calculate flagging 'views' showing the ratio
    'phase-rms with WVR / phase-rms without WVR' for each scan. A ratio < 1
    implies that the phase noise is improved, a ratio > 1 implies that it
    is made worse.

    Third, search the flagging views for antennas with anomalous high values.
    If any are found then recalculate the WVR calibration with the 'wvrflag'
    parameter set to ignore their data and interpolate results from other
    antennas according to 'maxdistm' and 'minnumants'.

    Fourth, after flagging, if the remaining unflagged antennas with WVR number
    fewer than 3, or represent a smaller fraction of antennas than the minimum
    threshold (ants_with_wvr_thresh), then the WVR calibration file is rejected
    and will not be merged into the context, i.e. not be used in subsequent
    calibration.

    Fifth, if the overall QA score for the final WVR correction of a vis file
    is greater than the value in 'accept_threshold' then make available the
    wvr calibration file for merging into the context and use in the
    subsequent reduction.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Compute the WVR calibration for all the MeasurementSets:

        >>> hifa_wvrgcalflag(hm_tie='automatic')

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
