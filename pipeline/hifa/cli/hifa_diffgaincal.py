import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.diffgaincal.diffgaincal.DiffGaincalInputs.__init__
@utils.cli_wrapper
def hifa_diffgaincal(vis=None, flagging_frac_limit=None, hm_spwmapmode=None, missing_scans_frac_limit=None):
    """Derive SpW phase offsets from differential gain calibrator.

    This task creates the spectral window phase offset table used to allow
    calibrating the "on-source" spectral setup with phase gains from a
    "reference" spectral setup. Currently this setup with two different
    SpectralSpecs is used by the band-to-band mode, for a high and low
    frequency band.

    A bright point source quasar, called the Differential Gain Calibrator
    (DIFFGAIN) source, is used for this purpose. This DIFFGAIN source is typically
    observed in groups of interleaved "reference" and "on-source" scans. These
    blocks typically occur once at the start and once at the end of the
    observation. In very long observations, there may be a group of scans
    occurring during the middle.

    The task first performs a temporary phase solution on the low frequency
    "reference" data using ``solint='inf'``. Next, the "phase offset" solution
    using the high frequency "on-source" data is made with scan combination.
    Separately combining those scan encompassing the "start" and "end" DIFFGAIN
    blocks respectively. The "reference" gaintable is also pre-applied. Finally,
    temporary "residual" phase solutions are produced using the high frequency
    data with ``solint='inf'`` while both the "reference" and "phase offset"
    phase solutions are pre-applied.

    The "residual" solutions are designed as to scatter about zero degrees phase
    with no drift, as shown in the figure below (right panel). The "residuals"
    not limited by SNR should ideally be within +/-30 deg; acceptable-conditions data
    should be within +/-50 deg. There should be no significant offset or outlier
    solutions from the base zero degree phase. QA sub-scores are described below.

    For all solves ``refantmode='strict'`` is used, such that the reference 
    antenna as established in :func:`~pipeline.hif.cli.hif_refant` cannot be swapped
    when data are flagged. If solutions are poor, one should investigate fixing
    the reference antenna.

    .. list-table:: Diffgain Phase Correction and Residuals
       :widths: 1 1

       * - .. image:: /figures/uid___A002_X116120b_X2d3a.ms.hifa_diffgaincal.s17_3.spw45_47_49_51_53_55_57_59.solintinf.gpcal.tbl-spw47-TARGET_CHECK-phase_vs_time.png
         - .. image:: /figures/uid___A002_X116120b_X2d3a.ms.hifa_diffgaincal.s17_5.spw45_47_49_51_53_55_57_59.solintinf.gpcal.tbl-spw55-phase_vs_time.png

    **Plots in the weblog**: The first set (left) shows the diffgain phase correction to be applied to the
    target source (the band-to-band offset). A plot is shown for each spectral window, with phase correction data
    points plotted per antenna and correlation as a function of time. The second set (right) shows the DIFFGAIN phase
    residuals as a function of time. The residual phase solutions should scatter about zero with no drift or outliers.

    As of PL2025, low-SNR heuristics allow ``combine='spw'`` to be used in any of the three solve steps.
    The gaincal workflow and low SNR logical flow are shown in the figure below.

    .. figure:: /figures/PL2026_hifa_diffgaincal_incHeuristic_lowSNR.png
       :width: 60%
       :alt: Gain solution workflow for hifa_diffgaincal

       Left: gain solution workflow with low-SNR heuristic before each ``gaincal``.
       Right: low-SNR heuristic logic for spectral window combination.

    The heuristic is triggered if:
    
    1. ``combine='spw'`` was triggered as required for the phase-up (in :func:`~pipeline.hifa.cli.hifa_spwphaseup`
       for the DIFFGAIN intent - using the relevant REF or the SRC). The previously computed SNR and ``solint``
       are used to calculate whether spw combination is required for the scan based phase solves, or in the case
       of the band-to-band offset - the group of scans, as to meet an SNR of 5.0. If this SNR threshold is not met,
       spw combination is triggered.
    2. A temporary ``gaincal`` shows that (i) not all spw solutions are made; (ii) the fraction of flagged solutions
       exceeds 0.5 of the total solutions, and (iii) the fraction of missing scans exceeds 0.7 of the expected scans.

    Notes:
        QA sub-scores:

        - 1.0 if each caltable (reference, band-to-band offset, residual) is successfully produced;
          0.0 if any table is missing (which invalidates the calibration).
        - 0.9 (informative only) if ``combine='spw'`` was required for any of the three solve steps;
          1.0 otherwise.
        - Residual solution phase offsets, rms, outliers:
            - 1.0 if phase `parameter` is <30 deg
            - 0.9 if phase `parameter` is between 30-50 deg
            - 0.67 if phase `parameter` is between 50-70 deg
            - 0.66 if phase `parameter` >=70 deg

        :func:`~pipeline.hifa.cli.hifa_diffgaincal` is only used in band-to-band (diffgain) recipes, but other 
        required pipeline tasks are DIFFGAIN-aware and handle band-to-band data correctly.

    Examples:
        1. Derive SpW phase offsets from differential gain calibrator.

        >>> hifa_diffgaincal()

        2. Derive SpW phase offsets while using SpW combination for the high-frequency ``'offset'`` solve only.

        >>> hifa_diffgaincal(hm_spwmapmode='offset')

    """
