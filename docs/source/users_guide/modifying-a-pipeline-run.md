# Modifying a Pipeline Run using `casa_pipescript.py`

(sec-pipescriptreprocess)=

## Pipeline re-processing considerations

As a rule, it does not make sense to rerun the `casa_pipescript.py` exactly as delivered, since this will merely reproduce the calibrated MeasurementSet (which for IF Pipeline calibrated data is much more easily generated using `scriptForPI.py` or `casa_piperestorescript.py` to "restore" the calibration, as described in {ref}`Archived scripts <sec-allscripts>` above) and/or already-delivered products. Instead, it is likely that the user may want to redo the calibration after some modifications or produce modified imaging products. This section describes a few of the more common calibration and imaging changes for both the IF and SD Pipeline tasks. See the task API pages for more complete details on the pipeline tasks and their inputs.

Re-running the pipeline can be very resource-intensive, both from a compute-time and disk-space perspective. For the compute time, an idea of how long the pipeline took when can be inferred from the WebLog (using the **Execution Duration** shown on the top of the "Home" page of the WebLog — see {ref}`the WebLog Home Page example <fig-homepage>` for an example, or the **Task Execution Statistics** that are listed for each task in the "By Task" part of the WebLog — see e.g. {ref}`the By Task summary view <fig-bytaskpage>`. Those times, however, reflect the run times using the ALMA Operations processing clusters, which have ≳ 256 GB RAM, and likely use parallel processing (multi-core) for imaging. Concerning disk space, to re-run SD or IF pipeline calibration, it is advisable to have a system with at least 8 GB RAM, and 50 – 75 GB free disk space per ASDM. To re-run the IF imaging pipeline, it is advisable to have a system with ≥64 GB RAM, and the available disk space needs to be 10 – 100 times the expected size of the final imaging products.

The above resource requirements for the IF imaging pipeline are rather daunting. However, in practice, it is unlikely that the imaging pipeline commands would need to be rerun in their entirety. It would be much quicker and demand much less computing resources to only image the sources and or spectral windows (spw) or channels of interest, at an appropriate spectral resolution, and often a reduced spectral range. This can be done by finding the corresponding {func}`CASA/tclean <casatasks.imaging.tclean>` command in the provided `casa_commands.log` file, modifying it as desired, and running it in CASA. These commands work on the MeasurementSet created by the pipeline {func}`hif_mstransform <pipeline.hif.cli.hif_mstransform>` command, so that part of the imaging script would need to be run first.

Please contact ALMA via the [ALMA Helpdesk](https://help.almascience.org/) if assistance is needed with data reprocessing.

## Preparing to run `casa_pipescript.py`

The following steps describe how to modify and re-run the Pipeline, starting from the archived products and directory structure created after downloading the data:

- Create **rawdata/**, **working/**, and **products/** subdirectories
- Copy `uid*casa_pipescript.py` to `working/casa_pipescript.py`.

To re-run IF calibration:
- copy `flux.csv`, `antennapos.csv` or `antennapos.json` (if present), and `uid*flagtemplate.txt` to the **working/** directory (there will be one flagtemplate.py file per EB). Depending on the delivery method, `flux.csv` and `*antennapos*` are likely to be found in `uid*auxproducts.tgz` which will need to be unzipped. If using the older `antennapos.csv`, the hifa_antpos() call should set `hm_antpos`='file' and `antposfile='antennapos.csv'`. If json antenna positions are present, hifa_antpos() needs no input parameters set.

To re-run IF imaging also:
- Copy `uid*flagtargetstemplate.txt` to the **working/** directory (note there is one per ASDM).
- Copy `cont.dat` (there will only be one per MOUS) to the **working/** directory.

To re-run SD calibration & imaging:
- copy `jyperk.csv` or `jyperk_query.csv` and `uid*flagtemplate.txt` to the **working/** directory (there will be one file per ASDM).

In the **rawdata/** directory:
- Make sure the naming of the raw ALMA data is consistent with those provided in the script (e.g. if the data ends in `asdm.sdm` then move to names which do not have this suffix).

In the **working/** directory:
- Modify the pipeline "helper" files as desired (e.g. editing the `*flagtemplate.txt` file to add any additional flags — see {ref}`Description of Pipeline Helper Text Files <sec-helperfiledescription>` for other options).
- Edit `casa_pipescript.py` to only include the pipeline steps you wish to repeat (e.g. commenting out the {func}`hif_findcont <pipeline.hif.cli.hif_findcont>` or imaging steps, which are very computationally expensive).
- Start the version of CASA containing Pipeline using `casa --pipeline`
- You are now ready to run the script by typing `execfile('casa_pipescript.py')`. Alternatively, you can sequentially execute individual commands from `casa_pipescript.py`, stopping at any point to run other CASA commands ({func}`CASA/plotms <casaplotms.plotms>`, etc).

**Note that to re-run the Pipeline multiple times, it is recommended to start each time from a clean working directory containing only CASA "helper" text files and the `casa_pipescript.py` script.**

## Modifying Calibration Commands

The pipeline calibration commands can be modified to produce different results.

For instance, problematic datasets (ASDMs) can be excluded from the processing by editing the `vis=` and `session=` lists in {func}`hifa_importdata <pipeline.hifa.cli.hifa_importdata>` or {func}`hsd_importdata <pipeline.hsd.cli.hsd_importdata>` tasks in the `casa_pipescript.py` script.

As a second example, a user-specified prioritized reference antenna list can be specified via the `refant` parameter in calibration tasks, over-riding the pipeline reference antenna heuristics, by passing the desired refant list. E.g. `hifa_bandpass(refant='DV06,DV07')`

See the task API pages for more options.

Another use case is to keep the default pipeline commands, but to change the values in the Pipeline "helper" text files to e.g. change the flux scaling, or update antenna positions (see {ref}`Description of Pipeline Helper Text Files <sec-helperfiledescription>` for details). The new values will be used when the relevant `hif_` commands are run.

## Modifying IF Pipeline Imaging Commands

The pipeline imaging commands can be modified to produce different products. Typical reasons for re-imaging include:

- Imaging improvements to be gained from interactively editing an emission specific clean mask and cleaning more deeply. The pipeline generates a clean mask automatically (see the {func}`hif_makeimages <pipeline.hif.cli.hif_makeimages>` (general) task description for specifics).
Cases with moderate to strong emission (or absorption) can benefit from deeper clean with additional interactive clean masking, with the most affected property being the integrated flux density.
- Non-optimal continuum ranges. The pipeline uses heuristics that attempt to identify continuum channels over a very broad range of science target line properties. Particularly for strong line forests (hot-cores) and occasionally for TDM continuum projects the pipeline ranges can be non-optimal — too much in the first case and too little in the second.

Other science goal driven reprocessing needs may include:
- Desire to use wide image channels in imaging to increase the signal-to-noise ratio (SNR) of cubes.
- Desire to use a different Briggs `robust` image weighting than the default value of `robust`=0.5 (smaller value = smaller beam, poorer SNR; larger value = larger beam, better SNR).
- Desire to uv-taper images to increase the SNR for extended emission.
- Desire to use different continuum frequency ranges than determined by the pipeline, by modifying the `cont.dat` file ({ref}`cont.dat <sec-cont-dat>`).

Some re-imaging examples are given in a "CASA Guide" at
<https://casaguides.nrao.edu/index.php/ALMA_Imaging_Pipeline_Reprocessing>.
There you will find examples of the following:
- Making aggregate continuum image with all channels of all spectral windows.
- Redoing continuum subtractions with user-derived continuum ranges.
- Making a cube of subset of sources, spectral windows, with a different `robust` weight and channel binning factor.

## Manual imaging after running `casa_pipescript.py`

### SD Data

After calibration with the script `casa_pipescript.py`, it is possible to re-image using the CASA Single Dish task, {func}`CASA/tsdimaging <casatasks.single.tsdimaging>`, with user-defined parameters. As mentioned earlier, the Single Dish Pipeline creates a calibrated MS with a filename extension of `*.ms.atmcor.atmtype1_bl` for each ASDM. The {func}`CASA/tsdimaging <casatasks.single.tsdimaging>` command will make images of all MS that are specified in the `infiles` parameter. For other parameters in {func}`CASA/tsdimaging <casatasks.single.tsdimaging>`, refer to the `*casa_commands.log` file.

Note that the images included in the delivery package have the native frequency resolution, and the cell size of one-ninth of the beam size, as recommended in the SD "CASA Guide" <https://casaguides.nrao.edu/index.php/M100_Band3_SingleDish>. If you want to change the frequency resolution and cell size, we recommend that you import the delivered FITS data cubes into CASA and regrid them using the CASA task {func}`CASA/imregrid <casatasks.analysis.imregrid>`.

It is also possible to revise the baseline subtraction using your preferred mask range instead of the pipeline-defined range. We recommend doing this on the images using the CASA tasks {func}`CASA/imcontsub <casatasks.analysis.imcontsub>` or {func}`CASA/sdbaseline <casatasks.single.sdbaseline>` during your own manual calibration (refer to the CASA Guides).

### IF Data

For IF data that are pipeline calibrated but *manually* imaged, the imaging commands will be included in a separate `scriptForImaging.py` script, containing all the CASA commands used to create the delivered products. In order to use this imaging script, after using `casa_pipescript.py` to recalibrate, the science spectral windows must first be "split" out from the calibrated MeasurementSets and the MeasurementSets output with a `*.split.cal` suffix. Perform the split in CASA with a command like this:

```
split('uid__A002_X89252c_X852.ms', outputvis='uid__A002_X89252c_X852.ms.split.cal', spw='17,19,21,23')
```

The science spectral windows are specified in the Pipeline WebLog (Home > Observation Summary > MeasurementSet Name > Spectral Setup, in the ID column) or can be determined using the CASA task {func}`CASA/listobs <casatasks.information.listobs>`, e.g.

```
listobs('uid___A002_X89252_X852.ms')
```

where the results will be reported in the CASA logger.

If the pipeline-calibrated data is restored using `scriptForPI.py`, that script can, with the appropriate parameters set, perform the split command for the user.

If a script named `scriptForFluxCalibration.py` is present in the **script/** directory, this must also be executed prior to running `scriptForImaging.py`. `scriptForPI.py` will run this script if it is present.

## The Pipeline Context

It is recommended to always run the Pipeline using python scripts. New Pipeline runs/scripts need to be initialized using {func}`h_init <pipeline.h.cli.h_init>` in order to create an empty pipeline **Context** object.

If the script is modified to only run a subset of the pipeline tasks, the **Context** should be saved after the last task by using {func}`h_save <pipeline.h.cli.h_save>`. To resume the run, use {func}`h_resume <pipeline.h.cli.h_resume>` to load the saved **Context** before executing any pipeline tasks. See detailed pages on the internal API for more information.
