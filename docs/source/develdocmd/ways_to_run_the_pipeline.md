# Ways to run the Pipeline

## PPR: pipeline processing request

At the highest level of abstraction, we can execute a pipeline processing request (ppr), which is how Pipeline
is run in operations at the ALMA centers.

This can be done at the command line, or at a CASA command prompt.

Execute PPR from the command line:

```console
$ casa --nologger --nogui --log2term --agg -c $SCIPIPE_HEURISTICS/pipeline/runvlapipeline.py PPRnew_VLAT003.xml
```

At a CASA command prompt:

```python
# execute a pipeline processing request (PPR)
CASA <1>: import pipeline.infrastructure.executevlappr as eppr
CASA <2>: eppr.executeppr('PPR_VLAT003.xml', importonly=False)
```


## Series of steps invoking CASA Pipeline tasks

A little lower level of abstraction would be to run the pipeline as a series of
steps as described in the VLA pipeline [casaguide](https://casaguides.nrao.edu/index.php/VLA_CASA_Pipeline-CASA4.5.3)

At the lowest level of abstraction, we can run the pipeline as a series of steps
like the following

A pipeline run will generate a file like the following:

```
pipeline_test_data/VLAT003/working/pipeline-20161014T172229/html/casa_pipescript.py
```

It contains a series of steps like those described in the casaguide.

We can execute this script from CASA

```python
CASA <1>: execfile('casa_pipescript.py')
```

Or we can run it from the command line:

```console
$ casa --nogui --log2term -c casa_pipescript.py
```

We can edit the script and turn on memory usage for each task:

```python
CASA <1>: h_init()
CASA <2>: import pipeline
CASA <3>: pipeline.infrastructure.utils.enable_memstats()
```

We can also turn weblog and plotting off:

```python
CASA <1>: h_init(loglevel="info", plotlevel="summary", output_dir="./", weblog=False, overwrite=True)
```

Or we can turn debug mode on, weblog off:

```python
CASA <1>: h_init(loglevel="debug", plotlevel="summary", output_dir="./", weblog=True, overwrite=True)
```

Full example of running Pipeline importdata task on CASA prompt:

```python
CASA <1>: h_init()
CASA <2>: h_save()
CASA <3>: import pipeline
CASA <4>: hifv_importdata(vis=['../rawdata/13A-537.sb24066356.eb24324502.56514.05971091435'], session=['session_1'], overwrite=False)
CASA <5>: h_save()
CASA <6>: exit
```

Resuming from a previous Pipeline run on CASA prompt:
```python
casa
CASA <1>: context = h_resume(filename='last')
```


## Creating and running Pipeline tasks in Python, bypassing the task interface

At the lowest level of abstraction, we can bypass the CASA Pipeline Task interface, and work directly within
CASA / Python, by instantiating a Pipeline `InputsContainer` object for the Pipeline Task, using it to instantiate a
Pipeline Task object, and then running its `execute` method to get the task result, as shown in the example below. Here,
the example should be run in a directory where the Pipeline has been partly run, i.e. a context already exists.

```python
from pipeline.infrastructure import launcher

context = launcher.Pipeline(context='last').context
inputs = pipeline.infrastructure.vdp.InputsContainer(pipeline.hifv.tasks.hanning.Hanning, context)
task = pipeline.hifv.tasks.hanning.Hanning(inputs)
result = task.execute()
result.accept(context)
context.save()
```

If we don't have a PPR or an executable script available.

```python
$ casa
import pipeline.recipes.hifv as hifv
from pipeline.infrastructure import launcher

# the next line will only importevla and save a context, b/c importonly=True
hifv.hifv(['../rawdata/13A-537.foofoof.eb.barbar.2378.2934723984397'], importonly=True)

context = launcher.Pipeline(context='last').context
vis = '13A-537.foofoof.eb.barbar.2378.2934723984397.ms'
# get the domain object
m = context.observing_run.get_ms(vis)
type(m)
# study this m object for INTENTS
# <class 'pipeline.domain.measurementset.MeasurementSet>
m.intents  # shows a python set of the MS intents
m.polarization  # show a list of polarization objects
```


## Running Pipeline with the "recipereducer"
The `recipereducer` module is a tool for Pipeline developer to be able to run
the Pipeline without using the Pipeline Processing Request (PPR) system that is
only available at the ALMA centers.

All that you need to pass along to the `recipereducer` is the recipe name and the
path to a directory containing the raw ASDM datasets.

### Simple "recipereducer" example
Run pipeline for your ASDM, with default pipeline recipe (hifa_calimage):
```python
import pipeline.recipereducer
pipeline.recipereducer.reduce(
  vis=['../rawdata/yourasdm'],
  # procedure='procedure_hifa_calimage.xml',
)
```

### About the procedure parameter
For the `procedure` parameter, you can specify either:
- the filename of one of the standard recipes (procedure files) located in `pipeline/recipes`
- a relative/absolute path to a file containing your own (customized) recipe file, 
  e.g. `procedure='/path/to/local/procedure.xml'`, or `procedure='../test_procedure_for_PIPE-1234.xml'`

If the `procedure` parameter is not specified, `recipereducer` will by default
run the full ALMA calibration + imaging recipe, `procedure_hifa_calimage.xml`.

### Examples with a different procedure file
Run Single-Dish calibration + imaging on 2 ASDMs:
```python
import pipeline.recipereducer
pipeline.recipereducer.reduce(
  vis=['../rawdata/yourasdm', '../rawdata/yourasdm_2'],
  procedure='procedure_hsd_calimage.xml',
)
```

Run VLA standard recipe:
```python
import pipeline.recipereducer
pipeline.recipereducer.reduce(
  vis=['../rawdata/yourasdm'],
  procedure='procedure_hifv.xml',
)
```

Run with a local copy of a recipe that you may have modified for development:
```python
import pipeline.recipereducer
pipeline.recipereducer.reduce(
  vis=['../rawdata/yourasdm'],
  procedure='../test_procedure_for_PIPE-1234.xml',
)
```

### Examples of stopping / starting at specific stages
Stop after stage 3 has completed. It will depend on the recipe which task this
stage number corresponds to.
```python
import pipeline.recipereducer
pipeline.recipereducer.reduce(
    vis=['../rawdata/yourasdm'],
    procedure='procedure_hifa_calimage.xml',
    exitstage=3,
)
```

Assuming the developer developed / debugged stage 4, once that is done, it is
possible to use `recipereducer` to resume with the remainder of the recipe, with:
```python
import pipeline.recipereducer
from pipeline.infrastructure import launcher

context = launcher.Pipeline(context='last').context
pipeline.recipereducer.reduce(
    vis=['../rawdata/yourasdm'],
    context=context,
    procedure='procedure_hifa_calimage.xml',
    startstage=5,
)
```
Here, since Pipeline is resuming from an earlier run, so the existing context is passed into `recipereducer`.

### Example with sessions
Some datasets will have measurement sets grouped together in separate sessions, which can be specified with:
```python
import pipeline.recipereducer
pipeline.recipereducer.reduce(
    vis=['../rawdata/yourasdm_1', '../rawdata/yourasdm_2', '../rawdata/yourasdm_3'],
    session=['session1', 'session3', 'session3'],
    procedure='procedure_hifa_calimage.xml',
    exitstage=3,
)
```
Here, the 1st ASDM belongs to "session1" while the latter 2 ASDMs are both in "session3".
Note, session names are assigned during operations, will normally be populated in the PPR files, and may not
always appear to have sequential numbers. 

### Example changing log level
If not specified, the loglevel is `info` by default, but this can be change to e.g. `debug` or `trace` to get 
(a lot) more diagnostic information during the run:
```python
import pipeline.recipereducer
pipeline.recipereducer.reduce(
    vis=['../rawdata/yourasdm_1'],
    loglevel='debug',
    plotlevel='summary',
)
```

### Example workflows for a Pipeline developer

For developers, a common workflow is to iteratively run a specific task to reproduce an issue, debug a specific task,
and/or implement a new stage.

Pipeline does not currently support snapshotting of the state after each run, and various pipeline tasks do
permanently change the stage of the measurement set (flagging, corrected, and/or model column) or calibration state in
the context. As a result, it would normally not be representative to keep re-running the same stage multiple times in
a row, as each subsequent execution starts from a different state.

Since a full Pipeline run can take a significant amount of time (hours to days depending on the size and complexity of
the dataset), a recommended workflow for developers would be to:

- run with recipereducer and the `exitstage` option up to the start of the stage you want to debug / implement
- create a tarball of the `working` directory, or restore the `working` directory from a previously created tarball
- run the stage-to-develop/debug individually (regular or in interactive debugger mode)

To this end, it may help to create a couple of custom Python scripts:

A `template.script` that runs pipeline up to just before the stage where you wish to implement / debug a task.
```python
import pipeline.recipereducer
pipeline.recipereducer.reduce(
    vis=['../rawdata/yourasdm'],
    loglevel='info',
    # exitstage=1,  # uncomment this line and set correct stage to stop after.
)
```
Place it in the parent of the working directory, and run with:
```console
cd working
casa -c ../template.script
```

A `debug.script` that executes an individual task:
```python
task_to_run = 'hifa_tsysflag'

import pipeline
from pipeline.infrastructure import task_registry, launcher

context = launcher.Pipeline(context='last', loglevel='info', plotlevel='default').context

taskclass = task_registry.get_pipeline_class_for_task(task_to_run)
inputs = pipeline.infrastructure.vdp.InputsContainer(taskclass, context)

# Optionally override input parameter(s) for debugging, e.g.:
# inputs.normalize_tsys = True

task = taskclass(inputs)
result = task.execute()
result.accept(context)
context.save()
```

Place it in the parent of the working directory, and run with:
```console
casa -c ../debug.script
```

Note: as an alternative to re-running an entire task for investigating and debugging issues, see the
`infrastructure.utils.utils.function_io_dumper` decorator functionality that is documented in `FunctionIODumper.md`,
introduced in [PIPE-2354 (2025 release)](https://open-jira.nrao.edu/browse/PIPE-2354).

Note: a Pipeline run is relocatable, so one can resume from a working directory (and context) that is located at
a different path from where the run was originally started. Depending on the ticket at hand, this can allow a developer
a couple of short-cuts:

- Create a run up through stage N, tarball `working` to snapshot, and optionally unpack to multiple copies
  (working1, working2, working3) to run (in parallel) a given stage with different checkouts of the Pipeline.
- When working on a shared cluster such as at NRAO Charlottesville, one can copy the run from a different developer / 
  PWG member into their own workspace, and resume the context (optionally even one of the pickled results from the
  stage, located under `pipeline-[...]/saved_state`) to inspect the context, re-run a stage with the
  interactive debugger, etc. This can be particularly useful for times where one has to urgently debug an issue that
  occurred for a large dataset.


## Create custom Pipeline processing recipes from SRDP Mustache templates

The SDRP templates are [mustache](http://mustache.github.io/) templates that can be used to generate custom SDRP processing recipe XML files.
All templates are located in the [pipeline/recipes](pipeline/recipes) directory (template_*.xml).
A mustache template contains both the XML and the mustache tags, the latter of which allows the insertion of values from the JSON file into the XML during rendering.

To generate a custom SDRP recipe, you will need to create a JSON file that contains the custom mustache tag values. Once the JSON file is prepared, we can render the SDRP recipes for testing.
Two [recommended](https://open-jira.nrao.edu/browse/PIPE-72?focusedCommentId=140995&page=com.atlassian.jira.plugin.system.issuetabpanels:comment-tabpanel#comment-140995) rendering options are below:

* Use the demo page on the [mustache](http://mustache.github.io/) site.  You can copy and paste the text from the JSON file and template into the boxes and click the "Render Template" button.

* Use a Python Library, e.g. [pystache](https://github.com/PennyDreadfulMTG/pystache) or [chevron](https://github.com/noahmorrison/chevron), you could do something like this:

```python
import json, pystache
with open('pipeline/recipes/tests/test_hifa_cubeimage.json') as f_json, open('template_hifa_cubeimage.xml') as f_template:
    d = json.load(f_json)
    t = f_template.read()
    with open('recipe.xml', 'w') as out:
        out.write(pystache.render(t,d))
```

## Workflow Break/Resume

### Context-by-Stage

The context content at individual stages can be pickled after the completion of each PL task.
The [implementation](https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline/commits/bf904d167c09c2f7a9e648ce3e30122185887586) is in `infrastructure.basetask` and will only be switched on if the pipeline is in the `DEBUG` (or lower) logging level. This feature works for both PPR and recipereducer runs.

The path of pickled context files is: `output_dir`/`context_name`/`saved_state`/`context-stage*.pickle`, saved along with `result-stage*.pickle` which is always present in the same directory.

### Break/Resume

- `executeppr` offers a "break/resume" feature at the workflow level (see the optional keywords [`bpaction` and `breakpoint`](https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline/browse/pipeline/infrastructure/executeppr.py)). One practical example is below, which is based on the test data available in the [pipeline-testdata](https://open-bitbucket.nrao.edu/projects/PIPE/repos/pipeline-testdata) repository:

  - pl-unittest/uid\_\_\_A002_Xc46ab2_X15ae_repSPW_spw16_17_small.ms
  - pl-regressiontest/uid\_\_\_A002_Xc46ab2_X15ae_repSPW_spw16_17_small/PPR.xml

  We first put the above MeasurementSet and PPR in the `rawdata` directory of your workspace. This specific PPR file already has a breakpoint set after the first `hifa_exportdata` call:

  To run the PPR up to the breakpoint, at a CASA command prompt,

  ```python
  import os
  import pipeline.infrastructure.executeppr as eppr
  os.environ['SCIPIPE_ROOTDIR'] = os.getcwd()
  eppr.executeppr('../rawdata/PPR.xml', importonly=False, loglevel='debug', bpaction='break')
  ```

  From the current or a new CASA session, the PPR can be resumed,

  ```python
  import os
  import pipeline.infrastructure.executeppr as eppr
  os.environ['SCIPIPE_ROOTDIR'] = os.getcwd()
  eppr.executeppr('../rawdata/PPR.xml', importonly=False, loglevel='debug', bpaction='resume')
  ```

  **Note**: if you try to run the PPR with bpaction='resume' again, the subsequent call(s) will likely fail: `executeppr` is hardcoded to resume from the "last" context (i.e. a `.context` file with the latest timestamp from your working directory), but we need the context content from the "breakpoint" stage to resume. Also, the file states (e.g. MSs, caltables) have changed. The only safe option is making a copy of the working directory before trying resume in case you might tweak the PPR in another attempt.

  For development/test purposes, one workaround to avoid copying the entire working directory is to create a fresh copy of the context pickled from the "breakpoint" stage (where your loglevel='debug' setting is crucial) in the existing working directory:

  First, you back up the context pickle files from different stages:

  ```console
  $ cp -rf pipeline-20210421T172403/saved_state pipeline-20210421T172403/saved_state_backup
  ```

  Then, at a CASA command prompt,

  ```python
  import os
  os.environ['SCIPIPE_ROOTDIR'] = os.getcwd()
  os.system('cp -rf pipeline-20210421T172403/saved_state_backup/context-stage26.pickle current.context')
  # we need some cleanup as this MS below is blocking the execution of the stage27 hif_mstransform() call.
  os.system('rm -rf uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small_target.ms*')
  import pipeline.infrastructure.executeppr as eppr
  eppr.executeppr('../rawdata/PPR.xml', importonly=False, loglevel='debug', bpaction='resume')
  ```

  Again, please note that the above workaround might yield scientifically meaningless results due to the changing file status and is only useful for testing under certain scenarios.
  All break/resume approaches use the **current** files (e.g. MSs/caltables) in your working directory. So be aware of the existence of files/versions that might be unexpected to the resumed PL workflow task call(s)!

- With `recipereducer`, you can load context saved at a specific stage from the working directory and run/rerun the next PL task designed in the workflow (also see the demonstration in the last section).

  A full recipe run with the above test data example can be done via,

  ```python
  import pipeline.recipereducer, os
  pipeline.recipereducer.reduce(vis=['../rawdata/uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.ms'],
                              procedure='procedure_hifa_calimage.xml', loglevel='debug')
  ```

  With the context pickled from individual stages, you may pick and test a single pipeline stage in your development:

  ```python
  task_to_run='hif_checkproductsize'
  task_keywords={'maxcubesize':40.0,'maxcubelimit':60,'maxproductsize':500.0}
  import pipeline
  from pipeline.infrastructure import task_registry, launcher
  context = launcher.Pipeline(context='pipeline-procedure_hifa_calimage/saved_state/context-stage24.pickle', loglevel='debug', plotlevel='default').context
  taskclass = task_registry.get_pipeline_class_for_task(task_to_run)
  inputs = pipeline.infrastructure.vdp.InputsContainer(taskclass, context, **task_keywords)
  task = taskclass(inputs)
  result = task.execute()
  result.accept(context)
  context.save('test-context-stage25.pickle')
  ```

  `recipereducer` doesn't offer the "breakpoint" feature built in `executeppr`. However, a calculated usage of `starttage`/ `exitstage`/`context` keywords may achieve the same workflow-level "break/resume":

  ```python
  from pipeline.infrastructure import task_registry, launcher
  context = launcher.Pipeline(context='pipeline-procedure_hifa_calimage/saved_state/context-stage3.pickle', loglevel='debug', plotlevel='default').context
  import pipeline.recipereducer
  pipeline.recipereducer.reduce(vis=['../rawdata/uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.ms'],
                                procedure='procedure_hifa_calimage.xml', loglevel='debug',startstage=4,exitstage=20,
                                context=context)
  ```

## Re-render Weblog

A common development task is improving weblog. Without re-running a
time-consuming pipeline task itself, you can only re-render the weblog using the
existing context/result to test a small weblog-related change (e.g., minor tweaks
in mako templates). Note: this will only rerun the weblog rendering portion of a
pipeline stage (therefore limits your testing scope).

```python
import os
import pipeline.infrastructure.renderer.htmlrenderer as hr
from pipeline.infrastructure import launcher

# Modify this to select which stage number to re-render weblog for.
os.environ['WEBLOG_RERENDER_STAGES'] = "16"

context = launcher.Pipeline(context='last', loglevel='debug', plotlevel='default').context
hr.WebLogGenerator.render(context)
```

## Re-run QA heuristics
A common development task is to implement or improve the QA heuristics for a task.
The QA step is normally run after the main task heuristics are completed and the
task `Results` have been created. 

As such, after having run the task at least once, one can rapidly re-run the QA
heuristic on the existing task result in the context to iterate more rapidly on
the heuristic without having to re-run the time-consuming pipeline task itself.

```python
from pipeline.infrastructure import pipelineqa, launcher
context = launcher.Pipeline(context='last', loglevel='debug', plotlevel='default').context

# Modify this to select which stage to run QA for.
stage_number = 14

task_results = context.results[stage_number-1].read()
pipelineqa.qa_registry.do_qa(context, task_results)
```

Note, the snippet above only re-runs the QA heuristic on a copy of the results read
in from disk, and updates the QA scores in this copy of the results in-place.
However, this does not modify the results on disk nor does it attempt to re-run
the weblog rendering; therefore re-running the QA this way will not update the QA
scores that are displayed in the task weblog. Instead, the snippet is primarily
useful for interactively debugging the QA heuristics. Once debugged, it would be
recommended to re-run the entire stage.


## Note on using executeppr/recipereducer and Pipeline CLI tasks

All the above usecases rely on _global_ pipeline context object that holds various information on pipeline processing. Please be careful when executeppr/reciperedicer and CLI tasks are used together in a single CASA session, especially when running executeppr/recipereducer in the middle of interactive processing with CLI tasks, e.g.,

1. `h_init` to start interactive processing (creates context #1 and register it to global scope)
2. run various tasks interactively (with context #1)
3. run executeppr (creates context #2 and overwrite global context #1)
4. run some more tasks interactively (with context #2)

In this example, step 2. and 4. are no longer continuous because they refer different context object. In such case, please save context object to disk before running executeppr/recipereducer and resume it when necessary. The above workflow should be tweaked as below.

1. `h_init` to start interactive processing (creates context #1 and register it to global scope)
2. run various tasks interactively (with context #1)
3. save current state to disk with `h_save('interactive.context')` (save context #1 to disk)
4. run executeppr (creates context #2 and overwrite global context #1)
5. resume previous state to disk with `h_resume('interactive.context')` (load context #1 from disk and overwrite global context #2)
6. run some more tasks interactively (with context #1)



## Known issues

Don't worry about the following intermittent message at the end of a pipeline run. It's a bug
but it doesn't mean the pipeline was unsuccessful.

```console
invalid command name "102990944filter_destroy"
    while executing
"102990944filter_destroy 3657 ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? 0 ?? ?? .86583632 17 ?? ?? ??"
    invoked from within
"if {"[102990944filter_destroy 3657 ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? 0 ?? ?? .86583632 17 ?? ?? ??]" == "break"} break"
    (command bound to event)
```
