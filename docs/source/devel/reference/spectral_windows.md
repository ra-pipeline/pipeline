# Spectral Windows and Reference Antennas

## Reference antenna updates

ALMA interferometry recipes typically include the `hif_refant` task that creates
a list of antennas ranked according to a flagging score and geometric score.

Upon acceptance of the Results from the `hif_refant` task, this refant list is
stored in the `reference_antenna` property of the MeasurementSet object in the
context and used in subsequent stages.

There are a number of ALMA IF calibration stages that can update the reference
antenna list to either a.) remove an antenna from the list, or
b.) demote an antenna to the end of the list (lowest priority):

- `hifa_bandpassflag`
- `hif_lowgainflag`
- `hifa_polcalflag`
- `h*_tsysflag`

Note: [PIPE-1664](https://open-jira.nrao.edu/browse/PIPE-1664) proposes to add a "refant list update" step to `hifa_gfluxscaleflag`.

A couple of reference antenna utility functions are bundled in
`pipeline.infrastructure.refantflag` (introduced in PIPE-1759):

- identifying fully flagged antennas from flagging view or from flagging commands
- marking antennas for refant update
- aggregating and formatting fully flagged antenna notifications

## SpectralSpec handling in tasks

A "SpectralSpec", also known as spectral setup, is a term used by the OT and SSR to refer to a tuning, which is a
collection of spectral windows that can be observed simultaneously (i.e. in the same subscan).

SpectralSpec was introduced in Pipeline as part of [PIPE-316 (2019, Cycle 7)](https://open-jira.nrao.edu/browse/PIPE-316),
to assign a SpectralSpec ID to each Spectral Window, and to allow for heuristics that e.g.:

- require that a SpW is only mapped to another SpW within the same SpectralSpec
- evaluate a heuristic separately for each SpectralSpec, aka each group of SpWs that share the same SpectralSpec ID.

As of September 2025, the following Pipeline tasks include steps based on SpectralSpec (aka spectral tuning):

- `hifa_flagdata`: considers SpectralSpec in step to flag ACA FDM spectral window edges (PIPE-1991).
- `hifa_bandpass`: considers SpectralSpec during determination of optimal phase-up solint (and combine).
- `hifa_gfluxscaleflag`: creates separate phase-up caltables for each SpectralSpec.
- `hifa_spwphaseup`:
  - the gaincal step in this task creates separate gaincal jobs for each SpectralSpec.
  - SpectralSpec is considered in the step to determine the optimal phase-up solint.
  - In phase decoherence step, considers SpectralSpec in selecting what SpWs to analyse (PIPE-1871).
  - SNR based narrow-to-wide spw map considers SpectralSpec for find matching spw for each science spw.
  - the science spw combination map considers SpectralSpec to set which SpWs can be combined.
- `hifa_polcalflag`: the gaincal step in this task creates separate gaincal jobs for each SpectralSpec.
- SD common raster utility `flag_raster_map` consolidates its results per SpectralSpec and field (PIPE-1990)
- SpW ID vs. Frequency plot in MS-summary page uses a different colour coding per SpectralSpec.
- `hifa_timegaincal`: the steps computing phase solutions for phase calibrators and for the target will create separate
  solutions for each SpectralSpec in case of spw combination (PIPE-390)
- `hifa_tsysflagcontamination`: uses SpectralSpec to determine if a dataset is multi-tuning and multi-source (which gets
  its own dedicated "unprocessable" score).
- `tsysspwmap` heuristic module:
  - Creates a Tsys SpW map where science SpW and Tsys SpW need to have matching SpectralSpec.
  - This tsysspwmap heuristic is used in both `h_tsyscal` and in `AtmHeuristics` (itself used in `hifa_wvrgcal` and `phasemetrics`).

## Spectral Windows in Pipeline

The Pipeline has defined the `domain.spectralwindow.SpectralWindow` domain class to represent spectral windows,
and these get generated during the importdata stage by
`infrastructure.tablereader.SpectralWindowTable.get_spectral_windows` and added to the `MeasurementSet` object
(`ms.spectral_windows`) in `infrastructure.tablereader.MeasurementSetReader.get_measurement_set`.

Throughout all Pipeline tasks, it is a common pattern to retrieve information about spectral windows via the
`MeasurementSet.get_spectral_windows` method.

The Pipeline heuristics distinguish a number of different kinds of spectral windows, such as:

- "science" spectral windows
- Tsys spectral windows
- Diffgain reference spectral windows
- Diffgain on-source spectral windows

Here, it should be noted that this "kind" of spectral window is *not* the same as its "type". The "type" of a
spectral window is recorded as the `type` property of the `SpectralWindow` domain class, and covers e.g. WVR,
CHANAVG, FDM, TDM; for reference, see this description in CASA docs:
<https://casadocs.readthedocs.io/en/stable/api/tt/casatools.msmetadata.html#casatools.msmetadata.msmetadata.almaspwse> description of almaspw

The above-mentioned "kinds" of spectral windows are not recorded as a property in `SpectralWindow` and instead are
determined in different manners for the different kinds. Moreover, these "kinds" are local definitions used by Pipeline
that may not be recognized by other ALMA subsystems.

## Science spectral windows

The definition of "science" spectral windows is implemented in the `MeasurementSet.get_spectral_windows` method,
and depends on whether the MS is from ALMA, VLA, or NRO. For ALMA, a science spectral window is a spectral window
that:

- covers one of the "science" intents; currently: 'TARGET', 'PHASE', 'BANDPASS', 'AMPLITUDE', 'POLARIZATION',
'POLANGLE', 'POLLEAKAGE','CHECK', 'DIFFGAINREF', 'DIFFGAINSRC'
- has a number of channels that is not 1 or 4 (specifically: not in `MeasurementSet.exclude_num_chans`)

By this definition, the science spectral windows exclude for example:

- 1-channel wide CHANAVG
- 1-channel wide SQLD
- 4-channel wide WVR
- spectral windows used for scans that only cover POINTING and WVR intents

Conceptually, the science spectral windows are the main spectral windows used to observe the astronomical targets,
and the majority of ALMA Pipeline tasks and heuristics typically only work on the science spectral windows.
As such, it is even the default behaviour of the `MeasurementSet.get_spectral_windows` method to return only the
science spectral windows. If a task does need all spectral windows, they can override this behaviour with:
`all_spws = ms.get_spectral_windows(science_windows_only=False)`.

## Tsys spectral windows

Tsys spectral windows are used to measure the system temperature, and used during Tsys calibration scans that
cover the "ATMOSPHERE" intent.

Depending on how the observation is set up, the Tsys SpWs can be the same as the science SpWs or they can be defined
as separate dedicated SpWs. The latter can occur for example when the science scans use high spectral resolution
(FDM mode) spectral windows while the Tsys scans are normally performed with lower resolution (TDM mode)
spectral windows.

Identifying a Tsys spectral window is defined in `h.heuristics.tsysspwmap` as either:

- spectral windows that are present in a Tsys solutions caltable created by CASA, or
- spectral windows in MS that cover 'ATMOSPHERE' intent and whose type is 'TDM'

## Diffgain reference and diffgain on-source spectral windows

The concept of "diffgain reference" and "diffgain on-source" spectral windows was introduced in PL2024 as part of adding
support for calibration band-to-band observations that use a differential gain calibrator. Relevant tickets:

- [PIPE-2079](https://open-jira.nrao.edu/browse/PIPE-2079)
- [PIPE-2145](https://open-jira.nrao.edu/browse/PIPE-2145)

Within Pipeline, these two kinds are identified as science spectral windows that cover either the `DIFFGAINREF` or
the `DIFFGAINSRC` intent, e.g.:

```python
dg_refspws = ms.get_spectral_windows(intent='DIFFGAINREF')
dg_srcspws = ms.get_spectral_windows(intent='DIFFGAINSRC')
```

## Spectral Window mapping in Pipeline

Various calibration heuristics in Pipeline require spectral window mapping, as supported by the `spwmap` parameter in
various CASA tasks such as `applycal`, `gaincal`, `bandpass`, `polcal`. Here, the `spwmap` is a simple list of integers,
where the index of the list corresponds to the target SpW ID in the MeasurementSet (i.e. the SpW you want to calibrate)
and the value in the list corresponds to the SpW ID in the calibration table whose solution should be applied to that
target SpW ID.

If spwmap is unspecified or an empty list, it signifies that each SpW ID is mapped to itself, i.e. no SpW re-mapping or
combination.

In some cases, typically when a calibrator has low SNR in one or more SpWs, the Pipeline can derive a SpW re-mapping
to map the calibration from a higher SNR SpW to the target SpWs where the calibrator had low SNR. In cases where a
calibrator has too low SNR in all SpWs, the Pipeline can decide to use spectral window combination instead, whereby
the SpWs-to-combine are all re-mapped to the lowest SpW ID among the SpWs-to-combine, and the CASA task using this
spwmap should be passed `combine=True` (which is otherwise False by default).

Pipeline has implemented SpW-to-SpW mapping heuristics for a number of distinct use-cases:

- Tsys-SpW to target SpW mapping
- Phase-offset gaincal calibrator SpW to target SpW mapping
- Diffgain reference SpW to diffgain on-source SpW mapping

## Tsys SpW to target SpW mapping

The Tsys spectral window to target (science) spectral window mapping is defined in `h.heuristics.tsysspwmap.tsysspwmap`.

The resulting `spwmap` is primarily used in the `h_tsyscal` task that creates and registers the Tsys calibration.
This task first creates the Tsys caltable and then creates the `spwmap` that maps each target SpW to its appropriate Tsys
SpW. This `spwmap` is then used in the step that creates the `CalApplications` that will register (in the callibrary)
how the Tsys caltable should be applied to the measurement set. Any subsequent task downstream that needs to (pre-)apply
the calibrations (e.g. `gaincal`, `applycal`) would then apply this Tsys caltable with the correct value of `spwmap`.

Note: a secondary use of `h.heuristics.tsysspwmap.tsysspwmap` occurs in
`hifa.heuristics.atm.AtmHeuristics._calculate_median_tsys`, used only
locally to compute median Tsys per science SpW.

## Phase-offset gaincal calibrator SpW to target SpW mapping

Various stages in ALMA calibration pipeline compute a phase-offset gain calibration table, in many cases even
just a temporary one that is only pre-applied during certain steps in the task without being registered to the
top-level Pipeline context.

To enable consistency in how those phase-offset gain calibrations are applied across various tasks,
ALMA IF calibration pipeline recipes include the `hifa_spwphaseup` stage. This stage evaluates for a number of
calibrator intents ('AMPLITUDE,BANDPASS,CHECK,DIFFGAINREF,DIFFGAINSRC,PHASE') and each of their corresponding fields,
what the optimal SpW maps are, based by default on calibrator SNR. See implementation details in
`hifa.tasks.spwphaseup.spwphaseup.SpwPhaseup._derive_spwmaps`, which invokes the `hifa.heuristics.phasespwmap`
to generate the `spwmap` lists for the case of narrow-to-wide (low-to-high-SNR) SpW mapping, or SpW-combination mapping.

The resulting `spwmap` lists are combined into a `SpwMapping` object together with:

- other recommended values to use: `combine`, `solint`, `gaintype`
- extra info such as SNR info / thresholds used in the SpW map derivation

The primary use-case is `combine`, i.e. whether or not to use SpW combination, which is currently not part of the
`CalApplication`. This is denoted with `combine=True` though in downstream tasks this gets converted to `combine='spw'`
before passing to a CASA task.

These `SpwMapping` are created for each combination of `intent, field` and stored by that key in a dictionary in the
context (`MeasurementSet.spwmaps`).

Downstream tasks that make use of this `SpwMapping` information include:

- hifa_gfluxscale: `hifa.tasks.fluxscale.gcorfluxscale.SerialGcorFluxscale._get_phasecal_params`
- hifa_gfluxscaleflag: `hifa.tasks.gfluxscaleflag.gfluxscaleflag.SerialGfluxscaleflag._get_phasecal_params`
- hifa_timegaincal: `hifa.tasks.gainal.timegaincal.SerialTimeGaincal._get_phasecal_params`
- hifa_diffgaincal: `hifa.tasks.diffgaincal.diffgaincal._assess_spw_combine_based_on_spwmapping_and_snr`

Note: each of these tasks may have their own task-specific heuristic for which values from the `SpwMapping`
to adopt.

## Diffgain reference SpW to diffgain on-source SpW mapping

For band-to-band calibrations, the phase SpW-to-Spw mapping derived in `hifa_spwphaseup` for the `PHASE` calibrator
requires an adjustment to ensure that diffgain on-source SpWs are remapped to an associated diffgain reference SpW.
This kind of diffgain-specific `spwmap` adjustment is implemented in
`hifa.heuristics.phasespwmap.update_spwmap_for_band_to_band`, and is used in `hifa_spwphaseup` and
`hifa_diffgaincal`.
