import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifv.tasks.flagging.flagdetervla.FlagDeterVLAInputs.__init__
@utils.cli_wrapper
def hifv_flagdata(vis=None, autocorr=None, shadow=None, scan=None,
                  scannumber=None, quack=None, clip=None, baseband=None,
                  intents=None, edgespw=None, fracspw=None,
                  online=None, fileonline=None, template=None,
                  filetemplate=None, hm_tbuff=None, tbuff=None,
                  flagbackup=None):
    """Do basic deterministic flagging.

    The hifv_flagdata task performs basic flagging operations on a list of MeasurementSets including:

    - autocorrelation data flagging
    - shadowed antenna data flagging
    - scan based flagging
    - edge channel flagging
    - baseband edge flagging
    - applying online flags
    - applying a flagging template
    - quack, shadow, and basebands
    - Antenna not-on-source (ANOS)

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Do basic flagging on a MeasurementSet:

        >>> hifv_flagdata()

        2. Do basic flagging on a MeasurementSet as well as flag pointing and
        atmosphere data:

        >>> hifv_flagdata(scan=True intent='*BANDPASS*')

    """
