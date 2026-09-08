# ALMA Pipeline Known Issues


## PL2026

**2026.2.0.XX**

### CASA

1. In {func}`~casatasks.imaging.tclean` `briggsbwtaper`, the fractional bandwidth is calculated per-chunk, so parallelizing with different breadth gives different answers ([CAS-14520](https://open-jira.nrao.edu/browse/CAS-14520) and {jira}`PIPE-2832`).
2. **{func}`~pipeline.hifa.cli.hifa_wvrgcalflag`** will crash on source names that are integers because the CASA task [wvrgcal](https://casadocs.readthedocs.io/en/v6.6.6/api/tt/casatasks.calibration.wvrgcal.html) no longer supports them ([CAS-14850](https://open-jira.nrao.edu/browse/CAS-14850)).

### Both Pipelines

### Interferometric Pipeline

1. **{func}`~pipeline.hif.cli.hif_uvcontsub`** will not skip spws that have "NONE" in cont.dat. This situation doesn't arise in operations, but could arise if someone manually edits cont.dat ({jira}`PIPE-1898`)
2. If the check source is so faint that no gain solutions can be found, then **{func}`~pipeline.hifa.cli.hifa_gfluxscale`** will crash ({jira}`PIPE-1468`).
3. In (i) the polcal recipe and in (ii) the B2B recipe, if the selected session reference antenna is fully flagged on any spw by hifa_gfluxscaleflag, then **{func}`~pipeline.hifa.cli.hifa_gfluxscale`** will crash. The workaround is to set a different reference antenna (or list of reference antennas) in the {func}`~pipeline.hif.cli.hif_refant` task in the PPR ({jira}`PIPE-1664`).
4. On the Spectral Setup weblog page, multi-target datasets with multiple tunings not observed in all targets will not show the Transition names for spws associated with tunings beyond the first tuning ({jira}`PIPE-1909`).
5. In **{func}`~pipeline.hifa.cli.hifa_spwphaseup`**, (i) if the refant drops out for the majority of solutions, then the Median Phase RMS assessment cannot be made; (ii) if there is low SNR in the bandpass solutions and the refant jumps in phase, then some antennas can incorrectly be identified as outliers by the Median Phase RMS assessment; (iii) for B2B datasets, if the lowest index of the target spectral windows are fully flagged no assessment will be made.
6. **{func}`~pipeline.hifa.cli.hifa_gfluxscaleflag`** crashes on MOUS with EBs that straddle Cycle 2 and Cycle 3 ({jira}`PIPE-2691`).
7. The aggregate bandwidth listed on continuum **{func}`~pipeline.hif.cli.hif_makeimages`** pages does not account for the deterministic flagging of edge channels on TDM spws ({jira}`PIPE-2349`) and it does not account for spw overlap ({jira}`PIPEREQ-37`).
8. The **{func}`~pipeline.hifa.cli.hifa_tsysflagcontamination`** stage does not work for the B2B and full-polarization observing modes ({jira}`PIPE-2407`).
9. If ``combine='spw'`` is used in gaincal calls, pipeline will crash in **{func}`~pipeline.hifa.cli.hifa_gfluxscale`** if the lowest index spw is fully flagged ({jira}`PIPE-128`).
10. In some B2B data, where DIFFGAIN cal == BP cal, QA will give a red warning in **{func}`~pipeline.hifa.cli.hifa_gfluxscale`** but the stage and results are correct ({jira}`PIPE-2204`).
11. **{func}`~pipeline.hif.cli.hif_selfcal`** does not properly handle (or fails on) cases of multi-EB datasets where a spw is missing from some EBs ({jira}`PIPE-2770`).
12. **{func}`~pipeline.hifa.cli.hifa_spwphaseup`** may incorrectly conclude for single-pol data that using "gaintype=T" could eke out enough SNR to use solint=int ({jira}`PIPE-2840`).
13. In rare cases of old data (Cycle 1), chantol needs to be increased in **{func}`~pipeline.h.cli.h_tsyscal`** in the PPR in order for tsysspwmap to succeed on all spws ({jira}`PIPE-1440`).

### Single Dish Pipeline




---

## PL2025

**2025.1.0.35**

### CASA

1. Any 2 GHz dual-polarization ACA spws with 256 channels are identified as TDM instead of FDM on Spectral Setup page (due to [CAS-14435](https://open-jira.nrao.edu/browse/CAS-14435)).
2. In {func}`~casatasks.imaging.tclean` `briggsbwtaper`, the fractional bandwidth is calculated per-chunk, so parallelizing with different breadth gives different answers ([CAS-14520](https://open-jira.nrao.edu/browse/CAS-14520) and {jira}`PIPE-2832`).
3. {func}`~casatasks.visualization.plotbandpass` will not produce a plot of overlay='antenna' if there is only one antenna in the cal table ([CAS-14657](https://open-jira.nrao.edu/browse/CAS-14657)). This impacts the single dish pipeline in {func}`~pipeline.hsd.cli.hsd_skycal` if the MOUS contains only 1 antenna ({jira}`PIPE-2825`).
4. CASA versions < 6.6.6.18 incorrectly unwrapped phase when applying with linearPD interpolation. This could affect the calibration of B2B datasets.

### Both Pipelines

1. FDM spws that have a small number of channels (<=256/Ncorr, e.g. <=128 for dual-pol) will be interpreted incorrectly as TDM by {func}`~pipeline.hifa.cli.hifa_flagdata` resulting in unnecessary edge channel flagging (0.03125% from each edge). This can happen in 4x4 bit mode with online channel averaging factors >= 8 ({jira}`PIPE-2320`).

### Interferometric Pipeline

1. **{func}`~pipeline.hif.cli.hif_uvcontsub`** will not skip spws that have "NONE" in cont.dat. This situation doesn't arise in operations, but could arise if someone manually edits cont.dat ({jira}`PIPE-1898`)
2. If the check source is so faint that no gain solutions can be found, then **{func}`~pipeline.hifa.cli.hifa_gfluxscale`** will crash ({jira}`PIPE-1468`).
3. In (i) the polcal recipe and in (ii) the B2B recipe, if the selected session reference antenna is fully flagged on any spw by hifa_gfluxscaleflag, then **{func}`~pipeline.hifa.cli.hifa_gfluxscale`** will crash. The workaround is to set a different reference antenna (or list of reference antennas) in the {func}`~pipeline.hif.cli.hif_refant` task in the PPR ({jira}`PIPE-1664`).
4. On the Spectral Setup weblog page, multi-target datasets with multiple tunings not observed in all targets will not show the Transition names for spws associated with tunings beyond the first tuning ({jira}`PIPE-1909`).
5. In **{func}`~pipeline.hifa.cli.hifa_spwphaseup`**, (i) if the refant drops out for the majority of solutions, then the Median Phase RMS assessment cannot be made; (ii) if there is low SNR in the bandpass solutions and the refant jumps in phase, then some antennas can incorrectly be identified as outliers by the Median Phase RMS assessment.
6. FDM spws that have a small number of channels (<=256/Ncorr, e.g. <=128 for dual-pol) will be interpreted as TDM by **{func}`~pipeline.hifa.cli.hifa_flagdata`** resulting in unnecessary edge channel flagging (0.03125% from each edge). This can happen in 4x4 bit mode (first offered in Cycle 10) with online channel averaging factors >= 8 (PIPE-2320).
7. **{func}`~pipeline.hifa.cli.hifa_gfluxscaleflag`** crashes on MOUS with EBs that straddle Cycle 2 and Cycle 3 ({jira}`PIPE-2691`).
8. The aggregate bandwidth listed on continuum **{func}`~pipeline.hif.cli.hif_makeimages`** pages does not account for the deterministic flagging of edge channels on TDM spws ({jira}`PIPE-2349`) and it does not account for spw overlap ({jira}`PIPEREQ-37`).
9. The **{func}`~pipeline.hifa.cli.hifa_tsysflagcontamination`** stage does not work for the B2B and full-polarization observing modes ({jira}`PIPE-2407`).
10. For very low SNR data (HF and narrow spws), (i) **{func}`~pipeline.hif.cli.hif_lowgainflag`** may entirely flag 'good' spws that cannot be 'int' phased-up without spw combination. The workaround is to remove the stage in the PPR ({jira}`PIPE-2601`), (ii) related, in particular cases, **{func}`~pipeline.hifa.cli.hifa_wvrgcalflag`** will crash if the spw selected to make gains is full flagged. The workaround is also to remove the stage in the PPR.
11. If combine='spw' is used in gaincal calls, pipeline will crash in **{func}`~pipeline.hifa.cli.hifa_gfluxscale`** if the lowest index spw is fully flagged ({jira}`PIPE-128`).
12. In some B2B data, where DIFFGAIN cal == BP cal, QA will give a red warning in **{func}`~pipeline.hifa.cli.hifa_gfluxscale`** but the stage and results are correct ({jira}`PIPE-2204`).
13. **{func}`~pipeline.hif.cli.hif_selfcal`** does not properly handle (or fails on) cases of multi-EB datasets where a spw is missing from some EBs ({jira}`PIPE-2770`).
14. **{func}`~pipeline.hifa.cli.hifa_spwphaseup`** may incorrectly conclude for single-pol data that using "gaintype=T" could eke out enough SNR to use solint=int ({jira}`PIPE-2840`).
15. The DR reported in the **{func}`~pipeline.hif.cli.hif_makeimages`** weblog can be different for IQUV vs I imaging of the same data, due to how masks are re-used, however, that reported DR has no effect on the IQUV cleaning, because the threshold from I imaging is re-used directly, instead of calculating a new threshold from the new DR ({jira}`PIPE-2464`).
16. Science projects with multiple SpectralSpecs due to multiple targets that require spw mitigation will crash in **{func}`~pipeline.hif.cli.hif_checkproductsize`** ({jira}`PIPE-2812`).
17. In rare cases of old data (Cycle 1), chantol needs to be increased in **{func}`~pipeline.h.cli.h_tsyscal`** in the PPR in order for tsysspwmap to succeed on all spws ({jira}`PIPE-1440`).
18. **{func}`~pipeline.hif.cli.hif_selfcal`** will fail for single-polarization mosaic datasets with a warning that a self-calibration worker failed. This does not, however, impact the regcal data products ({jira}`PIPE-2908`).
19. **{func}`~pipeline.hif.cli.hif_selfcal`** for single-field single-polarization datasets will likely show >50% flagging for the inf_EB solution interval due to the use of gaintype='G' in gaincal and the collection of flagging stats from the resulting table, which has entirely flagged solutions for the missing table. This is merely cosmetic, however, and the self-calibration itself is not impacted (return of {jira}`PIPE-2086`).
20. **{func}`~pipeline.hifa.cli.hifa_gfluxscale`** will crash on B2B datasets that lack a CHECK_SOURCE observation ({jira}`PIPE-2694`).
21. PL version 2025.1.0.36, when a repBW cube was created, would sometimes only export one of the repBW cube and the full resolution cube for the same source and spw. This was corrected in 2025.1.0.37, and you can request the additional image from the helpdesk.
22. For some older ALMA datasets (Cycle 3 to Cycle 8), the Spectral Setup Details page of the weblog might show an incorrect value for Correlation Bits column instead of "Unknown" which is what it should show prior to Cycle 9 ({jira}`PIPE-3095`).
23. In the polcal imaging recipe, the repBW **{func}`~pipeline.hif.cli.hif_makeimages`(repBW_fullpol)** stage of the pipeline is not using the clean threshold and mask from the corresponding repBW {func}`~pipeline.hif.cli.hif_makeimages`(repBW) Stokes I only imaging stage ({jira}`PIPE-3128`); as a result no cleaning is performed.
24. **{func}`~pipeline.hifa.cli.hifa_wvrgcalflag`** will crash on source names that are integers because the CASA task [wvrgcal](https://casadocs.readthedocs.io/en/v6.6.6/api/tt/casatasks.calibration.wvrgcal.html) no longer supports them ([CAS-14850](https://open-jira.nrao.edu/browse/CAS-14850)).

### Single Dish Pipeline

1. In {func}`~pipeline.hsd.cli.hsd_flagdata`, there is a wrong unit (arcsec instead of degree) in the log message reporting max separation of pointing outlier ({jira}`PIPE-2920`).

---

## PL2024

**2024.1.0**

### CASA 2024

1. Any 2 GHz dual-polarization ACA spws with 256 channels are identified as TDM instead of FDM on Spectral Setup page (due to [CAS-14435](https://open-jira.nrao.edu/browse/CAS-14435)).
2. Plotbandpass will not produce a plot of overlay='antenna' if there is only one antenna in the cal table ([CAS-14657](https://open-jira.nrao.edu/browse/CAS-14657)). This impacts the single dish pipeline in {func}`~pipeline.hsd.cli.hsd_skycal` if the MOUS contains only 1 antenna ({jira}`PIPE-2825`).

### Both Pipelines 2024

1. The spw name column is missing from the All Spws tab of the Spectral Setup weblog page ({jira}`PIPE-1736`).
2. FDM spws that have a small number of channels (<=256/Ncorr, e.g. <=128 for dual-pol) will be interpreted incorrectly as TDM by {func}`~pipeline.hifa.cli.hifa_flagdata` resulting in unnecessary edge channel flagging (0.03125% from each edge). This can happen in 4x4 bit mode with online channel averaging factors >= 8 ({jira}`PIPE-2320`).

### Interferometric Pipeline 2024

1. {func}`~pipeline.hif.cli.hif_uvcontsub` will not skip spws that have "NONE" in cont.dat. This situation doesn't arise in operations, but could arise if someone manually edits cont.dat ({jira}`PIPE-1898`)
2. If the check source is so faint that no gain solutions can be found, then {func}`~pipeline.hifa.cli.hifa_gfluxscale` will crash ({jira}`PIPE-1468`).
3. In {func}`~pipeline.hifa.cli.hifa_antpos`, in the second table "Antenna Position Offsets Sorted By Total Offset", when there are two antennas with the same offset and the Total Offset column has a common value, the second antenna is not bolded in the same way as the first. ({jira}`PIPE-1631`).
4. In the polcal recipe, if the selected session reference antenna is fully flagged on any spw by {func}`~pipeline.hifa.cli.hifa_gfluxscaleflag`, then {func}`~pipeline.hifa.cli.hifa_gfluxscale` will crash. The workaround is to set a different reference antenna (or list of reference antennas) in the {func}`~pipeline.hif.cli.hif_refant` task in the PPR ({jira}`PIPE-1664`).
5. On the Spectral Setup weblog page, multi-target datasets with multiple tunings not observed in all targets will not show the Transition names for spws associated with tunings beyond the first tuning ({jira}`PIPE-1909`).
6. For heterogeneous array mosaics with 3 or more PM antennas included, if any field has only 1 baseline of data left unflagged after online flags and any prior stage flagging, then {func}`~pipeline.hifa.cli.hifa_targetflag` will crash ({jira}`PIPE-1879`).
7. In {func}`~pipeline.hifa.cli.hifa_spwphaseup`, (i) if the refant drops out for the majority of solutions, then the Median Phase RMS assessment cannot be made; (ii) if there is low SNR in the bandpass solutions and the refant jumps in phase, then some antennas can incorrectly be identified as outliers by the Median Phase RMS assessment.
8. FDM spws that have a small number of channels (<=256/Ncorr, e.g. <=128 for dual-pol) will be interpreted incorrectly as TDM by {func}`~pipeline.hifa.cli.hifa_flagdata` resulting in unnecessary edge channel flagging (0.03125% from each edge). This can happen in 4x4 bit mode with online channel averaging factors >= 8 ({jira}`PIPE-2320`).
9. The Tsys field indicator in the mosaic pattern plot on the Spatial Setup page doesn't account for the angular offset of the field ({jira}`PIPE-2067`).
10. {func}`~pipeline.hifa.cli.hifa_gfluxscaleflag` crashes on MOUS with EBs that straddle Cycle 2 and Cycle 3 ({jira}`PIPE-2691`).
11. The aggregate bandwidth listed on continuum {func}`~pipeline.hif.cli.hif_makeimages` pages does not account for the deterministic flagging of edge channels on TDM spws ({jira}`PIPE-2349`) and it does not account for spw overlap ({jira}`PIPEREQ-37`).
12. The {func}`~pipeline.hifa.cli.hifa_tsysflagcontamination` stage does not work for the B2B and full-polarization observing modes ({jira}`PIPE-2407`).
13. If combine='spw' is used in gaincal calls, pipeline will crash in {func}`~pipeline.hifa.cli.hifa_gfluxscale` if the lowest index spw is fully flagged ({jira}`PIPE-128`).
14. There are a few issues with **Band-to-Band datasets**:
    a. In some cases, the Tsys spectra shown in {func}`~pipeline.h.cli.h_tsyscal` and {func}`~pipeline.hifa.cli.hifa_tsysflag` do not show all the normal labels nor the atmospheric transmission curve. ({jira}`PIPE-2293`)
    b. The {func}`~pipeline.hifa.cli.hifa_tsysflagcontamination` stage does not work. ({jira}`PIPE-2009`)
    c. If a low-frequency SpW (reference) is fully flagged for the DIFFGAIN, this will not allow the paired High Frequency (Science On Source) SpW(s) to be calibrated and thus the SpW(s) get fully flagged for the Target(s). For Band 7 and 8, there is a 1:1 relation, for Band 9 and 10 with 90-degree Walsh there is a 1:2 relation. Main occurrence = B10 paired with B5 in 183 GHz water line.
    d. If the refant is not ideal, or partially flagged, then some gaincal solves will not complete. Work-around: refant can be manually specified.
    e. For very narrow spws, especially with 7m ACA, the SNR can be too low even on the DIFFGAIN intent — PL is likely to finish but some HF spws will end up flagged. This requires manual calibration to do spw-combination on DIFFGAIN calibrator.
    f. For all high frequency data (B2B or not) with narrow spws, there can be significant decorrelation even on the BANDPASS scan, which can affect the phase transfer and flux scale on those spws.
15. In rare cases of old data (Cycle 1), chantol needs to be increased in {func}`~pipeline.h.cli.h_tsyscal` PPR in order for tsysspwmap to succeed on all spws ({jira}`PIPE-1440`).
16. For some older ALMA datasets (Cycle 3 to Cycle 8), the Spectral Setup Details page of the weblog might show an incorrect value for Correlation Bits column instead of "Unknown" which is what it should show prior to Cycle 9 ({jira}`PIPE-3095`).

---

## PL2023

**2023.1.0.124**

### CASA 2023

1. Ephemeris imaging in MPIcasa remains unreliable. *PLWG recommends that due to this, all multi-EB ephemeris data be run in serial mode.*
2. The tclean parameter psfphasecenter is still not functioning ([CAS-13899](https://open-jira.nrao.edu/browse/CAS-13899)). If you want to image a mosaic with no data at phase center, then you should make the image larger and move the phase center to a pointing that has data.
3. Any 2 GHz dual-polarization spws with 256 channels on the ACA are identified as TDM instead of FDM on Spectral Setup page (due to [CAS-13362](https://open-jira.nrao.edu/browse/CAS-13362)).
4. Plotbandpass will not produce a plot of overlay='antenna' if there is only one antenna in the cal table ([CAS-14657](https://open-jira.nrao.edu/browse/CAS-14657)). This impacts the single dish pipeline in {func}`~pipeline.hsd.cli.hsd_skycal` if the MOUS contains only 1 antenna ({jira}`PIPE-2825`).

### Both Pipelines 2023

1. PL2023 uses python3.8. Some user machines may find dependency issues if they only have python3.6 available.
2. The spw name column is missing from the All Spws tab of the Spectral Setup weblog page ({jira}`PIPE-1736`).
3. FDM spws that have a small number of channels (<=256/Ncorr, e.g. <=128 for dual-pol) will be interpreted incorrectly as TDM by {func}`~pipeline.hifa.cli.hifa_flagdata` resulting in unnecessary edge channel flagging (0.03125% from each edge). This can happen in 4x4 bit mode with online channel averaging factors >= 8 ({jira}`PIPE-2320`).

### Interferometric Pipeline 2023

1. {func}`~pipeline.hif.cli.hif_uvcontsub` will not skip spws that have "NONE" in cont.dat. This situation doesn't arise in operations, but could arise if someone manually edits cont.dat ({jira}`PIPE-1898`)
2. {func}`~pipeline.hif.cli.hif_selfcal` will fail for multi-EB single field projects with virtual spws — this is quite rare outside of polarization, and self-calibration of full-polarization projects is not fully validated in any case ({jira}`PIPE-1927`).
3. If the check source is so faint that no gain solutions can be found, then {func}`~pipeline.hifa.cli.hifa_gfluxscale` will crash ({jira}`PIPE-1468`).
4. An irregular mosaic with no pointing at the geometric center will likely fail, and the pipeline will warn you of this likelihood. Until the CASA bug with psfphasecenter is resolved ([CAS-13899](https://open-jira.nrao.edu/browse/CAS-13899)), create a larger image and put the phasecenter at a pointing with data. ({jira}`PIPE-98`)
5. In {func}`~pipeline.hifa.cli.hifa_antpos`, in the second table "Antenna Position Offsets Sorted By Total Offset", when there are two antennas with the same offset and the Total Offset column has a common value, the second antenna is not bolded in the same way as the first. ({jira}`PIPE-1631`).
6. In the polcal recipe, if the selected session reference antenna is fully flagged on any spw by {func}`~pipeline.hifa.cli.hifa_gfluxscaleflag`, then {func}`~pipeline.hifa.cli.hifa_gfluxscale` will crash. The workaround is to set a different reference antenna (or list of reference antennas) in the {func}`~pipeline.hif.cli.hif_refant` task in the PPR ({jira}`PIPE-1664`).
7. In the polcal recipe, {func}`~pipeline.hifa.cli.hifa_gfluxscale` can fail silently (pausing pipeline permanently) if the refant has 100% flagging on only 1 of the transfer targets (typically either PHASE or CHECK source) and it still exhibits the best score in {func}`~pipeline.hif.cli.hif_refant` ({jira}`PIPE-1805`). The workaround is to set geometry=False in {func}`~pipeline.hif.cli.hif_refant`.
8. On the Spectral Setup weblog page, multi-target datasets with multiple tunings not observed in all targets will not show the Transition names for spws associated with tunings beyond the first tuning ({jira}`PIPE-1909`).
9. For heterogeneous array mosaics with 3 or more PM antennas included, if any field has only 1 baseline of data left unflagged after online flags and any prior stage flagging, then {func}`~pipeline.hifa.cli.hifa_targetflag` will crash ({jira}`PIPE-1879`).
10. In {func}`~pipeline.hifa.cli.hifa_spwphaseup`, (i) if the refant drops out for the majority of solutions, then the Median Phase RMS assessment cannot be made; (ii) if there is low SNR in the bandpass solutions and the refant jumps in phase, then some antennas can incorrectly be identified as outliers by the Median Phase RMS assessment.
11. ACA projects with multiple single-spw FDM tunings might experience odd flagging of non-edge channels ({jira}`PIPE-1991`). The work-around is to set edgespw=False in {func}`~pipeline.hifa.cli.hifa_flagdata`.

> *Items below this point were discovered after the PL2023 Google slides were released and frozen:*

12. In {func}`~pipeline.hif.cli.hif_findcont`, spws with a single range of continuum channels identified might be declared AllCont even if they contain a significantly lesser amount of continuum than the nominal threshold of 91% ({jira}`PIPE-2034`).
13. In {func}`~pipeline.hifa.cli.hifa_bandpass`, the plots of phase vs. frequency can take a long time to display in the weblog due to a change in behavior of a mathematical function due to an upgrade in the scipy version packaged with the pipeline ({jira}`PIPE-2035`).
14. In full-polarization datasets, the {func}`~pipeline.hif.cli.hif_makeimages` page for the polcal has images of polarized intensity; the ">_" link which usually produces a popup with the tclean command, in this case just dims the screen without revealing a tclean command, because the image was not made with tclean. Clicking the image background will refresh the screen.
15. FDM spws that have a small number of channels (<=256/Ncorr, e.g. <=128 for dual-pol) will be interpreted incorrectly as TDM by {func}`~pipeline.hifa.cli.hifa_flagdata` resulting in unnecessary edge channel flagging (0.03125% from each edge). This can happen in 4x4 bit mode (offered first in Cycle 10) with online channel averaging factors >= 8 ({jira}`PIPE-2320`).
16. The Tsys field indicator in the mosaic pattern plot on the Spatial Setup page doesn't account for the angular offset of the field ({jira}`PIPE-2067`).
17. The {func}`~pipeline.hif.cli.hif_applycal` page can fail to render if the uv coverage plot fails to be made due to flagging of data ({jira}`PIPE-1294`).
18. Phase structure plots in {func}`~pipeline.hifa.cli.hifa_spwphaseup` will fail if the widest spw was flagged earlier ({jira}`PIPE-1871`).
19. {func}`~pipeline.hifa.cli.hifa_gfluxscaleflag` crashes on MOUS with EBs that straddle Cycle 2 and Cycle 3 ({jira}`PIPE-2691`).
20. The aggregate bandwidth listed on continuum {func}`~pipeline.hif.cli.hif_makeimages` pages does not account for the deterministic flagging of edge channels on TDM spws ({jira}`PIPE-2349`) and it does not account for spw overlap ({jira}`PIPEREQ-37`).
21. If combine='spw' is used in gaincal calls, pipeline will crash in {func}`~pipeline.hifa.cli.hifa_gfluxscale` if the lowest index spw is fully flagged ({jira}`PIPE-128`).
22. In rare cases of old data (Cycle 1), chantol needs to be increased in {func}`~pipeline.h.cli.h_tsyscal` PPR in order for tsysspwmap to succeed on all spws ({jira}`PIPE-1440`).
23. For some older ALMA datasets (Cycle 3 to Cycle 8), the Spectral Setup Details page of the weblog might show an incorrect value for Correlation Bits column instead of "Unknown" which is what it should show prior to Cycle 9 ({jira}`PIPE-3095`).

---

## PL2022.2

2022.2.0.64 used Oct 2022 – April 2023

2022.2.0.68 used April 2023 – Oct 2024, fixes some of the issues below, as noted.

### CASA 2022

1. A bug in imaging ephemeris cubes ([CAS-13908](https://open-jira.nrao.edu/browse/CAS-13908)) will sometimes cause part of the cube being erroneously empty, clearly visible in the pipeline spectrum under "other QA images". *PLWG recommends that due to this, all multi-EB ephemeris data be run in serial mode.*
2. The tclean parameter psfphasecenter is currently not functioning ([CAS-13899](https://open-jira.nrao.edu/browse/CAS-13899)). If you want to image a mosaic with no data at phase center, then you should make the image larger and move the phase center to a pointing that has data.
3. Plotbandpass will not produce a plot of overlay='antenna' if there is only one antenna in the cal table ([CAS-14657](https://open-jira.nrao.edu/browse/CAS-14657)). This impacts the single dish pipeline in {func}`~pipeline.hsd.cli.hsd_skycal` if the MOUS contains only 1 antenna ({jira}`PIPE-2825`).

### Both Pipelines 2022

1. PL2022 doesn't import on MacOS — PL was never fully supported on MacOS, and unfortunately this one doesn't work at all. ***Fixed in 2022.2.0.68***
2. 2 GHz dual-polarization spws with 256 channels on the ACA are identified as TDM instead of FDM on Spectral Setup page (due to [CAS-13362](https://open-jira.nrao.edu/browse/CAS-13362)).
3. The spw name column is missing from the All Spws tab of the Spectral Setup weblog page ({jira}`PIPE-1736`).

### Interferometric Pipeline 2022

1. If the check source is so faint that no gain solutions can be found, then {func}`~pipeline.hifa.cli.hifa_gfluxscale` will crash ({jira}`PIPE-1468`).
2. An irregular mosaic with no pointing at the geometric center will likely fail, and the pipeline will warn you of this likelihood. Until the CASA bug with psfphasecenter is resolved ([CAS-13899](https://open-jira.nrao.edu/browse/CAS-13899)), create a larger image and put the phasecenter at a pointing with data. ({jira}`PIPE-98`)
3. The atmospheric transmission curves overlaid in {func}`~pipeline.h.cli.h_tsyscal`, {func}`~pipeline.hifa.cli.hifa_tsysflag`, and {func}`~pipeline.hifa.cli.hifa_bandpass` will be incorrect if any weather stations have non-sensical pressure data. ([CAS-13910](https://open-jira.nrao.edu/browse/CAS-13910))
4. This version of the pipeline won't run on Cycle 2 and earlier data that were labeled J2000 frame because astropy does not recognize J2000. The workaround is to set {func}`~pipeline.hifa.cli.hifa_flagdata`(lowtrans=False) in the PPR ({jira}`PIPE-1575` → *fixed PL2023*).
5. For Single-pol data (there are none in C8, 2 approved C-rank in C9, so very rare):
   - The new calculation of achieved SNR in {func}`~pipeline.hifa.cli.hifa_spwphaseup` will issue a spurious red QA warning that the achieved SNR is zero — the actual calibration and data are fine, this is only a bug in the QA score calculation ({jira}`PIPE-1623`).
   - Inaccurate warning and QA score in {func}`~pipeline.hifa.cli.hifa_spwphaseup` (PIPE-1625).
   - The new phase offsets QA score in {func}`~pipeline.hifa.cli.hifa_timegaincal` fails ({jira}`PIPE-1628`).
   - {func}`~pipeline.h.cli.h_tsyscal` (hifa_tsyscal at the time) or {func}`~pipeline.hifa.cli.hifa_tsysflag` *might* fail due to the recent change to single-pol Tsys (ICT-15219), not communicated to the PL team and for which no E2E9 data were acquired.
6. Band 5 data with science spws overlapping with the WVR spws might fail in hif_uvcontfit because of a CASA bug ([CAS-13843](https://open-jira.nrao.edu/browse/CAS-13843)) in calculating TOPO ranges for such spws ({jira}`PIPE-1530`). The workaround is to set a suitable continuum selection range for (only) the failing spw(s) in cont.dat prior to re-running the pipeline.
7. In {func}`~pipeline.hifa.cli.hifa_antpos`, in the second table "Antenna Position Offsets Sorted By Total Offset", when there are two antennas with the same offset and the Total Offset column has a common value, the second antenna is not bolded in the same way as the first. ({jira}`PIPE-1631`).
8. In {func}`~pipeline.hifa.cli.hifa_gfluxscaleflag`, the flagging summary table does not reflect flagging applied to the TARGET intent when flags for bad baselines are propagated from PHASE cal ({jira}`PIPE-1630`).
9. In {func}`~pipeline.hifa.cli.hifa_spwphaseup`, (i) if several antennas of a CM+PM heterogeneous dataset are flagged on the bandpass calibrator, then the value of the Median Phase RMS in the table will be NaN and the QA score will be 0.0 ({jira}`PIPE-1633`); (ii) if the refant drops out for the majority of solutions the Median Phase RMS assessment cannot be made; (iii) if there is low SNR in the bandpass solutions and the refant jumps in phase then some antennas can incorrectly be identified as outliers by the Median Phase RMS assessment; (iv) the phase structure function plots are calculated from antenna-based gains, so baseline-based flags will not be reflected in the plot.
10. For {func}`~pipeline.hif.cli.hif_makeimages`(cubes), if mom8fc score is yellow, it **rarely** means that continuum subtraction needs to be redone, but merely that in some circumstances the continuum image can be improved to reduce line contamination (see DRM training material).
11. Due to CASA bug [CAS-13908](https://open-jira.nrao.edu/browse/CAS-13908), PLWG recommends that all multi-EB ephemeris data be run in serial.
12. Phase structure function plots in {func}`~pipeline.hifa.cli.hifa_wvrgcalflag` are calculated from antenna-based gains, so baseline-based flags will not be reflected ({jira}`PIPE-1661`).
13. In the polcal recipe, if the selected session reference antenna is fully flagged on any spw by {func}`~pipeline.hifa.cli.hifa_gfluxscaleflag`, then {func}`~pipeline.hifa.cli.hifa_gfluxscale` will crash. The workaround is to set a different reference antenna (or list of reference antennas) in the {func}`~pipeline.hif.cli.hif_refant` task in the PPR. In a related issue, if the session reference antenna is fully flagged due to shadowing on only 1 of the transfer targets (and still wins the best score in {func}`~pipeline.hif.cli.hif_refant`), then {func}`~pipeline.hifa.cli.hifa_gfluxscale` will crash ({jira}`PIPE-1805`).
14. {func}`~pipeline.hifa.cli.hifa_imageprecheck` will crash on mosaic observations of science targets that have integer names ({jira}`PIPE-1708`).
15. In the polcal recipe, {func}`~pipeline.hifa.cli.hifa_gfluxscale` can fail silently (pausing pipeline permanently) if the refant has 100% flagging on either PHASE or CHECK source ({jira}`PIPE-1805`). The workaround is to set geometry=False in {func}`~pipeline.hif.cli.hif_refant`.
16. On the Spectral Setup weblog page, multi-target datasets with multiple tunings not observed in all targets will not show the Transition names for spws associated with tunings beyond the first tuning ({jira}`PIPE-1909`).
17. For heterogeneous array mosaics with 3 or more PM antennas included, if any field has only 1 baseline of data left unflagged after online flags and any prior stage flagging, then {func}`~pipeline.hifa.cli.hifa_targetflag` will crash ({jira}`PIPE-1879`).
18. ACA projects with multiple single-spw FDM tunings might experience odd flagging of non-edge channels ({jira}`PIPE-1991`). The work-around is to set edgespw=False in {func}`~pipeline.hifa.cli.hifa_flagdata`.
19. In {func}`~pipeline.hif.cli.hif_findcont`, spws with a single range of continuum channels identified might be declared AllCont even if they contain a significantly lesser amount of continuum than the nominal threshold of 91% ({jira}`PIPE-2034`).
20. The Tsys field indicator in the mosaic pattern plot on the Spatial Setup page doesn't account for the angular offset of the field ({jira}`PIPE-2067`).
21. The {func}`~pipeline.hif.cli.hif_applycal` page can fail to render if the uv coverage plot fails to be made due to flagging of data ({jira}`PIPE-1294`).
22. {func}`~pipeline.hifa.cli.hifa_gfluxscaleflag` crashes on MOUS with EBs that straddle Cycle 2 and Cycle 3 ({jira}`PIPE-2691`).
23. The aggregate bandwidth listed on continuum {func}`~pipeline.hif.cli.hif_makeimages` pages does not account for the deterministic flagging of edge channels on TDM spws ({jira}`PIPE-2349`) and it does not account for spw overlap ({jira}`PIPEREQ-37`).
24. If combine='spw' is used in gaincal calls, pipeline will crash in {func}`~pipeline.hifa.cli.hifa_gfluxscale` if the lowest index spw is fully flagged ({jira}`PIPE-128`).
25. In rare cases of old data (Cycle 1), chantol needs to be increased in {func}`~pipeline.h.cli.h_tsyscal` PPR in order for tsysspwmap to succeed on all spws ({jira}`PIPE-1440`).

### Single Dish Pipeline 2022

1. The "npiece" parameter determining number of cubic splines to fit can sometimes be miscalculated when the baseline is complex, leading to non-optimal baseline fits. ({jira}`PIPE-1773`, ***Fixed in 2022.2.0.68***)
2. Weights calculated for spectra completely flagged in only one polarization can be inappropriately high, leading to bright and dark artifacts in the images. ({jira}`PIPE-1771`, ***Fixed in 2022.2.0.68*** — *affected data will be reprocessed*)

---

## Browser Security and Viewing file://weblog

More stringent security in most web browsers in 2020 broke the weblog when displayed using a `file://` URL, and users may encounter "failure to load" errors (see [Firefox security update details](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS/Errors/CORSRequestNotHttp)). As of PL2020, the weblog contains instructions for what users can do if they encounter this error, including a new local html server embedded in the pipeline that users can access through CASA. These are applicable for the older weblogs, even if the weblog itself won't give them to you.

> Note that newer versions of **Firefox** (>=v96, ~Feb 2022) no longer have the parameter `privacy.file_unique_origin`, but in that case the same workaround described below can be achieved by setting **`security.fileuri.strict_origin_policy`** to `False`.

For Google Chrome, it can be started with the following command line arguments:

```
chromium-browser --disable-web-security --user-data-dir="[some directory here]"
```

In addition to the suggestions below, you can start a local http server with python3, either the one included with CASA, or the one installed on your system:

```
python3 -m http.server 8080 --bind 127.0.0.1 &
```

and then access in your browser the url `http://127.0.0.1:8080/`

---

## PL2021.2.0

Oct 2021 – Oct 2022

### CASA 2021

1. The bsend mechanism has a limit of 100 MB (introduced in 2014), which can cause the pipeline to fail (PIPE-1337) on MOUS with large numbers of EBs/spws/targets/integrations. So far, it has been seen only on a 42-EB 7m dataset. *fixed 2022*
2. Plotbandpass will not produce a plot of overlay='antenna' if there is only one antenna in the cal table ([CAS-14657](https://open-jira.nrao.edu/browse/CAS-14657)). This impacts the single dish pipeline in {func}`~pipeline.hsd.cli.hsd_skycal` if the MOUS contains only 1 antenna ({jira}`PIPE-2825`).

### Interferometric Pipeline 2021

1. CASA tclean sometimes exits with an unsupported code "0" — this generally is okay, but PL will capture that as a yellow warning in the weblog, and the data reducer should check the images for scientific acceptability. *fixed 2022*
2. In the {func}`~pipeline.hifa.cli.hifa_renorm` (hifa_almarenorm at the time) PDF summary plot, if the first spw is narrow, subsequent spws even if wide will be missing the vertical segment boundary lines. This only affects the summary plot, so other plots in the PDF will show the lines. *fixed 2022*
3. When spw mapping is in use, bad data can sometimes escape unassessed by {func}`~pipeline.hifa.cli.hifa_bandpassflag` and appear as bad in {func}`~pipeline.hifa.cli.hifa_timegaincal` and {func}`~pipeline.hif.cli.hif_applycal` (PIPE-838, to be fixed by PIPE-1154 where spw mapping and combination will be prohibited for all calibrators except the phase calibrator). *fixed 2022*
4. If an spw is fully flagged for Tsys in {func}`~pipeline.hifa.cli.hifa_tsysflag`, then {func}`~pipeline.hifa.cli.hifa_gfluxscale` can crash (PIPE-1208). This is often due to poor or strongly-varying atmospheric transmission vs. frequency. The possible workarounds are to either: set the offending EB to SemiPass, raise ff_max_limit from 13 to 30 for {func}`~pipeline.hifa.cli.hifa_tsysflag` in the PPR, or flag the poorest transmission parts of the spw (both its Tsys solutions and visibility data). *fixed 2022*
5. For the {func}`~pipeline.hif.cli.hif_applycal` stage, the QA subscore for %newly flagged is not included in the overall score evaluation, meaning that a "!" or "?" can appear in the left navigation pane, different from the "By Topic" QA color bar for {func}`~pipeline.hif.cli.hif_applycal`. *fixed 2022*
6. As in previous releases, in the {func}`~pipeline.hif.cli.hif_applycal` weblog, if there are multiple phase calibrators or check sources, their calibrated spectra are overlaid in the same plot (PIPE-432). *fixed 2022*
7. A bad score for the mom8fc can be erroneously triggered in cube {func}`~pipeline.hifa.cli.hifa_makeimages` when the channelized noise is not uniform in the findcont channels, and has some channels with significantly higher noise (e.g. in regions of deep atmospheric absorption), resulting in more pixels above the Peak/(medianChanMAD) than expected. No workaround — looking at weblog plots should make it clear that there is really no emission in the findcont channels. *improved 2022, may still require manual examination*
8. <span style="color:red">Full-polarization datasets contain a {func}`~pipeline.hifa.cli.hifa_lock_refant`() task</span> — `pipelinemode="automatic"` must be removed from that task in casa_pipescript.py in order for casa_pipescript.py to run (PIPE-1226). casa_restorescript.py works without modification. *fixed 2022*
9. MOUS with large numbers of EBs/spws/fields/integrations can exceed the 100MB memory footprint of bsend in CASA and crash (PIPE-1337). This feature was introduced in 2014 and a small increase has been requested (CAS-13656). *improved 2022*
10. As in previous releases, in the {func}`~pipeline.hif.cli.hif_applycal` weblog, if there are multiple phase calibrators or check sources, their calibrated spectra are overlaid in the same plot (PIPE-432). *fixed 2022*
11. If pointing is not performed in every EB of a full-polarization dataset, {func}`~pipeline.hif.cli.hif_makeimages` (check sources) can crash (PIPE-1364). *fixed 2022*
12. If the check source is so faint that no gain solutions can be found, then {func}`~pipeline.hifa.cli.hifa_gfluxscale` will crash (PIPE-1468).
13. An irregular mosaic with no pointing at the geometric center will likely fail, and the pipeline will warn you of this likelihood. You can use tclean with the psfphasecenter parameter to image manually. (PIPE-98)
14. On the Spectral Setup weblog page, multi-target datasets with multiple tunings not observed in all targets will not show the Transition names for spws associated with tunings beyond the first tuning (PIPE-1909).
15. ACA projects with multiple single-spw FDM tunings might experience odd flagging of non-edge channels ({jira}`PIPE-1991`). The work-around is to set edgespw=False in {func}`~pipeline.hifa.cli.hifa_flagdata`.
16. In {func}`~pipeline.hif.cli.hif_findcont`, spws with a single range of continuum channels identified might be declared AllCont even if they contain a significantly lesser amount of continuum than the nominal threshold of 91% ({jira}`PIPE-2034`).
17. The {func}`~pipeline.hif.cli.hif_applycal` page can fail to render if the uv coverage plot fails to be made due to flagging of data ({jira}`PIPE-1294`).
18. The aggregate bandwidth listed on continuum {func}`~pipeline.hif.cli.hif_makeimages` pages does not account for the deterministic flagging of edge channels on TDM spws ({jira}`PIPE-2349`) and it does not account for spw overlap ({jira}`PIPEREQ-37`).
19. If combine='spw' is used in gaincal calls, pipeline will crash in {func}`~pipeline.hifa.cli.hifa_gfluxscale` if the lowest index spw is fully flagged ({jira}`PIPE-128`).
20. In rare cases of old data (Cycle 1), chantol needs to be increased in {func}`~pipeline.h.cli.h_tsyscal` PPR in order for tsysspwmap to succeed on all spws ({jira}`PIPE-1440`).

### Single Dish Pipeline 2021

0. Some task parameters in PPR are not selected properly. For example, {func}`~pipeline.hsd.cli.hsd_blflag` fails when spw is specified in PPR (PIPE-1298).
1. {func}`~pipeline.hsd.cli.hsd_imaging` does not properly combine datasets associated with virtual spw. (PIPE-1478)

---

## Known Issues for PL2020.1.0

Release date Feb 2021

### CASA 2020

See [CASA 6.1.X known issues](https://casa.nrao.edu/casadocs/casa-6.1.0/introduction/known-issues)

1. Plotbandpass will not produce a plot of overlay='antenna' if there is only one antenna in the cal table ([CAS-14657](https://open-jira.nrao.edu/browse/CAS-14657)). This impacts the single dish pipeline in {func}`~pipeline.hsd.cli.hsd_skycal` if the MOUS contains only 1 antenna ({jira}`PIPE-2825`).

### Interferometric Pipeline 2020

0. For polarization datasets, {func}`~pipeline.hifa.cli.hifa_restoredata` does not include the polarization calibrator in its applycal commands. A workaround is being arranged with DRM.
1. If {func}`~pipeline.hif.cli.hif_lowgainflag` (hifa_lowgainflag at the time) flags a large number of antennas on a given spw, but not all antennas, then the imaging pipeline can crash downstream in {func}`~pipeline.hif.cli.hif_findcont`. One workaround is to set niter=2 in {func}`~pipeline.hif.cli.hif_lowgainflag` (hifa_lowgainflag at the time) in the PPR. This works as desired (the whole spw is flagged), but it fails to render the weblog page for {func}`~pipeline.hif.cli.hif_lowgainflag` (hifa_lowgainflag at the time). The other alternative is to apply a manual flag for the spw in the regular flag template file.
2. A bad score for the mom8fc can be erroneously triggered in cube {func}`~pipeline.hif.cli.hif_makeimages`(cubes) when the channelized noise is not uniform in the findcont channels, and has some channels with significantly higher noise (e.g. in regions of deep atmospheric absorption), resulting in more pixels above the Peak/(medianChanMAD) than expected. No workaround — looking at weblog plots should make it clear that there is really no emission in the findcont channels.
3. For full-polarization datasets, the amp vs. time detail plots (per antenna) in {func}`~pipeline.hif.cli.hif_applycal` do not include the calibrator scans with POLARIZATION intent, but the plots of calibration solutions in {func}`~pipeline.hifa.cli.hifa_timegaincal` do include them. The workaround is to run plotms manually if there is bad data in the parent plot (with all antennas overlaid) and you want to determine the subset of antennas involved.
4. The amplitude vs uv distance version of the "before/after flagging" plots are not shown in {func}`~pipeline.hifa.cli.hifa_polcalflag`. Only the ampl. vs time plots are shown.
5. Datasets suffering from the Cycle 7 correlator instrumental problem related to concurrent subarrays can have some outliers escape unflagged. But this issue was apparently fixed in SCCB-1042 (2021-05-20), so it should not affect the remainder of Cycle 7 data.
6. Antenna-based single-polarization, single-integration outliers not apparent in {func}`~pipeline.hifa.cli.hifa_polcalflag` can appear as amplitude outliers on the polarization calibrator in {func}`~pipeline.hif.cli.hif_applycal`.
7. When spw mapping is used in {func}`~pipeline.hifa.cli.hifa_spwphaseup`, bad data on the bandpass calibrator can escape {func}`~pipeline.hifa.cli.hifa_bandpassflag` unflagged and appear as outliers in {func}`~pipeline.hif.cli.hif_applycal`, because the timegaincal solutions come from a different spw when applycal is run.
8. The QA message in {func}`~pipeline.hifa.cli.hifa_gfluxscale` on the ratio of S_calibrated / S_catalog has an incorrectly calculated percentage.
9. For Cycle 3 datasets affected by extra field IDs associated with only SQLD data, the new {func}`~pipeline.hifa.cli.hifa_targetflag` stage will show a warning message for these fields (each spw): "Warning! Unable to compute flagging for intent TARGET, field 2, spw 16". The workaround is simply to ignore this warning – it should not happen in new data.
10. Due to CASA changing how tasks are built, several tasks fail to completely render the "inp" input parameters (blank lines appear in the "inp" output). `help(taskname)` still lists all of the available parameters, and we strongly recommend users refer to the Reference Manual if task parameters are not clear. Affected tasks: {func}`~pipeline.hifa.cli.hifa_importdata`, {func}`~pipeline.hifa.cli.hifa_wvrgcalflag`, {func}`~pipeline.hif.cli.hif_lowgainflag`, {func}`~pipeline.hifa.cli.hifa_bandpassflag`, {func}`~pipeline.hifa.cli.hifa_bandpass`, {func}`~pipeline.hif.cli.hif_applycal`, {func}`~pipeline.hif.cli.hif_makeimlist`, {func}`~pipeline.hif.cli.hif_makeimages`, {func}`~pipeline.hifa.cli.hifa_imageprecheck`, {func}`~pipeline.hif.cli.hif_checkproductsize`, {func}`~pipeline.hifa.cli.hifa_exportdata`, {func}`~pipeline.hif.cli.hif_mstransform`, {func}`~pipeline.hif.cli.hif_findcont`, {func}`~pipeline.hsd.cli.hsd_importdata`, {func}`~pipeline.hsd.cli.hsd_flagdata`, {func}`~pipeline.hsd.cli.hsd_applycal`, {func}`~pipeline.hsd.cli.hsd_imaging`, {func}`~pipeline.hifa.cli.hifa_polcalflag`, hif_uvcontfit, {func}`~pipeline.hif.cli.hif_uvcontsub` (dryrun parameter only missing)
11. In the Cycle 6, Cycle 7, and PL2020 releases: datasets with heterogeneous antenna diameters will also include the cross-diameter baselines in the science target imaging (rather than merely the 7m-7m or merely the 12m-12m baselines). The calibrator imaging stage correctly includes all baselines, as desired. For 7m array projects with 1 or more 12m antennas included, the effects on the resulting image are: a different effective PB response (slightly smaller), lower noise, a smaller synthesized beam, and (likely) a smaller LAS. Different science use cases may see the net difference as a positive or negative effect.
12. In all pipeline releases through PL2020: FDM spws with 256 channels are being labeled as TDM on the Spectral Setup details page. This is due to faulty logic implemented in CASA::msmd.almaspws.
13. Full-polarization datasets contain a {func}`~pipeline.hifa.cli.hifa_lock_refant`() task — `pipelinemode="automatic"` must be removed from that task in casa_pipescript.py in order for casa_pipescript.py to run. casa_restorescript.py works without modification.
14. As in previous releases, in the {func}`~pipeline.hif.cli.hif_applycal` weblog, if there are multiple phase calibrators or check sources, their calibrated spectra are overlaid in the same plot (PIPE-432).
15. If pointing is not performed in every EB of a full-polarization dataset, {func}`~pipeline.hif.cli.hif_makeimages` (check sources) can crash (PIPE-1364).
16. If the check source is so faint that no gain solutions can be found, then {func}`~pipeline.hifa.cli.hifa_gfluxscale` will crash (PIPE-1468).
17. ACA projects with multiple single-spw FDM tunings might experience odd flagging of non-edge channels ({jira}`PIPE-1991`). The work-around is to set edgespw=False in {func}`~pipeline.hifa.cli.hifa_flagdata`.
18. In {func}`~pipeline.hif.cli.hif_findcont`, spws with a single range of continuum channels identified might be declared AllCont even if they contain a significantly lesser amount of continuum than the nominal threshold of 91% ({jira}`PIPE-2034`).
19. The aggregate bandwidth listed on continuum {func}`~pipeline.hif.cli.hif_makeimages` pages does not account for the deterministic flagging of edge channels on TDM spws ({jira}`PIPE-2349`) and it does not account for spw overlap ({jira}`PIPEREQ-37`).
20. If combine='spw' is used in gaincal calls, pipeline will crash in {func}`~pipeline.hifa.cli.hifa_gfluxscale` if the lowest index spw is fully flagged ({jira}`PIPE-128`).
21. In rare cases of old data (Cycle 1), chantol needs to be increased in {func}`~pipeline.h.cli.h_tsyscal` PPR in order for tsysspwmap to succeed on all spws ({jira}`PIPE-1440`).

### Single Dish Pipeline 2020

1. Observed RMS tends to be larger than theoretical RMS (SD pipeline). There are two possible causes. One is that ATM and ripple features remain in the final image. The second is that the pixels located at the map edge are included in the measurement of the observed RMS. The latter will be improved in pipeline2021.
2. Strong emission is flagged in {func}`~pipeline.hsd.cli.hsd_blflag`. The reason of this issue is that some emission components at some channels (i.e. wing component) are not identified as a line. This increases the RMS at corresponding channels. Essentially, improving the line identification algorithm is required to fix this issue. This issue can be avoided by changing the threshold of blflag manually.
3. Wrong position of the open circle indicating peak SN position in Peak SN map. When the scan direction is not along RA/DEC, the open circle indicating peak SN position in Peak SN map and spectrum at peak position are not plotted correctly. However, the information of the peak position is used just as a reference. This does not affect the detection of the contamination and giving "warning".
4. {func}`~pipeline.hsdn.cli.hsdn_restoredata` crashes (Nobeyama Pipeline)
5. executeppr does not support {func}`~pipeline.hsd.cli.hsd_restoredata` task (ALMA-SD Pipeline)

---

## Contact Us

Questions about the ALMA Pipeline may be submitted to the [ALMA Helpdesk](https://help.almascience.org/).

Feedback specific to CASA should be sent to casa-feedback@nrao.edu.
