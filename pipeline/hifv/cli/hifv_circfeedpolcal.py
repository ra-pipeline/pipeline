import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.circfeedpolcal.circfeedpolcal.CircfeedpolcalInputs.__init__
@utils.cli_wrapper
def hifv_circfeedpolcal(vis=None, Dterm_solint=None, refantignore=None, leakage_poltype=None, mbdkcross=None,
                        clipminmax=None, refant=None, run_setjy=None):
    """Perform polarization calibration for VLA circular feeds.

    Only validated for VLA sky survey data in S-band continuum mode with 3C138
    or 3C286 as polarization angle. Requires that all polarization intents are
    properly set during observation.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Basic circfeedpolcal task:

        >>> hifv_circfeedpolcal()

    """
