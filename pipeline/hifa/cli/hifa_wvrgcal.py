import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.wvrgcal.wvrgcal.WvrgcalInputs.__init__
@utils.cli_wrapper
def hifa_wvrgcal(vis=None, caltable=None, offsetstable=None, hm_toffset=None, toffset=None, segsource=None,
                 sourceflag=None, hm_tie=None, tie=None, nsol=None, disperse=None, wvrflag=None, hm_smooth=None,
                 smooth=None, scale=None, maxdistm=None, minnumants=None, mingoodfrac=None, refant=None, qa_intent=None,
                 qa_bandpass_intent=None, qa_spw=None, accept_threshold=None):
    """Generate a gain table based on Water Vapor Radiometer (WVR) data.

    Generate a gain table based on the Water Vapor Radiometer data in each vis
    file. By applying the wvr calibration to the data specified by ``qa_intent``
    and ``qa_spw``, calculate a QA score to indicate its effect on
    interferometric data; a score > 1 implies that the phase noise is improved,
    a score < 1 implies that it is made worse. If the score is less than
    ``accept_threshold`` then the wvr gain table is not accepted into the
    context for subsequent use.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Compute the WVR calibration for all the MeasurementSets:

        >>> hifa_wvrgcal(hm_tie='automatic')

    """
