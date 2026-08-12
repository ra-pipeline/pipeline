# Pipeline Versions & Documentation

## Obtaining the Pipeline

A link to the CASA+pipeline package is available, along with installation instructions and supporting documentation, from the **Overview and Pipeline** section of the **ALMA Science Portal** at <http://www.almascience.org> (under the "Processing" tab, or directly at <http://almascience.org/processing/>). If any issues are encountered with CASA installation, please contact the [ALMA Helpdesk](https://help.almascience.org/) via the link on the ALMA Science Portal.

The pipeline tasks become available by starting up CASA using the command:

```
% casa --pipeline
```

Or to run CASA with pipeline tasks using MPI (multi-core parallelization):

```
% mpicasa -n 8 casa --pipeline
```

Note that you may need to provide the full path to `casa` in the `mpicasa` command line to initiate the desired version if you have multiple versions installed.

## Pipeline-related Documentation

The officially accepted user documentation for the ALMA Pipeline is listed on the Overview and Pipeline section of the Science Portal referenced above. This includes the **ALMA Science Pipeline User's Guide**, and the **ALMA Pipeline Reference Manual** (a detailed description of individual Pipeline tasks parameters).  Those used to be separate documents, but are now part hosted on this site.

Examples of common re-imaging modifications to the IF pipeline script are given at:
<https://casaguides.nrao.edu/index.php/ALMA_Imaging_Pipeline_Reprocessing>

An example of the pipeline processing for the total power data is available at: <https://casaguides.nrao.edu/index.php/Single-Dish_(Total_Power)_Data_Processing_with_Pipeline>

In addition, Chapters 10, 11, and 13 of the [ALMA Technical Handbook](https://almascience.nrao.edu/proposing/technical-handbook) provide more information on calibration in general, how Quality Assurance is performed, and how data is archived.

## Pipeline and CASA Versions

The pipeline heuristic tasks have a specific version number, and are bundled with a specific version of CASA. These versions are reported in the README file that is archived with the pipeline data products, and are also reported on the Home page of the WebLog for each pipeline-processed dataset (see {ref}`the WebLog Home Page example <fig-homepage>`).

CASA produces numerous releases, but only the versions listed in the table on the Science Portal <http://almascience.org/processing/> have been scientifically validated, are accepted for operations, and are supported by ALMA. That table additionally lists the versions which can be used to restore previously pipeline-calibrated archival visibility data.

Note that each CASA release often includes one or more updates to the third-party Python modules that are packaged with it. A summary of the changes in the CASA versions used between PL2023, PL2024, and PL2025 are shown in the table below.

(table-thirdparty)=
**Changes to third-party Python modules in CASA**

The ones likely to be of most interest to users are highlighted in bold.

```{list-table} Changes to third-party Python modules in CASA
:widths: 25 25 25 25
:header-rows: 1
:class: small-font-table

* - module
  - 6.5.4py3.8 (PL2023)
  - 6.6.1py3.8 (PL2024)
  - 6.6.6py3.10 (PL2025)
* - almatasks<sup>a</sup>
  - 1.6.1
  - 1.7.1
  - —
* - **Astropy**
  - 5.2.1
  - 5.2.2
  - 6.1.7
* - attrs
  - 22.2.0
  - —
  - —
* - backcall
  - 0.2.0
  - 0.2.0
  - —
* - bdsf
  - 1.10.2
  - 1.10.3
  - 1.13.0.post2
* - cachetools
  - 5.2.0
  - 5.3.1
  - 5.5.2
* - casaconfig
  - —
  - —
  - 1.1.1
* - certifi
  - 2022.12.07
  - 2023.07.22
  - 2024.7.4
* - csscompressor
  - 0.9.5
  - 0.9.5
  - 0.9.5
* - cycler
  - 0.11.0
  - 0.11.0
  - 0.12.1
* - decorator
  - 5.1.1
  - 5.1.1
  - 5.1.1
* - grpcio
  - 1.29.0
  - 1.26.0
  - 1.66.0
* - intervaltree
  - 3.1.0
  - 3.1.0
  - 3.1.0
* - ipython
  - 7.15.0
  - 7.34.0
  - 8.26.0
* - jedi
  - 0.18.2
  - 0.19.0
  - 0.19.1
* - kiwisolver
  - 1.4.4
  - 1.4.5
  - 1.4.5
* - logutils
  - 0.3.5
  - 0.3.5
  - 0.3.5
* - mako
  - 1.2.4
  - 1.2.4
  - 1.3.10
* - **Matplotlib**
  - 3.3.3
  - 3.5.0
  - 3.9.2
* - mpi4py
  - 3.1.3
  - 3.1.5
  - 3.1.5
* - **NumPy**
  - 1.23.5
  - 1.24.4
  - 2.0.1
* - Open MPI
  - 1.10.4
  - 5.0.1
  - 5.0.1
* - packaging
  - 23.0
  - 23.1
  - 24.1
* - parso
  - 0.8.3
  - 0.8.3
  - 0.8.4
* - pip
  - 23.0.1
  - 22.3.1
  - 22.3.1
* - pluggy
  - 1.0.0
  - 1.3.0
  - 1.5.0
* - prompt_toolkit
  - 3.0.36
  - 3.0.39
  - 3.0.47
* - ps_mem
  - 3.14
  - 3.14
  - 3.14
* - ptyprocess
  - 0.8.0
  - 0.7.0
  - 0.7.0
* - Pygments
  - 2.14.0
  - 2.26.1
  - 2.28.0
* - pyparsing
  - 3.0.9
  - 3.1.1
  - 3.1.2
* - pypubsub
  - 4.0.3
  - 4.0.3
  - 4.0.3
* - pytest
  - 7.2.1
  - 7.4.2
  - 8.3.2
* - pytz
  - 2022.7.1
  - 2023.3.1
  - 2024.1
* - **SciPy**
  - 1.10.0
  - 1.10.1
  - 1.14.1
* - setuptools
  - 56.0.0
  - 70.1.1
  - 65.5.0
* - traitlets
  - 5.8.1
  - 5.10.0
  - 5.14.3
* - wcwidth
  - 0.2.6
  - 0.2.6
  - 0.2.13
* - wheel
  - 0.41.2
  - —
  - —
```

<sup>a</sup> contained the CASA task `wvrgcal` (legacy `almatasks` package), which was migrated to {func}`CASA/wvrgcal <casatasks.calibration.wvrgcal>` in PL2025.

## Pipeline and CASA tasks

(sec-pipelinecasa)=
The pipeline heuristics are written as python functions appearing with a `hif_` or `hifa_` (for interferometric) or `hsd_` (for single-dish) prefix. They can be viewed and executed within CASA just as any python function (if one has launched CASA with "--pipeline"). For example, one can view the possible inputs for the task {func}`hifa_importdata <pipeline.hifa.cli.hifa_importdata>` by typing `?hifa_importdata`.

The pipeline heuristics use CASA tasks wherever possible to perform the data reduction or imaging. E.g. the pipeline bandpass calibration & flagging task {func}`hifa_bandpassflag <pipeline.hifa.cli.hifa_bandpassflag>` calls the CASA {func}`CASA/bandpass <casatasks.calibration.bandpass>` task, and the interferometric imaging task {func}`hif_makeimages <pipeline.hif.cli.hif_makeimages>` calls the CASA imaging task {func}`CASA/tclean <casatasks.imaging.tclean>`.

The standard pipeline processing recipes are deterministic and should always give the same result for the same data, if run on the same hardware allocation (number of cores, memory). However, the CASA pipeline tasks are designed to be highly flexible, so that they can have the default inputs over-ridden with user-specified values, or be added, subtracted, or rearranged to produce alternative processing recipes. This enables a manual "mix and match" mode for data reduction and imaging that combines standard CASA pipeline tasks with other CASA commands or python code to produce scripts that are better tuned to the idiosyncrasies of a specific dataset. The exact pipeline commands that will reproduce the standard recipe are delivered with each dataset, in a script called `member.<mous_uid>.<recipe>.casa_pipescript.py` (see {ref}`The Pipeline processing script <sec-pipescriptintro>` below). One can edit and add to that script to implement "mixed mode" processing.

Some common "manual mode" modifications are presented in {ref}`Pipeline re-processing considerations <sec-pipescriptreprocess>` below. A complete list of the variables for each pipeline task is given in the API sections of this site.

This documentation describes key aspects of the pipeline tasks. Important changes to other CASA tasks are documented in the Release Notes for the corresponding CASA release, available from the CASA page <https://casa.nrao.edu>.
