import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.spwphaseup.spwphaseup.SpwPhaseupInputs.__init__
@utils.cli_wrapper
def hifa_spwphaseup(vis=None, caltable=None, field=None, intent=None, spw=None, hm_spwmapmode=None, maxnarrowbw=None,
                    minfracmaxbw=None, samebb=None, phasesnr=None, intphasesnr=None, intphasesnrmin=None,
                    phaseupmaxsolint=None, bwedgefrac=None, hm_nantennas=None, maxfracflagged=None, combine=None,
                    refant=None, minblperant=None, minsnr=None, unregister_existing=None):
    """Compute phase calibration spw map/combine mode, solution parameters, per spw phase offsets and phase decoherence.

    :func:`~pipeline.hifa.cli.hifa_spwphaseup` performs three main functions:

    - Determines the spectral window mapping or combination mode, ``gaintype`` and
      ``solint``, for each independent BANDPASS, AMPLITUDE, DIFFGAIN, PHASE and CHECK
      source, to use when specifically solving the phaseup - phase as a function of (short, ideally integration)
      time - in subsequent stages (mapping/combine mode isused in :func:`~pipeline.hifa.cli.hifa_gfluxscaleflag`,
      combine mode is used in :func:`~pipeline.hifa.cli.hifa_diffgaincal` for band-to-band modes, all parameters
      are used in :func:`~pipeline.hifa.cli.hifa_gfluxscale` and :func:`~pipeline.hifa.cli.hifa_timegaincal`).

    - Computes the per spectral window phase offset table (using
      the BANDPASS calibrator by default) that will be applied
      to the data to remove mean phase differences between the spectral windows.

    - Compute the baseline based phase RMS using the phaseup solutions generated for the BANDPASS intent.
      The phase RMS measured over a given timescale can provide insights about (de)coherence.

    **Determining mapping.combine mode and solint/gaintype**
   
    As part of the first function, if ``hm_spwmapmode='auto'``, then the spectral
    window mapping or combination mode, ``gaintype`` and ``solint``, are computed for
    each SpectralSpec and each intent, using the following algorithm (see the workflow diagram):

    - Estimate the per-spectral-window (spw) signal-to-noise ratio (SNR) based on
      catalog flux densities, Tsys, number of antennas, and integration and scan times.
      These SNR estimates are shown in the WebLog.

    - Compute the per-spw SNR for each intent based on a temporary phaseup gain
      calibration using ``solint='inf'`` for the PHASE and CHECK intents, or
      ``solint='int'`` otherwise, and ``gaintype='G'``. These computed SNR
      values override the use of the estimated values unless there is a problem creating
      the temporary table.

    - If both SNR calculations fail, then subsequent heuristics are skipped, warnings
      are printed, and the mapping mode falls back to a narrow-to-wide. The narrow-to-wide
      maps narrow spws to the nearest wide spw.

    - Compare the SNR for all spectral windows compared to ``phasesnr``
      for the PHASE or CHECK intents, and ``intphasesnr`` for the other
      intents. The PHASE and CHECK intents are referenced to a ``solint='inf'``
      and ``phasesnr`` while ``intphasesnr`` is used for other intents and
      reference to gaincal solutions using ``solint='int'``. The ideal ``solint``
      for phaseup is 'int', as part of which the workflow will establish, yet
      the PHASE and CHECK intents are referenced to ``solint='inf'``
      as these intents can be too weak such that initial estimates using
      ``solint='int'`` in :func:`~casatasks.calibration.gaincal` could fail.
    
      - If the SNR of all spws for a given intent is greater than the respective ``phasesnr``
        or ``intphasesnr`` then (1) set ``solint='int'`` and ``gaintype='G'``.

      - If the SNR of only some spws are greater than the value of
        ``phasesnr`` or ``intphasesnr`` respectively, then (2) each
        low-SNR spw is mapped to the highest SNR spw
        in the same SpectralSpec. Set ``solint='int'`` and ``gaintype='G'``.
    
      - If all spws have low SNR (or all spws in a given SpectraSpec for
        multi-SpectralSpec observations), then spws are combined and the SNR
        recomputed. If the  aggregate bandwidth SNR (per SpectralSpec) is now above
        the respective ``phasesnr`` or ``intphasesnr``, then (3) set ``combine='spw'``,
        ``solint='int'`` and ``gaintype='G'``.

      - If the aggregate bandwidth SNR is still not enough, change the ``gaintype`` to ``'T'`` to
        combine polarizations. Then, if the SNR is above ``phasesnr`` or ``intphasesnr``
        for the selected intent, use (4) ``combine='spw'``, ``solint='int'`` and ``gaintype='T'``.
        In the case that the intent is AMPLITUDE, the ``intphasesnr`` threshold is lowered to
        ``intphasesnrmin`` before moving to the next steps where ``solint`` can increase.

      - If the aggregate bandwidth SNR after combining spws and polarizations still does not meet the
        respective thresholds, ``solint`` is increased as to achieve the effective SNR threshold for
        for the reference timescale:

        - for the PHASE or CHECK intent, then (5) the ``solint`` has to be a multiple of the
          integration time between twice the integration time and half the scan time.
          If there is no suitable multiple, use a quarter of the scan time ('inf'/4). Otherwise,
          if the computed ``solint`` exceeds the scan time then (6) fix to half the scan time ('inf'/2).

        - for other intents, (5) compute ``solint`` as a multiple of the integration time
          up to the limit of ``maxphaseupsolint``. If the limit is exceeded, then (6) fix
          ``solint = maxphaseupsolint``
    
    .. figure:: /figures/PL2025_lowSNR_spwphaseup_v1.png
       :width: 60%
       :alt: Logic flowchart for spw phase-up strategy

       Logic flowchart for determining the temporal gain strategy. Extends
       phase-up mapping/combine, ``solint`` and ``gaintype`` calculation to
       all intents except the Polarization calibrator.
    
    If ``hm_spwmapmode='combine'``, :func:`~pipeline.hifa.cli.hifa_spwphaseup` maps all the science windows
    to a single science spectral window with a given SpectralSpec. For example, if the list of science
    spectral windows is ``[9, 11, 13, 15]`` then all the science spectral windows
    in the data will be combined and mapped to the science window ``9`` in the
    combined phase vs time calibration table. Establishing ``solint`` and ``gaintype`` begins
    from point (3). If no SNRs are found, then the PHASE and CHECK
    intents will default to a ``solint`` of one quarter of the scan time ('inf'/4)
    and ``gaintype='T'``, while other intents use ``solint='int'`` and ``gaintype='G'``. 

    If ``hm_spwmapmode='simple'``, the default ``solint='int'`` and ``gaintype='G'``
    are used, while a mapping from narrow science to wider science spectral windows
    is computed using the following algorithm:

    - Establish all science spectral windows per SpectralSpec.

    - Identify within each SpectralSpec the spw with the highest SNR.

    - For each science spectral window assess the SNR:

      - If the SNR exceeds the threshold, map the spw to itself.

      - If the highest SNR spw of the SpectralSpec exceeds the threshold
        map to that spw.

      - If no SNR reach the threshold or no SNR are found, map the spw to itself
        while passing an internal warning that no good spw maps were established.

    If ``hm_spwmapmode='default'``, the spw mapping is assumed to be one to one,
    with default ``solint='int'`` and ``gaintype='G'``. 

    **Per spectral window phase offsets**
    
    For the second functionality, the phase offsets per spectral window are determined by
    computing a phase only gain calibration on the selected data, normally the high
    SNR BANDPASS calibrator observations, using the solution interval ``solint='inf'``.

    At the end of these tasks the spectral window map, combine mode, ``solint``
    and ``gaintype`` along  with the phase offset calibration table(s) are stored in
    the pipeline context for use by later tasks.

    **Phase decoherence assessment**

    Using the bandpass phase-up solutions from :func:`~pipeline.hifa.cli.hifa_bandpass`, the baseline-based phase RMS is reconstructed
    from each antenna relative to the reference antenna. For each baseline the phase RMS is calculated over
    the entire bandpass scan (total-time) and also over a period equal to the phase referencing cycle time.
    The median phase RMS of all baselines longer than the 80th percentile is reported in the WebLog table.

    Outlier antennas (phase RMS > 180 deg, or > 4 x MAD + median when median > 50 deg, or > max(6 x MAD + median,
    2 x median) when median <= 50 deg) are identified and shown as semi-transparent symbols in the plot (see below). When
    outliers are found above 50 deg, a reassessment is made excluding them.

    .. figure:: /figures/hifa_spwphaseup_phasedeco_PL2022.png
       :width: 60%
       :alt: Phase decoherence plots

       Example phase decoherence plots (phase RMS vs. baseline length). Semi-transparent
       points indicate excluded outlier antennas. Horizontal coloured lines show the
       decoherence thresholds at 30 deg, 50 deg, and 70 deg.

    Notes:

        QA sub-scores for SNR:

        - The SNR of the calibration solutions are inspected and if the median
          value on a per-spw basis does not reach specific thresholds, a warning is
          issued with a reduced QA score.

          - For PHASE intent, blue, yellow, and red QA
            result if the achieved SNR is less than 0.75, 0.5, and 0.33 times ``phasesnr``,
            respectively.
          - For BANDPASS, AMPLITUDE, and DIFFGAIN intents, QA messages are
            based on 0.75, 0.5, and 0.33 times ``intphasesnr`` (unless ``intphasesnrmin``
            was used for intent AMPLITUDE, and BANDPASS if the same field).
          - For CHECK intent the QA score is always blue, but
            scales (0.67 - 0.9) depending on achieved SNR relative to ``phasesnr``.
    
        QA sub-scores for phase decoherence:

        - Phase RMS < 30 deg (excellent stability): QA = 1.0 (or 0.9 if outlier antennas detected).
        - Phase RMS 30-50 deg (good stability): QA = 0.9.
        - Phase RMS 50-70 deg (notably elevated): QA between 0.3 and 0.5.
        - Phase RMS > 70 deg (poor stability): QA between 0.0 and 0.3.

        Phase RMS of 30 deg, 50 deg, and 70 deg correspond to flux decoherence of ~13%, ~32%, and ~53% respectively
        for a point source with Gaussian phase noise. These thresholds are shown as coloured horizontal
        lines in the phase decoherence plots.

        The overall stage score is the lowest of the gain calibration QA and the phase decoherence QA.

    Examples:
        1. Compute the default spectral window map and the per spectral window phase offsets:

        >>> hifa_spwphaseup()

        2. Compute the default spectral window map and the per spectral window phase offsets while
        setting the spectral window mapping mode to 'combine':

        >>> hifa_spwphaseup(hm_spwmapmode='combine')

    """
