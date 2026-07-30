import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.tsysflag_contamination.tsysflagcontamination.TsysFlagContaminationInputs.__init__
@utils.cli_wrapper
def hifa_tsysflagcontamination(
    vis=None,
    caltable=None,
    filetemplate=None,
    logpath=None,
    remove_n_extreme=None,
    relative_detection_factor=None,
    diagnostic_plots=None,
    continue_on_failure=None,
    parallel=None,
):
    """Flag astronomical line contamination in the system temperature (Tsys) calibration table.

    Identifies and flags channel ranges in the Tsys spectrum where astronomical line emission is detected.
    Differences in line emission profiles due to variations in spatial position and spectral resolution between
    the Tsys spectrum and the autocorrelation spectrum can introduce mis-calibration in the affected channels.
    This task corrects the Tsys contamination; :py:func:`hifa_renorm <hifa_renorm>` handles the corresponding autocorrelation issue.

    The heuristics compare Tsys spectra from CALIBRATE_ATMOSPHERE scans toward the science source (and
    sometimes the phase calibrator) against the Tsys spectrum from the bandpass calibrator. The hypothesis is
    that these should be similar except for atmospheric line profile differences due to airmass, and any
    astronomical line contamination. Channel ranges where the difference exceeds the detection threshold are
    flagged.

    Configurable parameters:

    - ``relative_detection_factor`` (default: 0.5 %): minimum line-to-continuum ratio below which possible
      astronomical line features are ignored.
    - ``remove_n_extreme`` (default: 2): number of deviant Tsys profiles to ignore when building the
      comparison.

    The WebLog report shows three sections:

    1. Tsys plots similar to those from :py:func:`h_tsyscal <h_tsyscal>` / :py:func:`hifa_tsysflag <hifa_tsysflag>` but with the detected contaminated
       ranges already flagged.
    2. Diagnostic plots — a two-panel graph per source (CALIBRATE_ATMOSPHERE intent), per spw, per EB.
       The left panel shows the averaged Tsys toward the science fields (blue), toward the bandpass (orange),
       their difference (green), and an atmospheric opacity model (dashed red). Detected contamination ranges
       are shown in red. The right panel shows the difference corrected by the atmospheric model.

    .. figure:: /figures/uid___A002_X11c688d_Xad31.ms.tsyscontamination_spw22_field2.png
       :scale: 60%
       :alt: Diagnostic plot for hifa_tsysflagcontamination

       Example diagnostic plot. Left panel: averaged Tsys profile toward science fields (blue)
       and bandpass (orange), their difference plus a constant offset (green), atmospheric
       opacity model (dashed red), and detected contamination ranges (red). Right panel:
       difference corrected by the atmospheric model, with dual y-axis (K and approximate SNR).

    3. A flag summary table and the specific flag command template text.

    Notes:
        - QA = 1.0 if no Tsys contamination detected.
        - QA = 0.9 if contamination ranges were detected and flagged.
        - QA = 0.6 with a warning message in any of the following cases:

          - 'Large difference between the bandpass telluric line and...' — an uncorrected telluric residual
            may also appear in the autocorrelations and may need manual flagging in :py:func:`hifa_renorm <hifa_renorm>`.
          - 'Astronomical contamination covering a wide frequency range...' — the identified range is too
            wide to be reliable; no flagging was done.
          - 'Large residuals...' — the hypothesis that Tsys profiles should be similar is not fulfilled;
            results may be unreliable (possibly caused by very broad line contamination).
          - 'Heuristic not applied:...' — the input data are not supported (multi-source multi-tuning,
            double-sideband Bands 9/10, or full-polarization data); no flags applied.
        - QA = -0.1 if the task did not run correctly.

        Not applied in diffgain or full-pol recipes.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Flag Tsys line contamination using currently recommended parameters:

        >>> hifa_tsysflagcontamination()

        2. Halt pipeline execution if a failure occurs in the underlying heuristic:

        >>> hifa_tsysflagcontamination(continue_on_failure=False)

    """
