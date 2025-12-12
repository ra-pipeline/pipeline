import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hsd.tasks.flagging.flagdeteralmasd.FlagDeterALMASingleDishInputs.__init__
@utils.cli_wrapper
def hsd_flagdata(vis=None, autocorr=None, shadow=None, scan=None,
                 scannumber=None, intents=None, edgespw=None, fracspw=None,
                 fracspwfps=None, online=None, fileonline=None, template=None,
                 filetemplate=None, pointing=None, filepointing=None, incompleteraster=None,
                 hm_tbuff=None, tbuff=None, qa0=None, qa2=None, parallel=None,
                 flagbackup=None):
    """Do basic flagging of a list of MeasurementSets.

    The hsd_flagdata data performs basic flagging operations on a list of
    MeasurementSets including:

    - applying online flags
    - applying a flagging template
    - shadowed antenna data flagging
    - scan-based flagging by intent or scan number
    - edge channel flagging

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Do basic flagging on a MeasurementSet

        >>> hsd_flagdata()

        2. Do basic flagging on a MeasurementSet flagging additional scans selected
        by number as well.

        >>> hsd_flagdata(scannumber='13,18')

    """
