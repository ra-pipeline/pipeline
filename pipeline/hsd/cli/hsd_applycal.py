import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hsd.tasks.applycal.applycal.SDApplycalInputs.__init__
@utils.cli_wrapper
def hsd_applycal(vis=None, field=None, intent=None, spw=None, antenna=None,
                 applymode=None, flagbackup=None, parallel=None):
    """Apply Tsys, sky, and Jy/K calibration tables to single-dish data.

    Applies the Tsys (amplitude-scale), sky (OFF-source), and Kelvin-to-Jansky calibration tables
    stored in the pipeline context to the science target data. The WebLog lists the calibrated MSs
    with the names of the applied caltables and shows:

    - Frequency-averaged amplitude vs. time plots after calibration.
    - Time-averaged amplitude vs. frequency plots after calibration.
    - Heuristic plots of the XX-YY polarization amplitude difference (Figure showing a
      good case and a case requiring attention), useful for detecting receiver instabilities
      or polarization leakages.

    .. figure:: /figures/XX-YY.png
       :scale: 60%
       :alt: XX-YY polarization difference heuristic plots

       Heuristic plots for amplitude difference between two polarizations.
       Left: good case. Right: case requiring attention.

    Notes:
        Two QA scores are computed:

        **Flagging QA** (restricted to TARGET scans; falls back to all intents if no TARGET
        scans are present):

        - QA = 1.0 if additional flagging is 0%-5%.
        - QA = 1.0-0.5 if additional flagging is 5%-50%.
        - QA = 0.0 if additional flagging > 50%.

        **XX-YY polarization difference QA**:

        - QA = 1.0 if no significant XX-YY polarization difference is detected.
        - QA = 0.95-0.65 if an XX-YY deviation is detected.
        - QA < 0.65 if a large XX-YY deviation outlier is detected.

    Examples:
        1. Apply calibration to the science target data:

        >>> hsd_applycal(intent='TARGET')

        2. Apply calibration to specific fields and spectral windows:

        >>> hsd_applycal(field='3C279, M82', spw='17', intent='TARGET')

    """
