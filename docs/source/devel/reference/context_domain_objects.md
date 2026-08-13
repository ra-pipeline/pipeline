# Context and Domain Objects

The Pipeline Context is the Pipeline's record of state, used to:
- Transfer state from task to task
- Quickly access (cached) info about the dataset without expensive I/O to disk
- Save the state of a pipeline run to disk to be able to restore/resume from disk in a future session

The domain objects are logical representations of real-world concepts in the radio interferometry domain, and form
the core building blocks for the Pipeline application.

## Overview of Context

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

## Overview of domain objects

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


## Using the pipeline context

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


## Accessing the pipeline context via task interface

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


## Accessing the pipeline context using Python classes directly

Initializing a new run / context and saving to disk:
```python
from pipeline.infrastructure import launcher
context = launcher.Pipeline().context
context.save()
```

Resuming previous run / context:
```python
from pipeline.infrastructure import launcher
context = launcher.Pipeline(context='last').context
```


## Example interactions with the Pipeline context and its domain objects

### Context queries: info about pipeline run, results

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

### Context queries: measurement sets

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

### Context queries: virtual spectral windows

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

### MeasurementSet queries: spectral windows

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

### MeasurementSet queries: fields

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

### MeasurementSet queries: scans

```python
# Get IDs of all scans.
ms = context.observing_run.get_ms(name=vis)
scan_ids = [scan.id for scan in ms.get_scans()]

# Get time on source for scans with PHASE intent for selected fields.
times = [scan.time_on_source
         for scan in ms.get_scans(field="J1851+0035,W43-MM1", scan_intent="PHASE")]
```

### MeasurementSet queries: data descriptions

```python
# Get polarization ID for given MS, SpW ID, and correlation type.
ms = self.inputs.context.observing_run.get_ms(name=vis)
datadesc = ms.get_data_description(id=3)
pol_id = datadesc.get_polarization_id("XY")
```

### Retrieving spectral windows for an MS

```python
# Restore latest context from disk.
from pipeline.infrastructure import launcher

context = launcher.Pipeline(context='last').context

# Retrieve measurement set domain object.
vis = 'myvis.ms'
ms = context.observing_run.get_ms(vis)

# Get a list of spectral windows in the MS.
spws = ms.get_spectral_windows()
```


