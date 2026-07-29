import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hsd.tasks.flagging.flagdeteralmasd.FlagDeterALMASingleDishInputs.__init__
@utils.cli_wrapper
def hsd_flagdata(vis=None, autocorr=None, shadow=None, scan=None,
                 scannumber=None, intents=None, edgespw=None, fracspw=None,
                 fracspwfps=None, online=None, fileonline=None, template=None,
                 filetemplate=None, pointing=None, filepointing=None, incompleteraster=None,
                 hm_tbuff=None, tbuff=None, qa0=None, qa2=None, parallel=None,
                 flagbackup=None):
    """Apply deterministic flagging to single-dish MeasurementSets.

    Performs a sequence of flagging operations on each MS. The WebLog shows the percentage of
    flagged data per MS for each agent. The ``Before Task`` column reports the percentage of data
    already flagged by binary data flagging (BDF) prior to this task. The reasons for flagging are
    also displayed visually as a function of time.

    Flagging agents applied:

    - **Online flags**: flags provided by the online system.
    - **Template flags**: flags from user-provided ``*flagtemplate.txt`` files.
    - **Shadow**: antennas shadowed by others.
    - **Unwanted intents**: scans with intents not required for processing.
    - **Autocorrelation**: always disabled (autocorrelations are not used for SD).
    - **Edge channels**: leading/trailing channels of each spw.
    - **Pointing outlier** (PL2025+): safety-net flag for OFF positions not removed by online
      flags, which would otherwise cause map creation to crash. A map-size threshold is computed
      and data points outside it are flagged.

    Notes:
        QA scoring:

        - Score = 0 if flag fraction >= 60%; Score = 1 if flag fraction <= 5%; linearly
          interpolated between 0 and 1 for fractions 5%-60%. Applies to ``online``, ``shadow``,
          ``qa0``, ``qa2``, ``before``, and ``template`` flagging agents.
        - Pointing outlier QA (PL2025+): 1.0 if no pointing outliers detected; 0.83 if outliers
          detected.

    Examples:
        1. Do basic flagging on a MeasurementSet:

        >>> hsd_flagdata()

        2. Do basic flagging and flag additional scans selected by number:

        >>> hsd_flagdata(scannumber='13,18')

    """
