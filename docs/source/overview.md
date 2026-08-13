# Pipeline Overview

The Pipeline can be invoked in three ways, depending on the use case:

- **PPR XML** (production): a Pipeline Processing Request XML file specifies the data, task sequence, and processing intents. It is executed via `runpipeline.py` in a CASA session, which drives `executeppr()` in `pipeline.infrastructure.executeppr`.
- **Interactive CASA session**: tasks are called individually from the CASA prompt after importing them via `pipeline.initcli()`. This is the standard mode for development and debugging.
- **Python API**: tasks can be imported and called directly from a Python script, e.g. `from pipeline.cli import hifa_bandpass`.

## Task Namespaces

Pipeline tasks are grouped by telescope and observing mode using a prefix scheme:

```{list-table}
:header-rows: 1
:widths: 12 25 63

* - Prefix
  - Module
  - Scope
* - `h_`
  - `pipeline/h/`
  - Generic (all modes): `h_init`, `h_save`, `h_resume`, `h_weblog`
* - `hif_`
  - `pipeline/hif/`
  - Generic interferometry
* - `hifa_`
  - `pipeline/hifa/`
  - ALMA interferometry
* - `hifv_`
  - `pipeline/hifv/`
  - VLA interferometry
* - `hsd_`
  - `pipeline/hsd/`
  - ALMA single-dish
* - `hsdn_`
  - `pipeline/hsdn/`
  - Nobeyama single-dish
```

## Session Lifecycle

A pipeline session is built around a **Context** object, which holds all state (domain data, calibration tables, results, directory paths) across tasks. It is persisted to disk as a `.context` pickle file after each task.

A typical session follows this pattern:

```python
h_init()               # create a new Context; opens a pipeline session
hifa_importdata(...)   # load raw data into the Context
hifa_flagdata(...)     # each task reads and updates the Context
# ... further tasks ...
hifa_exportdata(...)   # write final products
h_save()               # persist the Context to disk
```

The Context is an implicit input to every task: each task's `Inputs` object is
initialised with the current Context (via `Inputs.create_from_context(context)`),
giving tasks read access to all prior results, calibration state, and domain
data, without the user needing to pass it explicitly on the command line.

An interrupted session can be resumed with `h_resume()`, which restores the last saved Context.

In practice, pipeline runs are launched in one of two ways:

- **PPR XML** (production): a Pipeline Processing Request XML file drives the full task sequence automatically — this is how pipeline runs are triggered at observatory processing centers.
- **Script replay**: each completed run produces a `casa_pipescript.py` that can be re-executed or edited to reproduce or modify the run.

For full details and examples of both approaches, see {doc}`devel/usage/running_pipeline`.

## Output Products and Weblog

After each task, the Pipeline renders an HTML weblog incrementally into `<output_dir>/<context_name>/html/`. The weblog entry point is `t1-1.html`. Final data products (images, calibration tables, restore scripts, archive tars, AQUA report) are written to the `products/` directory.

The weblog can be opened in a browser from a CASA session with `h_weblog()`, which starts a local HTTP server.

## Pipeline Input and Output

The following diagram illustrates the main inputs and outputs of the Pipeline processing workflow.

```mermaid
%%{init: {'flowchart': {'curve': 'basis', 'padding': 20, 'useMaxWidth': false}}}%%
graph LR
    subgraph Inputs [Input Data]
        direction TB
        in1([uncalibrated data]):::blueInput
        in2([lists of data to flag]):::blueInput
        in3([antenna position corrections]):::blueInput
        in4([flux catalogue measurements]):::blueInput
        in5([known spectral lines in the flux calibrator spectrum]):::greenInput
        in6([additional lists of data to flag]):::greenInput
        in7([user-provided flux measurements]):::greenInput
        in8([continuum range definitions]):::greenInput
        in9([user-provided calibration tables]):::greenInput
    end

    subgraph Controls [Flow Control/Parameters]
        c1([pipeline processing request PPR])
        c2([interactive input in a CASA session])
    end

    subgraph Process [Processing]
        P([Pipeline]):::whiteProcess
    end

    subgraph Outputs [Pipeline Products]
        direction TB
        out1([flagged calibrated data]):::orangeOutput
        out2([flagged calibration tables]):::orangeOutput
        out3([calibrated images]):::orangeOutput
        out4([execution logs]):::orangeOutput
        out5([web log]):::orangeOutput
        out6([AQUA report]):::orangeOutput
        out7([restore scripts]):::orangeOutput
        out8([archive manifest]):::orangeOutput
        out9([tars for archive ingest]):::orangeOutput
    end

    %% Styles for the Subgraph Boxes
    style Inputs fill:#f0f8ff,stroke:#6c8ebf,stroke-dasharray: 5 5
    style Controls fill:#f0f8ff,stroke:#6c8ebf,stroke-dasharray: 5 5
    style Process fill:#ffffff,stroke:#333,stroke-dasharray: 5 5
    style Outputs fill:#fff5e6,stroke:#d79b00,stroke-dasharray: 5 5

    %% Connections
    in1 --> P
    in2 --> P
    in3 --> P
    in4 --> P
    in5 --> P
    in6 --> P
    in7 --> P
    in8 --> P
    in9 --> P

    c1 --> P
    c2 --> P

    P --> out1
    P --> out2
    P --> out3
    P --> out4
    P --> out5
    P --> out6
    P --> out7
    P --> out8
    P --> out9

    %% Styling Classes for Nodes
    classDef blueInput fill:#dae8fc,stroke:#6c8ebf,stroke-width:2px,color:black,rx:15,ry:15;
    classDef greenInput fill:#d5e8d4,stroke:#82b366,stroke-width:2px,color:black,rx:15,ry:15;
    classDef whiteProcess fill:#ffffff,stroke:#333333,stroke-width:3px,color:black,rx:15,ry:15,font-size:16px;
    classDef orangeOutput fill:#ffe6cc,stroke:#d79b00,stroke-width:2px,color:black,rx:15,ry:15;

    %% Link Styling
    linkStyle 0,1,2,3,4,5,6,7,8,9,10 stroke:#6c8ebf,stroke-width:3px,fill:none;
    linkStyle 11,12,13,14,15,16,17,18,19 stroke:#d79b00,stroke-width:3px,fill:none;
```
