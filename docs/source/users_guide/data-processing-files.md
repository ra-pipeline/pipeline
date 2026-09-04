# Data Processing Files

## Archived scripts

(sec-allscripts)=
There are several scripts that are archived with ALMA data deliveries. These are described in the document **ALMA QA2 Data Products** (sometimes cycle-specific) available from the `ALMA Science Portal <https://almascience.nrao.edu/processing/science-pipeline>`_ under the "Processing" tab. The particular scripts for a specific dataset should also be described in the QA2 report archived with the data products. This report will vary based on how the data were processed (pipeline calibrated & imaged; pipeline calibrated & manually imaged; manually calibrated & pipeline imaged, manually calibrated & manually imaged).

The scripts produced by the pipeline are archived with the data and have file names like:
`member.<mous_uid>.<recipe>.casa_pipescript.py` and `member.<mous_uid>.<recipe>.casa_piperestorescript.py`.

The former includes all pipeline processing commands that were run on the data, and is more fully described below. The latter "restores" the data, which means that rather than re-running the pipeline calibration commands, it uses previously derived calibration and flagging tables and applies them directly to the raw data, producing a calibrated MeasurementSet. This is much quicker and requires less computing resources than re-running the pipeline calibration commands. However, expert users should be aware that if the latter, faster method is used, then the state of the MeasurementSets are not exactly the same as in a complete run (e.g. the model of the calibrators will not be set).

Every delivery package also includes a master script with a file name like `member.<mous_uid>.scriptForPI.py`, that will reproduce the calibrated data regardless of how it was processed (manual or pipeline). This script is not created by the pipeline, but instead by the data packaging software so that it is produced for both pipeline and manually reduced data. For pipeline calibrated data, it will simply invoke the pipeline-produced `casa_piperestorescript.py` or `casa_pipescript.py` scripts mentioned above.

**Using `scriptForPI.py` is the recommended and easiest method of obtaining calibrated ALMA data from the delivery.**
However, one can also run the pipeline `casa_piperestorescript.py` using the steps in {ref}`The Pipeline script to restore calibrated MSs <sec-piperestorescript>`. To *change* the calibration results, one would re-run the commands in `casa_pipescript.py` after making modifications, as described in {ref}`Pipeline re-processing considerations <sec-pipescriptreprocess>`.

## Pipeline "Helper" text files

(sec-helperfileintro)=
Both the IF and SD pipeline use a number of text files that, if present, will affect the pipeline results (e.g. by applying manually identified flags or by updating calibrator fluxes or antenna positions before calculating the calibration tables). These files are particularly useful for users to over-ride the default pipeline behavior when re-running the pipeline at home, as more fully described in {ref}`Pipeline re-processing considerations <sec-pipescriptreprocess>` below. They include the following:

- `flux.csv`: This file is used by the IF pipeline to update the flux of calibrators. The flux of the calibrator with the "AMPLITUDE" intent will affect the overall flux scale of the data. If this file is not present where the pipeline is run and {func}`hifa_importdata <pipeline.hifa.cli.hifa_importdata>` parameter `dbservice` is True, the pipeline will attempt to contact the ALMA source catalog (at the URL specified by the environment variable `FLUX_SERVICE_URL`) for previously recorded flux densities, and if that doesn't succeed, the fluxes in the ASDM(s) will be used, representing the best flux estimate at the time the SB was executed. If no flux value appears in either the flux.csv file or the ASDM, a flux of 1.0 Jy is adopted.
- `jyperk.csv` or `jyperk_query.csv`: These files are used by the SD pipeline to update the "Kelvin to Jansky" calibration factors which set the overall flux scale of the data. The SD pipeline will use a file specified by {func}`hsd_k2jycal <pipeline.hsd.cli.hsd_k2jycal>` parameter `reffile`. If they are not present where the pipeline is run and the pipeline database query parameter (`dbservice`) is True, conversion factors are obtained via the database. If they are not present and `dbservice` is False, conversion factors of unity are assumed.
- `uid*antennapos.json` or `antennapos.csv`: uid*antennapos.json files are used by the IF pipeline to update the positions of the antenna elements. The pipeline will, by default, query an online database to retrieve these files, but if already present in the working directory then the existing files will be used instead (e.g. if one were to want to manually control the antenna position corrections). Alternatively, an antennapos.csv file can be supplied in conjunction with hm_antpos='file' to provide antenna position corrections.
- `uid*flagtemplate.txt`: This file is used to add additional CASA flagging commands that will be applied to the data before the calibration tables are calculated.
- `uid*flagtsystemplate.txt`: This file is used to add additional CASA flagging commands that will be applied to the Tsys spws before the calibration tables are calculated.
- `uid*flagtargetstemplate.txt`: This file is used to add additional CASA flagging commands that will be applied to the data after the calibration tables are calculated, but before science target imaging is performed.
- `cont.dat`: This file is used to specify the continuum frequency ranges used for constructing the continuum images and creating the continuum-subtracted cubes. This particular file is described in more detail below {ref}`cont.dat (IF imaging pipeline) <sec-cont-dat>` and in the reimaging casaguide <https://casaguides.nrao.edu/index.php/ALMA_Imaging_Pipeline_Reprocessing>.

The format of each of these files is given in {ref}`Description of Pipeline Helper Text Files <sec-helperfiledescription>`.

## The Pipeline script to restore calibrated MSs: `casa_piperestorescript.py`

(sec-piperestorescript)=
To restore data calibrated by the pipeline, one can either run `scriptForPI.py` as described in **ALMA QA2 Data Products** document available from ALMA Science Portal under the "Processing" tab (or directly at <https://almascience.org/processing>), or one can run the pipeline-provided `casa_piperestorescript.py` script:

- Create **rawdata/**, **working/**, and **products/** subdirectories.
- Download the raw ASDMs from the archive and put them in **rawdata**/. Make sure the naming of the raw ALMA data is consistent with those provided in the script (e.g. if the data ends in .**asdm.sdm** then rename to not have this suffix).
- Copy or move `*manifest.xml, *caltables.tgz, *flagversions.tgz, *auxproducts.tgz` and `*calapply.txt` to **products/.**
- Copy `uid*casa_piperetorescript.py` to `working/casa_piperestorescript.py`.
- In **working/,** start `casa --pipeline`, and `execfile("casa_piperestorescript.py")`.

### Results from running the SD `casa_piperestorescript.py`

- A calibrated MS for each ASDM with a name like `uid___A002_Xe50c9e_X1297.ms`.

Running the script through {func}`hsd_atmcor <pipeline.hsd.cli.hsd_atmcor>` command will additionally create:
- A calibrated, atmospheric-corrected MS for each ASDM with a name like

  `uid___A002_Xe50c9e_X1297.ms.atmcor.atmtype1`.

  The pipeline "automatic" mode reproduces correction for atmospheric effects.

Note that the *baseline subtraction is not done for the restored calibrated MS*. Running the script through {func}`hsd_atmcor <pipeline.hsd.cli.hsd_atmcor>` and {func}`hsd_baseline <pipeline.hsd.cli.hsd_baseline>` commands will additionally create:
- A calibrated, atmospheric-corrected, baseline-subtracted MS for each ASDM with a name like

  `uid___A002_Xe50c9e_X1297.ms.atmcor.atmtype1_bl`.

  The pipeline "automatic" mode reproduces the baseline subtraction. If instead the user may want to set the mask ranges to be used for baseline subtraction, CASA task {func}`CASA/sdbaseline <casatasks.single.sdbaseline>` is recommended. In this case, please be aware that a WebLog is not generated for CASA tasks. If the baseline subtraction is done with the CASA task {func}`CASA/sdbaseline <casatasks.single.sdbaseline>`, any further Pipeline tasks cannot be used.

Running the script additionally through {func}`hsd_blflag <pipeline.hsd.cli.hsd_blflag>` command will result in:
- flagging based on the baseline rms for each ASDM. The {func}`hsd_blflag <pipeline.hsd.cli.hsd_blflag>` command has to be run after {func}`hsd_baseline <pipeline.hsd.cli.hsd_baseline>` at least once. In the standard recipe, {func}`hsd_baseline <pipeline.hsd.cli.hsd_baseline>` and {func}`hsd_blflag <pipeline.hsd.cli.hsd_blflag>` are repeated twice to improve the quality of baseline detection.

Running the script through the {func}`hsd_imaging <pipeline.hsd.cli.hsd_imaging>` command will additionally create:
- native resolution images per spectral window, antenna, and source.

### Results from running the IF `casapiperestorescript.py`

- A calibrated MS for each ASDM with a name like `uid___A002_Xe50c9e_X1297.ms`, containing all sources including calibrators, with calibrated data in the CORRECTED column.

It is often desirable to subsequently run the first few steps of the imaging pipeline, to recover uv-subtracted target visibilities. Detailed instructions are found here
<https://casaguides.nrao.edu/index.php/ALMA_Imaging_Pipeline_Reprocessing>. In brief:

1. navigate to the **calibrated/working** directory
2. copy `cont.dat` ({ref}`cont.dat <sec-cont-dat>`) into that directory - it is likely to be found inside **calibration/\*auxproducts.tgz**
3. if you still have casa running from having just run `scriptForPI.py` or `casa_piperestorescript.py`, then you have an active Pipeline session, and new pipeline task calls will use the active **Context** — for example, the MSs are already known in that **Context**.
4. if not, you will have to start `casa --pipeline`, and run {func}`h_init <pipeline.h.cli.h_init>` and then {func}`hifa_importdata <pipeline.hifa.cli.hifa_importdata>` with the list of recently-restored, calibrated MSs, to start a new pipeline session.
5. run {func}`hif_mstransform <pipeline.hif.cli.hif_mstransform>` to create `*_targets.ms`, with calibrated continuum+line target data in the DATA column.
6. next, run {func}`hif_makeimlist <pipeline.hif.cli.hif_makeimlist>`(specmode="mfs");
{func}`hif_findcont <pipeline.hif.cli.hif_findcont>`(). It should use your existing `cont.dat` and not have to recalculate anything.
7. finally, run {func}`hif_uvcontsub <pipeline.hif.cli.hif_uvcontsub>`(). Now your `*.targets_line.ms` will have continuum-subtracted line visibilities in the DATA column.

## The Pipeline processing script: `casa_pipescript.py`

(sec-pipescriptintro)=

### Format of `casa_pipescript.py`

The complete set of pipeline commands are given in the script `casa_pipescript.py`. This is a python script that includes all tasks and parameter values, in the correct sequence, that were used for the pipeline run. A typical `casa_pipescript.py` script for a SD Pipeline run (including both calibration + imaging steps) is shown below, while a typical IF pipeline script including both pipeline calibration and imaging steps follows it.

For data that were both calibrated and imaged in the pipeline (including all SD data run through the pipeline), the `casa_pipescript.py` file will include both the calibration and imaging pipeline commands. For IF data that were calibrated in the pipeline but imaged outside of the pipeline, the `casa_pipescript.py` file will only include the IF calibration pipeline commands (up to the line "# Start of pipeline imaging commands"), and the archived data will include a separate `scriptForImaging.py` script containing the manual (CASA) imaging commands. If instead the IF data were manually calibrated and pipeline imaged, there will be a separate `scriptForCalibration.py` script (one for each EB) in the archived data, containing the manual (CASA) calibration commands, and the IF pipeline imaging commands (those following the line "# Start of pipeline imaging commands" in the example below) would be included in a separate `scriptForImaging.py` script.

(fig-sdcasapipescript)=
**Example of the Single Dish Pipeline calibration + imaging script `casa_pipescript.py`**

The "#" comment line identifies the pipeline command that uses one of the pipeline "helper" text files described in {ref}`Description of Pipeline Helper Text Files <sec-helperfiledescription>`.

```python
context = h_init()
context.set_state('ProjectStructure', 'recipe_name', 'hsd_calimage')
try:
    hsd_importdata(vis=['uid___A002_X85c183_X36f'], session=['default'])
    hsd_flagdata() # uses *flagtemplate.txt
    h_tsyscal()
    hsd_tsysflag()
    hsd_skycal()
    hsd_k2jycal()  # uses jyperk.csv
    hsd_applycal()
    hsd_atmcor()
    hsd_baseline()
    hsd_blflag()
    hsd_baseline()
    hsd_blflag()
    hsd_imaging()
    hsd_exportdata()
finally:
    h_save()
```

(fig-if-casapipescript)=
**Example of an non-polarization IF Pipeline `casa_pipescript.py` script**

```python
context = h_init()
context.set_state('ProjectStructure', 'recipe_name', 'hifa_calimage')
try:
    hifa_importdata(vis=['uid___A002_Xc46ab2_X15ae'], session=['session_1'], dbservice=True) # use flux.csv
    hifa_flagdata() # uses *flagtemplate.txt
    hifa_fluxcalflag()
    hif_rawflagchans()
    hif_refant()
    h_tsyscal()
    hifa_tsysflag()
    hifa_tsysflagcontamination()
    hifa_antpos() 
    hifa_wvrgcalflag()
    hif_lowgainflag()
    hif_setmodels()
    hifa_bandpassflag()
    hifa_bandpass()
    hifa_spwphaseup()
    hifa_gfluxscaleflag()
    hifa_gfluxscale()
    hifa_timegaincal()
    hifa_renorm(createcaltable=True, atm_auto_exclude=True)
    hifa_targetflag()
    hif_applycal()
    hif_makeimlist(intent='PHASE,BANDPASS,AMPLITUDE')
    hif_makeimages()
    hif_makeimlist(intent='CHECK', per_eb=True)
    hif_makeimages()
    hifa_imageprecheck()
    hif_checkproductsize(maxcubesize=40.0, maxcubelimit=60.0, maxproductsize=500.0)
    hifa_exportdata()
    hif_mstransform()
    hifa_flagtargets() # uses *flagtargettemplate.txt
    hif_makeimlist(specmode='mfs') # uses cont.dat
    hif_findcont() # modifies cont.dat
    hif_uvcontsub()
    hif_makeimages() # uses cont.dat
    hif_makeimlist(specmode='cont') # uses cont.dat
    hif_makeimages() # uses cont.dat
    hif_makeimlist(specmode='repBW')
    hif_makeimages()
    hif_selfcal() # uses cont.dat
    hif_makeimlist(specmode='mfs', datatype='selfcal') # uses cont.dat
    hif_makeimages() # uses cont.dat
    hif_makeimlist(specmode='cont', datatype='selfcal') # uses cont.dat
    hif_makeimages() # uses cont.dat
    hif_makeimlist(specmode='cube', datatype='best')
    hif_makeimages()
    hif_makeimlist(specmode='repBW', datatype='selfcal')
    hif_makeimages()
finally:
    h_save()
```

The tasks names, order, and parameter values in the `casa_pipescript.py` script reflect the processing recipe used for each individual delivery. Most tasks are run with default parameters; to see what task parameters are available, type `?<task_name>` at the CASA command line or consult the API pages here for more details, and {ref}`Pipeline re-processing considerations <sec-pipescriptreprocess>` below for examples of modified pipeline re-runs.

### Results from running the single dish `casa_pipescript.py`

Running the script will create:
- A calibrated, atomospheric-corrected MS for each ASDM with a name like

  `uid___A00X_XXXX_XXX.ms.atmcor.atmtype1`
- A calibrated, atomospheric-corrected, baseline-subtracted MS for each ASDM with a name like

  `uid___A00X_XXXX_XXX.ms.atmcor.atmtype1_bl`
- Baseline subtracted image cubes of the the science targets in `*.image` format (1 per spectral window, all antennas combined, at the native correlator frequency spacing).
- A `pipeline-*/html` directory containing
  - The Pipeline WebLog ({ref}`The Pipeline WebLog <sec-weblog>`).
  - The `casa_commands.log` file (see {ref}`CASA equivalent commands file <sec-casacommandslog>`)

### Results from running the interferometric `casa_pipescript.py`

Running the script through the first {func}`hif_makeimages <pipeline.hif.cli.hif_makeimages>` command (calibrator imaging) will create:
- A calibrated MS for each ASDM with a name like `uid___A00X_XXXX_XXX.ms`. This ms includes both calibrator and science data and all spectral windows, with the raw data in the DATA column, and the calibrated continuum + line data in the CORRECTED column.
- Continuum images of the bandpass, phase, and (if present) check source calibrators (1 per spectral window for the bandpass and phase and 1 per spectral window per EB for the check source, in `*.image` format). To view a `*.image` file e.g. use [casaviewer](https://casadocs.readthedocs.io/en/stable/api/casaviewer.html) `image_file_name`.
- A `pipeline-*/html` directory containing:
  - The Pipeline WebLog ({ref}`The Pipeline WebLog <sec-weblog>`).
  - The `casa_commands.log` file (see {ref}`CASA equivalent commands file <sec-casacommandslog>`)

```{admonition} Deprecation Warning
:class: warning

CASA support for the standalone viewer is not expected to continue indefinitely (it is already gone for MacOS), and users are encouraged to switch to the CARTA viewer <http://cartavis.org> for CASA images.
```

Running the script through the {func}`hif_mstransform <pipeline.hif.cli.hif_mstransform>` command will additionally create:
- A calibrated MS for each ASDM containing only science target data (only science targets and spectral windows), with a name like `uid___A00X_XXXX_XXX_targets.ms`. This ms will have the calibrated continuum + line data in the DATA column.

Running the script through {func}`hif_uvcontsub <pipeline.hif.cli.hif_uvcontsub>` command will result in:
- The science-target only MS `uid___A00X_XXXX_XXX_targets_line.ms`, with the calibrated continuum-subtracted line data in the DATA column.

Running the script through the final {func}`hif_makeimages <pipeline.hif.cli.hif_makeimages>` command (science target spectral line imaging) will additionally create:
- Per-spw continuum images, aggregate continuum images, and continuum subtracted image cubes of at least some science targets (the number of targets may be reduced automatically — see the mitigation section of {func}`hif_checkproductsize <pipeline.hif.cli.hif_checkproductsize>`).

## CASA equivalent commands file: `casa_commands.log`

(sec-casacommandslog)=
The `casa_commands.log` file is written by the pipeline to provide a list of the equivalent CASA task commands (as opposed to Pipeline tasks) used by the Pipeline to process a dataset. While this log cannot be used to create a CASA reduction script that is identical to the Pipeline processing, it does provide the executable CASA commands with the parameter settings used by the pipeline. The log is commented to indicate which Pipeline stage the tasks were called from and why. The imaging commands given in this file can be easily modified to produce new imaging products with more finely tuned inputs (e.g. interactive masks and deeper cleaning thresholds).
