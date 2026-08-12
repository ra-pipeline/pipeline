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

    The procedure for the phase calibration process is as follow:

    - ``reference`` calibration uses the "reference" spectral setup, the "low"
      frequency for band-to-band observations (this uses the intent DIFFGAINREF,
      as implemented since PL2024). The solint is fixed as 'inf' (i.e.
      solutions are made per scan). Spectral window combination is governed by
      the hm_spwmapmode options described below. In standard pipeline operation
      ``auto`` is used - basing spw combination upon SNR and flagging level.
      These reference phase solutions are later applied on-the-fly while solving
      the (band-to-band) ``phase offset``. The premise being that the ``reference``
      solutions correct for atmospheric phase variability.

    - ``phase offset`` (i.e. the band-to-band correction) calibration uses the
      "on-source" spectral setup, the "high" frequency for band-to-band observations.
      The above ``reference`` phase corrections are applied on-the-fly using a
      linearPD interpolation - this corrects (scales) the phases according to the
      different ratio of the frequency bands. The solint = 'inf' and each group of
      scan blocks (combining groups of DIFFGAINSRC HF scans typically at the start
      and end of the observation) are combined respectively. The phase offset
      solution generally comprises of 2 time solutions per spw, per polarization
      (effectively the instrumental offset between bands). If the observation is long,
      approaching two hours, it is possible that there is an additional DIFFGAIN
      observation also at the mid-point of the observations, thus making 3 scan groups,
      and 3 solutions per spw per polarization. Spectral window combination is governed
      by the hm_spwmapmode options described below. ``auto`` is used - basing spw
      combination upon SNR and flag data. These solutions are stored in the
      pipeline context for later application to the TARGET and CHECK intent(s).

    - ``residual offset`` solutions are produced by applying both ``reference`` and
      band-to-band ``phase offset`` solutions to the 'on-source' DIFFGAIN intent
      on-the-fly, and subsequently solving phases per spw, per scan using
      solint='inf'.  Spectral window combination is governed by the hm_spwmapmode
      options described below. ``auto`` is used - basing spw combination upon SNR
      and flagging level.

    Residual solutions pre-apply all corrections and solve for the scan-based DIFFGAINSRC phases. These are
    designed to scatter about zero degrees with no drift, as shown in the figure below (right panel). Residuals
    not limited by SNR should ideally be within +/-30 deg; good-conditions data should be within +/-50 deg.
    There should be no significant offset or outlier solutions from the base zero degree phase.

    .. list-table:: Diffgain Phase Correction and Residuals
       :widths: 1 1

       * - .. image:: /figures/uid___A002_X116120b_X2d3a.ms.hifa_diffgaincal.s17_3.spw45_47_49_51_53_55_57_59.solintinf.gpcal.tbl-spw47-TARGET_CHECK-phase_vs_time.png
         - .. image:: /figures/uid___A002_X116120b_X2d3a.ms.hifa_diffgaincal.s17_5.spw45_47_49_51_53_55_57_59.solintinf.gpcal.tbl-spw55-phase_vs_time.png

    Plots in the hifa_diffgaincal weblog. The first set (left) shows the diffgain phase correction to be applied to the
    target source (the band-to-band offset). A plot is shown for each spectral window, with phase correction data
    points plotted per antenna and correlation as a function of time. The phase offsets are computed by pre-applying
    the LF scan based phase-only solution to the diffgain calibrator data and computing new phase solutions for each
    spw while combining scan groups at the start and end of the EB. The second set (right) shows the diffgain phase
    residuals as a function of time. The residual phase solutions should scatter about zero with no drift and are
    calculated by pre-applying the LF to HF phase solutions and the band-to-band offset. The new solutions are not
    applied to the target.

    As of PL2025, low-SNR heuristics allow ``combine='spw'`` to be used in any of the three solve steps.
    The gaincal workflow and low SNR logical flow are shown in the figure below.

    .. figure:: /figures/PL2025_hifa_diffgaincal_incHeuristic.png
       :scale: 60%
       :alt: Gain solution workflow for hifa_diffgaincal

       Left: gain solution workflow with low-SNR heuristic before each ``gaincal``.
       Right: low-SNR heuristic logic for spectral window combination.

    The heuristic is triggered if:
    
    1. ``combine='spw'`` was triggered as required for the phase-up (in :py:func:`hifa_spwphaseup <hifa_spwphaseup>`
       for the DIFFGAIN intent - using the relevant REF or the SRC). The previously computed SNR and ``solint``
       are used to calculate whether spw combination is required for the scan based phase solves, or in the case
       of the band-to-band offset - the group of scans, as to meet an SNR of 5.0. If this SNR threshold is not met,
       spw combination is triggered.
    2. A temporary ``gaincal`` shows that (i) not all spw solutions are made; (ii) the fraction of flagged solutions
       exceeds 0.7 of the total solutions, and (iii) the fraction of missing scans exceeds 0.7 of the expected scans.

    Notes:
        QA sub-scores:

        - 1.0 if each caltable (reference, band-to-band offset, residual) is successfully produced;
          0.0 if any table is missing (which invalidates the calibration).
        - 0.9 (informative only) if ``combine='spw'`` was required for any of the three solve steps;
          1.0 otherwise.

        Only used in band-to-band (diffgain) recipes.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Derive SpW phase offsets from differential gain calibrator.

        >>> hifa_diffgaincal()

    """
