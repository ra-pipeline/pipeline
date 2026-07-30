import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.polcal.polcal.PolcalInputs.__init__
@utils.cli_wrapper
def hifa_polcal(vis=None, minpacov=None, solint_chavg=None, vs_stats=None, vs_thresh=None):
    """Perform per-session polarization calibration for ALMA.

    Derives the instrumental polarization calibrations using the polarization calibrators. This task is
    called once per session (which for ALMA polarization observations is typically 2-3 execution blocks).

    The WebLog displays the following tables:

    - Session information: MeasurementSets, polarization calibrator, and reference antenna per session.
    - Residual polarization of the calibrator after calibration (per spw and averaged over all spws).
    - Derived polarization of the calibrator (per spw and averaged over all spws).

    And the following plots per session for the polarization calibrator:

    - Amplitude vs. parallactic angle per spw
    - Gain amplitude polarization ratio vs. scan
    - Cross-hand phase vs. channel
    - D-term solution gain vs. channel per spw for all antennas
    - Gain ratio RMS vs. scan
    - X,Y amplitude vs. antenna per spw
    - X/Y amplitude gain ratio vs. antenna per spw
    - Real vs. imaginary component of the calibrated polarization calibrator (XX, YY, XY, YX)

    .. figure:: /figures/polcal.png
       :scale: 60%
       :alt: WebLog QA for hifa_polcal

       Example of the WebLog QA for the ``hifa_polcal`` stage.

    Notes:
        Four QA scores are computed:

        - Residual polarization: QA = 0.5 (yellow) if residual polarization > 0.1%; QA = 1.0 otherwise.
        - Gain ratio RMS: QA = 0.6 (yellow) if gain ratio RMS after calibration > 2%; QA = 1.0 otherwise.
        - D-terms: QA = 0.75 (blue) if D-terms 0.10-0.15; QA = 0.55 (yellow) if > 0.15; QA = 1.0
          otherwise.
        - Gain ratio: QA = 0.65 (yellow) if any antenna/spw gain ratio outside 0.9-1.10; QA = 1.0
          otherwise.

        Only used in polarization recipes.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Compute the polarization calibrations:

        >>> hifa_polcal()

    """
