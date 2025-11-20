# Pipeline developer documentation

This is to be populated, as time permits, with information that may be useful for other pipeline developer team members.

Think of it as a place for a new team member to look for useful bits of information, as a refresher for experienced team members, or as a reference for a developer unfamiliar with certain areas of the pipeline.



## Pipeline Context and domain objects

The Pipeline Context is the Pipeline's record of state, used to:
- Transfer state from task to task
- Quickly access (cached) info about the dataset without expensive I/O to disk
- Save the state of a pipeline run to disk to be able to restore/resume from disk in a future session

The domain objects are logical representations of real-world concepts in the radio interferometry domain, and form
the core building blocks for the Pipeline application.

### Overview of Context

The following is a brief overview of contents in the Pipeline context, not expected to be comprehensive:
- Metadata about the Pipeline run (stage counter, output dir)
- Metadata describing the MeasurementSet(s), represented by Domain objects (e.g. antenna, spectral windows, fields, scans…)
  - Originally implemented at a time that the CASA `msmd` tool was not yet available, so this was necessary to access
    metadata quickly. Since the introduction of `msmd`, most elements in Pipeline domain objects are now populated
    using `msmd` (see usage of `infrastructure.casa_tools.MSMDReader` and `infrastructure.tablereader`).
- Calibration state (callibrary)
- Results from completed stages (just as reference to results stored on disk)
- Cached data from stage(s) required as input in subsequent stage(s), e.g.:
  - Spectral window maps
  - Mapping of phase calibrator to target/check fields
  - Lists of images to be produced by imaging stage(s)
  - Self-cal targets

Note: The Pipeline context is not a formally agreed user interface. Interface changes happen regularly during
development of each release, and the Pipeline is not guaranteed to be backwards compatible with context pickles
created by previous releases.

Context key properties:
- output_dir, report_dir, products_dir: directories to store Pipeline output
- logs: filenames for log/script outputs
- results: list of references to task results (stored on disk)
- callibrary: Pipeline Calibration State
- project_[summary|structure|performance_parameters]: information about the observing project
- processing_intents: list of processing intents
- observing_run: metadata about the observing run that is (being) processed
- calimlist, sciimlist, rmsimlist, subimlist: lists of images that have been computed in (calibrator, science, RMS, cutout) imaging stages
- contfile, linesfile, clean_list_info, imaging_mode, imaging_mode, imaging_parameters, etc: Parameters / info used in imaging stages

Context key functions:
- get_oussid(): returns the parent OUS “ousstatus” name
- get_recipe_name(): returns the recipe name from the project structure
- set_state(): internal function to set project structure, recipe name, proc title
- save(filename=None): saves a copy of the context to disk

`observing_run` key properties:
- measurement_sets: list of MS domain objects
- virtual_science_spw_[ids|names|shortnames]: info on virtual spectral windows across observing run
- start_[time|datetime], end_[time|datetime]: start/end time (and date) for run (based on first/last MS)
- project_ids, schedblock_ids, execblockids, observers: return set of unique project / scheduling block / execution block IDs or observers for given run
- ms_datatable_name, ms_reduction_group, org_directions: parameters / info used in ALMA Single-Dish stages

`observing_run` key functions:
- add_measurement_set(ms): register MS object with run
- get_ms(name, intent): retrieve MS by name (or intent)
- get_measurement_sets(names, intents, fields): retrieve MSes filtered by names, fields, intents
- get_measurement_sets_of_type(dtypes, msonly, source, spw, vis): retrieve MSes filtered by name, data type, source name, spw
- get_real_spw_id_by_name(spw_name, target_ms): translate spw name to real spw ID for given MS
- get_virtual_spw_id_by_name(spw_name): translate spw name to virtual spw ID for run
- [virtual2real|real2virtual]_spw_id(spw_id, target_ms): translate spw ID from virtual to real / real to virtual for given MS
- real2real_spw_id(spw_id, source_ms, target_ms): translate a real spw ID from one MS to another MS.

### Overview of domain objects

Pipeline includes the following domain objects:
- ObservingRun: Representation of the observing run that is processed
- MeasurementSet: Representation of the MeasurementSet: AntennaArray, Fields, Sources, Scans, DataDescription, SpWs, Pol, States (Intents), FluxMeasurements, DataType.
- Also stores PL derived MS-specific properties used in subsequent stages.
- AntennaArray: Representation of the antenna array (name, antennas, baselines, location, centre, …)
- Antenna: Representation of a single antenna (name, ID, long/lat/height, diameter, direction)
- Field: Representation of a field (name, ID, associated source ID, times, intents, states, valid SpWs, flux dens.)
- Source: Representation of a source (name, ID, associated field IDs, direction, proper motion, ephemeris info)
- Scan: Representation of a single scan (antennas, intents, fields, states, data_descriptions, scan times)
- DataDescription: Representation of the DATA_DESCRIPTION table of an MS (data description IDs, SpW IDs, Pol IDs)
- SpectralWindow: Representation of a single SpW (name, ID, type, receiver, band, baseband, sideband, bandwidth, LO freqs, mean freq, ref freq, intents, list of Channels (themselves representations of each channel), …)
- Polarization: Representation of a polarization (ID, # of correlations, correlation type, correlation products)
- State: Representation of the STATE table in the MS, mapping “obs_mode” to pipeline “intents”
- FluxMeasurement: Representation of a flux measurement (SpW ID, I, Q, U, V, spix, uv min/max, origin, age, query date)
- DataType: Defines different types of data (raw, calibration, after spectral bl subtraction, …)
- datatable: Contains classes to hold metadata for scan table in memory, mapping between serial row indices and per-MS row indices, etc…
- measures: Defines commonly used measures and their units  (angles, distance, flux, frequency, velocity, file size, 
- unitformat: Defines format for units of magnitude (e.g. Kilobyte, millimeter, GHz, …)
- singledish: Defines classes to represent a MS Reduction Group, and individual MS Reduction Group Members.


### Using the pipeline context

A new Context is created with:
```python
h_init()
```
In this case, the Pipeline context becomes a hidden global variable in the CASA session.

Contexts can be saved to and restored from disk:
```python
# Save context to disk.
h_save()
# Restore context from disk.
h_resume()
```

At the end of a Pipeline run, the final state of the Pipeline Context is written to the working directory.

Depending on the `loglevel` of the Pipeline run, per-staged pickled Contexts can be found in the `saved_stage` folder.


### Accessing the pipeline context via task interface

Upon initializing a new context:
```python
context = h_init()
```

Upon resuming the most recent context found in working directory:
```python
context = h_resume()

# Note, this is equivalent to using:
context = h_resume(filename='last')
# where 'last' is a special case "filename" interpreted to load the context with
# the most recent timestamp.
```
Upon resuming a user-specified context:
```python
context = h_resume(filename='pipeline-procedure_hifa_cal.context')
```

In case a Pipeline context was initialized or resumed without capturing the returned reference:
```python
# Context gets initialized but the returned context is not captured:
h_init()
```
then this can still be retrieved with:
```python
# Later in the session, you can get a reference to the context in the current CASA session with:
from pipeline.h.cli import cli
context = cli.stack.get(cli.PIPELINE_NAME)
```


### Accessing the pipeline context using Python classes directly

Initializing a new run / context and saving to disk:
```python
import pipeline
context = pipeline.Pipeline().context
context.save()
```

Resuming previous run / context:
```python
import pipeline
context = pipeline.Pipeline(context='last').context
```


### Example interactions with the Pipeline context and its domain objects

#### Context queries: info about pipeline run, results

```python
# Resume a context:
context = h_resume()

# Display recipe name and Observing Unit Set Status ID:
print(context.get_recipe_name())
print(context.get_oussid())

# Display various information about the observing run:
print(context.observing_run.project_ids)
print(context.observing_run.schedblock_ids)
print(context.observing_run.execblock_ids)

print(context.observing_run.observers)

print(context.observing_run.start_time)
print(context.observing_run.start_datetime)
print(context.observing_run.end_time)
print(context.observing_run.end_datetime)

# Get stage number and name for all task results:
for results_proxy in context.results:
    results = results_proxy.read()  # this reads the result back in from disk
    print(f"{results.stage_number}, {results.taskname}")

# Show specific result, and corresponding task inputs.
task_result_list = context.results[14].read()  # Reading results from stage 15 (stage numbers are 1-indexed)
import pprint
pprint.pprint(task_result_list)
```

#### Context queries: measurement sets

```python
# Get names of MeasurementSets in current run.
msnames = [ms.name for ms in context.observing_run.get_measurement_sets()]

# Get MeasurementSet by name.
ms = context.observing_run.get_ms(name="uid___A002_X1181695_X1c6a4_8ant.ms")

# Get MeasurementSets filtered by given names & intents.
mslist = context.observing_run.get_measurement_sets(names=vislist, intents="BANDPASS,PHASE")

# Get MeasurementSets matching given DataType.
from pipeline.domain.datatype import DataType
mslist = context.observing_run.get_measurement_sets_of_type(dtypes=[DataType.REGCAL_CONTLINE_ALL, DataType.REGCAL_CONTLINE_SCIENCE])
```

#### Context queries: virtual spectral windows

```python
# Full/short names for all virtual SpWs in the observing run.
print(context.observing_run.virtual_science_spw_names)
print(context.observing_run.virtual_science_spw_shortnames)

# Convert virtual SpW ID to real one for given MS.
ms = context.observing_run.get_measurement_sets()[0]
virt_spwid = 16
real_spwid = context.observing_run.virtual2real_spw_id(virt_spwid, ms)

# Convert real SpW ID for given MS to virtual SpW ID.
virtual_spwid = context.observing_run.real2virtual_spw_id(22, ms)
```

#### MeasurementSet queries: spectral windows

```python
ms = context.observing_run.get_ms(name=vis)

# Get all Spectral Windows.
all_spws = ms.get_spectral_windows(science_windows_only=False)

# Get frame for specific SpW.
frame = ms.get_spectral_window(16).frame

# Get all "Differential Gain Reference" spectral windows, filtered by requested IDs.
dgref_spws = ms.get_spectral_windows("16,18,20,22", intent="DIFFGAINREF")

# Get SpW IDs for science SpWs (default), filtered by band and number of channels.
scispw_ids_sel = [spw.id for spw in ms.get_spectral_windows()
                  if spw.band == "ALMA Band 3" and spw.num_channels > 4]
```

#### MeasurementSet queries: fields

```python
ms = context.observing_run.get_ms(name=vis)

# Get names for all fields in the MS.
field_names = [field.name for field in ms.get_fields()]

# Get unique intents covered by fields for given field argument.
field_intents = {intent for field in ms.get_fields("J1851+0035,W43-MM1")
                 for intent in field.intents}

# Get field ID for all fields matching science target intent.
fieldlist = [field.id for field in ms.get_fields(intent="TARGET")]
```

#### MeasurementSet queries: scans

```python
# Get IDs of all scans.
ms = context.observing_run.get_ms(name=vis)
scan_ids = [scan.id for scan in ms.get_scans()]

# Get time on source for scans with PHASE intent for selected fields.
times = [scan.time_on_source
         for scan in ms.get_scans(field="J1851+0035,W43-MM1", scan_intent="PHASE")]
```

#### MeasurementSet queries: data descriptions

```python
# Get polarization ID for given MS, SpW ID, and correlation type.
ms = self.inputs.context.observing_run.get_ms(name=vis)
datadesc = ms.get_data_description(id=3)
pol_id = datadesc.get_polarization_id("XY")
```

#### Retrieving spectral windows for an MS

```python
# Restore latest context from disk.
import pipeline
context = pipeline.Pipeline(context='last').context

# Retrieve measurement set domain object.
vis = 'myvis.ms'
ms = context.observing_run.get_ms(vis)

# Get a list of spectral windows in the MS.
spws = ms.get_spectral_windows()
```



## Logging


### Log files for individual tasks
The `casapy.log` that gets linked from the task page is generated upon pickling a
task result after execution. The contents of this log file are taken from the
temporary `result.casalog` property that is populated by the `capture_log`
decorator. This temporary property is deleted as soon as the stage log is written
to disk, to reduce the size of the final result pickle that is serialized to disk.

The `capture_log` decorator is only appropriate for (and used around) the
`infrastructure.basetask.StandardTaskTemplate.execute` method, and so it currently
can only ever capture what happens during execution of the main task heuristics
(primarily its `prepare` and `analyse` methods) but not what occurs during QA or
weblog generation.

At present, the QA heuristic evaluation and weblog generation are kicked off as part
of accepting a task result (from a task that finished execution) into the Pipeline
context, in `infrastructure.basetask.Result.accept` that is invoked by
`infrastructure.basetask.Executor.execute`.

The `capture_log` decorator operates directly on the CASA log file (and CASA's `casalog`),
bypassing the `pipeline.infrastructure.logging` that is used throughout pipeline
to handle logging.


### Log handling for attention, warning, and error notifications in weblog
Separate from `result.casalog`, there also exists a `result.logrecords` property.
This is initially populated by `basetask.StandardTaskTemplate.execute` itself
(rather than a decorator for `result.casalog`) and later further appended to by
`pipelineqa.QARegistry.do_qa`.

Both at the init and append steps, the logging handlers only intend to capture
errors, warnings, and attention level messages, as `result.logrecords` is only
ever used by the weblog renderer, for the purpose of generating
warning/error/attention notifications and corresponding badges.

Over the years, a couple of exceptional cases were introduced with the aim of
capturing these kinds of notifications when they occur during weblog generation.
To this end, in the weblog renderer module of a couple of tasks, a logging
handler has been wrapped around a particular rendering step (e.g. creating some
plot) to capture any error/warning/attention messages from there, and add those
to `result.logrecords` as well. Since these are still messages that occur
during weblog generation, added to `result.logrecords`, these messages will only
show up as notifications in the weblog (banner at top of page), but not in the
task-specific `casapy.log`.



## Weblog rendering
The pipeline weblog generator is implemented in `infrastructure.renderer.htmlrenderer.WebLogGenerator`.

The weblog rendering is always executed on the "pipeline context", not on an
individual task result. As such, the weblog generator cannot render results that
have not (yet) been accepted into the context.

During a pipeline run, weblog rendering is triggered as a step after execution of
the main task heuristics, during the step where the task `Results` are accepted
into the Pipeline context, as implemented in `infrastructure.basetask.Results.accept`.

Weblog generation can be disabled with the module-level variable
`infrastructure.basetask.DISABLE_WEBLOG`, e.g.:

```python
import pipeline.infrastructure.basetask as basetask
basetask.DISABLE_WEBLOG = True
# continue with execution of Pipeline stages, recipereducer, or executeppr...
```
or at time of Pipeline initialisation with:
```python
h_init(weblog=False)
```

Weblog generation can also be triggered after a Pipeline run has completed, with:
```python
import pipeline.infrastructure.renderer.htmlrenderer as htmlrenderer
context = h_resume(filename='last')
htmlrenderer.WebLogGenerator.render(context)
```

However, at present, there are various pipeline stages where the weblog rendering
will include steps that create statistics (e.g. flagging summary) or plots based on the
state that the Measurement Set is left in at the end of the pipeline stage.
As such, decoupling weblog rendering from task execution is possible, but running
weblog generation for the first time at the end of the pipeline run would currently
lead to the weblog of several stages looking different, because the measurement set
will have been changed in subsequent stages (typically updates to flagging,
corrected amplitude, and/or model data columns).

There are already a couple of tasks that need to create plots during execution of
the task heuristics, because those plots need to reflect the temporary state of the
measurement set during the task. Examples include: `hifa_bandpassflag`,
`hifa_gfluxscaleflag`, `hifa_targetflag`, `hifa_polcalflag`, which all use a mid-task
temporary applycal. 



## Single-vis, multi-vis, and session-aware tasks
By default, each pipeline task is considered a single-vis task, which means that
if invoked on a list of measurement sets, the task will automatically be executed
separately for each measurement set, with the `Results` object from each execution
aggregated into a `ResultsList` that is returned by the single-vis task. This handling
is implemented in `infrastructure.basetask.StandardTaskTemplate.execute`.

A task can declare itself to be multi-vis with the `is_multi_vis_task` class
property. Examples include the `exportdata` and `restoredata` tasks, and many
tasks in the "imaging" pipeline. A multi-vis task is not necessarily a
session-aware task. Many multi-vis tasks merely process all input measurement sets
at once, without regard of what session each measurement set belongs to.

Session-aware tasks were first foreseen as necessary for the future implementation
of "group processing": processing a group of measurement sets that were observed
as part of a "session", where certain measurement sets no longer contain all required
calibrator intents themselves but instead need to be calibrated using calibration
scans from a different measurement set in the same session.

Initial updates to the pipeline framework to support sessions were introduced in
[CAS-10781](https://open-jira.nrao.edu/browse/CAS-10781) around Fall 2017 for the Cycle 6 release, see commit
[0a23bd5b](https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline/commits/0a23bd5b85154118371d3bfedf9fbc7a50bb4bfc).

As part of CAS-10781, prototype of 2 session-aware tasks were introduced:
- the `session_bandpass` task defined in `hifa.tasks.bandpass.almaphcorbandpass.SessionALMAPhcorBandpass` is a prototype of bandpass task that would process a session of MSes where one or more MSes might miss a bandpass calibrator; for those MSes without a bandpass, it would take a bandpass scan from another MS that is closest in time.
- the `session_gfluxscale` task defined in `hifa.tasks.fluxscale.gcorfluxscale.SessionGcorFluxscale` is a prototype that would process a session of MSes, adopting flux calibrations from one MS to another MS if the latter were to be missing a flux calibrator 

Note: as of September 2025, these tasks are still prototypes that are not validated,
have never been used in recipes / production, and are not actively maintained. To
avoid ongoing maintenance, these tasks could be commented out or removed from their module.

A task is session-aware when it acts separately on each session and its corresponding list of MSes. 

As of September 2025, the following Pipeline tasks are session aware, as
indicated by their use of `pipeline.infrastructure.sessionutils.group_vislist_into_sessions`:
- hifa_session_refant:
  - used in ALMA IF polarization calibration cal recipes.
  - considers all MSes within a session to assess the best single common reference antenna list.
- hifa_polcal:
  - used in ALMA IF polarization calibration cal recipes.
  - performs polarization calibration separately for each session, combining measurement sets within each session.
- hif_makeimlist:
  - used in numerous ALMA IF and VLA (imaging) recipes
  - if called with `inputs.per_session=True` (default: False), `hif_makeimlist` will create an image target per session.



## Stage numbers in filenames
The pipeline stage number that is used in pipeline products () is composed of two elements:
- the task counter: incremented in StandardTaskTemplate.execute when the task-to-be-executed is the top-level task.
- the sub-task counter: incremented in StandardTaskTemplate.execute when the task-to-be-executed is not the top-level task.

This stage number, e.g. "s17.3", is included in the filenames of intermediate Pipeline products (such as caltables, plots)
that are all stored in the same common 'working' directory, to ensure these products have unique filenames, even if a
task re-runs a gaincal step multiple times (different sub-tasks) or a pipeline task is run multiple times in a recipe.

The stage number is added to a task result as `result.stage_number` by `infrastructure.basetask.result_finaliser`.



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
https://casadocs.readthedocs.io/en/stable/api/tt/casatools.msmetadata.html#casatools.msmetadata.msmetadata.almaspwse description of almaspw

The above-mentioned "kinds" of spectral windows are not recorded as a property in `SpectralWindow` and instead are
determined in different manners for the different kinds. Moreover, these "kinds" are local definitions used by Pipeline
that may not be recognized by other ALMA subsystems. 

### Science spectral windows
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

### Tsys spectral windows
Tsys spectral windows are used to measure the system temperature, and used during Tsys calibration scans that
cover the "ATMOSPHERE" intent.

Depending on how the observation is set up, the Tsys SpWs can be the same as the science SpWs or they can be defined
as separate dedicated SpWs. The latter can occur for example when the science scans use high spectral resolution
(FDM mode) spectral windows while the Tsys scans are normally performed with lower resolution (TDM mode)
spectral windows.

Identifying a Tsys spectral window is defined in `h.heuristics.tsysspwmap` as either:
- spectral windows that are present in a Tsys solutions caltable created by CASA, or
- spectral windows in MS that cover 'ATMOSPHERE' intent and whose type is 'TDM'

### Diffgain reference and diffgain on-source spectral windows
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

### Tsys SpW to target SpW mapping
The Tsys spectral window to target (science) spectral window mapping is defined in `h.heuristics.tsysspwmap.tsysspwmap`.

The resulting `spwmap` is primarily used in the `h_tsyscal` task that creates and registers the Tsys calibration.
This task first creates the Tsys caltable and then creates the `spwmap` that maps each target SpW to its appropriate Tsys
SpW. This `spwmap` is then used in the step that creates the `CalApplications` that will register (in the callibrary)
how the Tsys caltable should be applied to the measurement set. Any subsequent task downstream that needs to (pre-)apply
the calibrations (e.g. `gaincal`, `applycal`) would then apply this Tsys caltable with the correct value of `spwmap`.

Note: a secondary use of `h.heuristics.tsysspwmap.tsysspwmap` occurs in
`hifa.heuristics.atm.AtmHeuristics._calculate_median_tsys`, used only
locally to compute median Tsys per science SpW.

### Phase-offset gaincal calibrator SpW to target SpW mapping
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

### Diffgain reference SpW to diffgain on-source SpW mapping
For band-to-band calibrations, the phase SpW-to-Spw mapping derived in `hifa_spwphaseup` for the `PHASE` calibrator
requires an adjustment to ensure that diffgain on-source SpWs are remapped to an associated diffgain reference SpW.
This kind of diffgain-specific `spwmap` adjustment is implemented in
`hifa.heuristics.phasespwmap.update_spwmap_for_band_to_band`, and is used in `hifa_spwphaseup` and
`hifa_diffgaincal`.
