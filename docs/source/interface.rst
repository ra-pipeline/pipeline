====================================
Interface Overview
====================================

.. contents:: Table of Contents
   :depth: 2
   :local:

--------

Pipeline Input and Output
-------------------------

The following diagram illustrates the main inputs and outputs of the Pipeline processing workflow.

.. mermaid::

    %%{init: {'flowchart': {'curve': 'basis', 'padding': 20}}}%%
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
