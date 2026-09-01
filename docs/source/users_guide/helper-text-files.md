(sec-helperfiledescription)=
# Description of Pipeline "Helper" Text Files

As mentioned in {ref}`Pipeline "Helper" text files <sec-helperfileintro>`, both the IF and SD pipeline use a number of text files that are read by various pipeline tasks (as indicated by comments `##` in the example {ref}`Single Dish <fig-sdcasapipescript>` and {ref}`IF <fig-if-casapipescript>` `casa_pipescript.py` figures), and which affect the pipeline results (e.g. by applying manually identified flags or by updating calibrator fluxes or antenna positions before calculating the calibration tables). These files are particularly useful for users to over-ride the default pipeline behavior when re-running the pipeline at home, as described in the following section. Below we describe all of the currently available control files, identifying whether they are used by the IF pipeline, SD pipeline, or both in the subsection heading.

## `flux.csv` (IF Pipeline)

From Cycle 4 onward, the fluxes of standard ALMA quasar calibrators at the observed frequencies for each spw are written into the ASDM, using extrapolated values calculated from entries in the ALMA Source Catalog available at the time of observation. These fluxes are sometimes updated subsequently (thereby bracketing the observation in time), allowing for more accurate interpolated fluxes to be used for the absolute flux calibration.

Since the pipeline is usually run days to weeks after an observation is completed, better flux densities are often available at that time, so the pipeline {func}`hifa_importdata <pipeline.hifa.cli.hifa_importdata>` task does the following:

1. If `dbservice=True` (the default for production pipeline runs), an online observatory database service is queried and the best flux densities for the time and frequency of the observation are interpolated, overriding values in the ASDM.
2. If the `flux.csv` text file exists in the working directory, any values therein, for example as retrieved by `analysisUtils::getALMAFluxcsv()`, will in turn override results from the online database.
3. If no flux density is available in ASDM, dbservice, or `flux.csv`, a flux of 1Jy will be assumed.
4. After evaluating this sequence of preferred sources, the flux densities for each source and spw are written into the `flux.csv` text file. Note that even if all values are taken from `flux.csv`, they will be written back to `flux.csv`, so the file's modification date will be updated.
5. The new flux value of the flux calibrator (the source with intent=AMPLITUDE) is then used in the subsequent {func}`hif_setmodels <pipeline.hif.cli.hif_setmodels>` task. Values for the other calibrator intents (BANDPASS, PHASE, CHECK) are also updated, but these values are only shown for comparison against the values derived from the pipeline calibration (both are shown in a table in the {func}`hifa_gfluxscale <pipeline.hifa.cli.hifa_gfluxscale>` stage of the WebLog).

The format of the `flux.csv` file is shown in the example below. It contains one row for every spw of every calibrator (intents of AMPLITUDE, BANDPASS, PHASE or CHECK) in every ASDM in the MOUS. This file can be edited by users and the pipeline re-run in order to scale the fluxes of each ASDM to a different value for the AMPLITUDE calibrator. Changing the values of other calibrators will not have an effect on the calibration.

(fig-fluxcsvfile)=
**Example of a `flux.csv` file used by the interferometric pipeline (one per MOUS)**

```csv
ms,field,spw,I,Q,U,V,spix,uvmin,uvmax,comment
uid___A002_Xca8fbf_X5733.ms,0,23,1.7632620185868495,0.0,0.0,0.0,-0.285,0.0,0.0,"# field=J1517-2422 intents=A..
uid___A002_Xca8fbf_X5733.ms,0,25,1.7450149079637087,0.0,0.0,0.0,-0.285,0.0,0.0,"# field=J1517-2422 intents=A...
uid___A002_Xca8fbf_X5733.ms,0,27,1.7448343973502576,0.0,0.0,0.0,-0.285,0.0,0.0,"# field=J1517-2422 intents=A...
uid___A002_Xca8fbf_X5733.ms,0,29,1.7482019091989398,0.0,0.0,0.0,-0.285,0.0,0.0,"# field=J1517-2422 intents=A...
uid___A002_Xca8fbf_X5733.ms,0,31,1.7474672794635093,0.0,0.0,0.0,-0.285,0.0,0.0,"# field=J1517-2422 intents=A...
uid___A002_Xca8fbf_X5733.ms,0,33,1.766271050283792,0.0,0.0,0.0,-0.285,0.0,0.0,"# field=J1517-2422 intents=AM...
uid___A002_Xca8fbf_X5733.ms,0,35,1.7656450126668404,0.0,0.0,0.0,-0.285,0.0,0.0,"# field=J1517-2422 intents=A...
uid___A002_Xca8fbf_X5733.ms,0,37,1.7648329718913716,0.0,0.0,0.0,-0.285,0.0,0.0,"# field=J1517-2422 intents=A...
uid___A002_Xca8fbf_X5733.ms,1,25,0.16623488895935037,0.0,0.0,0.0,-0.468,0.0,0.0,"# field=J1532-1319 intents=...
uid___A002_Xca8fbf_X5733.ms,1,27,0.1662065981594399,0.0,0.0,0.0,-0.468,0.0,0.0,"# field=J1532-1319 intents=A...
uid___A002_Xca8fbf_X5733.ms,1,29,0.16673468749683268,0.0,0.0,0.0,-0.468,0.0,0.0,"# field=J1532-1319 intents=...
uid___A002_Xca8fbf_X5733.ms,1,31,0.16661942767873175,0.0,0.0,0.0,-0.468,0.0,0.0,"# field=J1532-1319 intents=...
uid___A002_Xca8fbf_X5733.ms,1,33,0.16957947525989395,0.0,0.0,0.0,-0.468,0.0,0.0,"# field=J1532-1319 intents=...
uid___A002_Xca8fbf_X5733.ms,1,35,0.16948059703943796,0.0,0.0,0.0,-0.468,0.0,0.0,"# field=J1532-1319 intents=...
uid___A002_Xca8fbf_X5733.ms,1,37,0.16935237463260322,0.0,0.0,0.0,-0.468,0.0,0.0,"# field=J1532-1319 intents=...
uid___A002_Xca8fbf_X5733.ms,1,23,0.16910442689668115,0.0,0.0,0.0,-0.468,0.0,0.0,"# field=J1532-1319 intents=...
```

The original `flux.csv` file written by the pipeline upon the initial run of the {func}`hifa_importdata <pipeline.hifa.cli.hifa_importdata>` task, starts out with "origin=Source.xml" as part of the comment on all lines. Lines updated with the online database will have "origin=DB".

## `jyperk.csv` or `jyperk_query.csv` (SD pipeline)

ALMA single-dish observations do not include observations of absolute amplitude calibrators. Instead, the observatory conducts regular observations of standard single-dish calibrators and stores them in an observatory database.
In the {func}`hsd_k2jycal <pipeline.hsd.cli.hsd_k2jycal>` stage, the CASA task {func}`CASA/gencal <casatasks.calibration.gencal>` retrieves the best value of these "Kelvin to Jansky" calibration factors, based on the observing date, frequency, Tsys, and source elevation from the observatory database. The appropriate values are written into the `jyperk_query.csv` text file that is read and applied.

The format of the `jyperk_query.csv` file is shown in the example below. It contains one row for every spw in every ASDM in the MOUS. This file can be edited by users and the pipeline re-run in order to scale the fluxes of each ASDM to a different value.

(fig-jyperkfile)=
**Example of a `jyperk_query.csv` file used by the single-dish pipeline (one per MOUS)**

```csv
MS,Antenna,Spwid,Polarization,Factor
uid___A002_X85c183_X36f.ms,DA61,17,I,51.890035198
uid___A002_X85c183_X36f.ms,PM03,17,I,51.890035198
uid___A002_X85c183_X36f.ms,PM04,17,I,51.890035198
uid___A002_X85c183_X60b.ms,DA61,17,I,51.890035198
uid___A002_X85c183_X60b.ms,PM03,17,I,51.890035198
uid___A002_X85c183_X60b.ms,PM04,17,I,51.890035198
uid___A002_X8602fa_X2ab.ms,PM02,17,I,51.4634859397
uid___A002_X8602fa_X2ab.ms,PM03,17,I,51.4634859397
uid___A002_X8602fa_X2ab.ms,PM04,17,I,51.4634859397
uid___A002_X8602fa_X577.ms,PM02,17,I,51.4634859397
uid___A002_X8602fa_X577.ms,PM03,17,I,51.4634859397
uid___A002_X8602fa_X577.ms,PM04,17,I,51.4634859397
uid___A002_X864236_X2d4.ms,PM03,17,I,49.437094842
uid___A002_X864236_X2d4.ms,PM04,17,I,49.437094842
uid___A002_X864236_X693.ms,PM03,17,I,49.437094842
uid___A002_X864236_X693.ms,PM04,17,I,49.437094842
uid___A002_X864236_X693.ms,DV10,17,I,49.437094842
uid___A002_X86fcfa_X664.ms,PM03,17,I,54.5385894402
uid___A002_X86fcfa_X664.ms,PM04,17,I,54.5385894402
uid___A002_X86fcfa_X664.ms,DV10,17,I,54.5385894402
uid___A002_X86fcfa_X96c.ms,PM03,17,I,54.5385894402
uid___A002_X86fcfa_X96c.ms,PM04,17,I,54.5385894402
...
```

## `uid*antennapos.json` or `antennapos.csv` (IF pipeline)

The position of every antenna in an interferometric observation must be known in order to properly transfer the calibration from the phase calibrator to the science targets. If these positions have errors, it will lead to phase errors in the imaging of the science target (increasing with telescope position error and separation between the phase calibrator and science target).

The antenna positions are calculated by special observatory observations taken outside of PI science observing, and the positions stored in an observatory database. This database is queried at the time of an SB execution, and the appropriate antenna positions are written into the ASDM. These positions are sometimes updated subsequently, especially if the observation happened shortly after an array reconfiguration or if an array element was recently moved.

Since the pipeline is usually run days to weeks after an observation, the {func}`hifa_antpos <pipeline.hifa.cli.hifa_antpos>` task will query the online database to get the best-available antenna positions at the time the pipeline is run. These are written into `uid*antennapos.json` text files, which is then read in by the {func}`CASA/gencal <casatasks.calibration.gencal>` task and used to correct the values in the ASDM.

The format of the `uid*antennapos.json` file is shown in the example below. It contains a dictionary entry for every antenna in an EB with the total position of that antenna. Though a user need not supply such a file, as {func}`hifa_antpos <pipeline.hifa.cli.hifa_antpos>` will automatically query the service for it, if these files are present in the directory where the pipeline is run a priori, the existing files will be used in lieu of querying the online database.

(fig-jsonantennaposfile)=
**Example of a `uid*antennapos.json` file used by the interferometric pipeline (one per EB)**

File lists the total positions for each antenna, which are converted into corrections to be applied to the values written into the MS by the {func}`CASA/gaincal <casatasks.calibration.gaincal>` task.

```json
{
    "data": {
        "CM05": [2225063.5461666198,-5440128.205155838,-2481550.079322571],
        "CM04": [2225074.067549907,-5440115.249648992,-2481568.944019133],
        "CM03": [2225076.734462043,-5440122.932430074,-2481549.8243493875],
        "CM02": [2225070.957887418,-5440127.671403772,-2481544.6552856914],
        "CM01": [2225080.354745021,-5440132.956785359,-2481524.789613484],
        "CM12": [2225089.438089277,-5440119.773602419,-2481545.39917787],
        "CM11": [2225065.4337890167,-5440120.433856066,-2481565.3136376073],
        "CM10": [2225078.9290363584,-5440126.085189326,-2481541.0211708946],
        "CM08": [2225063.5325220255,-5440134.134238726,-2481537.201932615],
        "CM07": [2225090.9997122493,-5440126.601164151,-2481529.1336664273],
        "CM06": [2225084.2403706782,-5440114.998424933,-2481560.411721414]
    },
    "metadata": {
        "caltype": "ALMA antenna positions",
        "description": "ALMA ITRF antenna positions in meters",
        "product_code": "antposalma",
        "outfile": "uid___A002_Xe1f219_X9dbf.antennapos.json",
        "hosts": [
            "https://asa.alma.cl/uncertainties-service/uncertainties/versions/last/measurements/casa/"
        ],
        "asdm": "uid://A002/Xe1f219/X9dbf",
        "search": "auto",
        "successful_url": "https://asa.alma.cl/uncertainties-service/uncertainties"
                "/versions/last/measurements/casa//?asdm=uid%3A%2F%2FA002%2FXe1f219%2FX9dbf&search=auto",
        "timestamp": "2025-08-25 18:22:13.785714"
    }
}
```

Alternatively, for datasets originally processed through the 2024 pipeline or earlier, a `antennapos.csv` file may be present in the `*auxproducts.tgz` from the original run. If this file exists in the directory where the pipeline is run, and the {func}`hifa_antpos <pipeline.hifa.cli.hifa_antpos>` task parameters are set to `hm_antpos='file'` and `antposfile='antennapos.csv'`, the corrections it contains will be used in-lieu of the online database.

The format of the `antennapos.csv` file is shown in the example below. It contains one row for every antenna in every ASDM in the MOUS. This file can be edited by users and the pipeline re-run in order to correct antenna position errors.

(fig-antennaposfile)=
**Example of a `antennapos.csv` file used by the interferometric pipeline (one per MOUS)**

The offset units are in meters. Corrections that are comparable, or larger than the observing wavelength are consequential.

```csv
name,antenna,xoff,yoff,zoff,comment
uid___A002_Xca8fbf_X5733.ms,DA41,-5.29597e-06,-1.16080e-05,-1.60051e-04,
uid___A002_Xca8fbf_X5733.ms,DA42,-8.69576e-06,-2.61175e-04,-8.79318e-05,
uid___A002_Xca8fbf_X5733.ms,DA43,-9.54466e-06,-1.70737e-04,-1.47686e-04,
uid___A002_Xca8fbf_X5733.ms,DA44,1.88754e-04,-2.52803e-04,-7.59289e-05,
uid___A002_Xca8fbf_X5733.ms,DA46,-2.86531e-04,-4.77569e-04,-4.69737e-04,
uid___A002_Xca8fbf_X5733.ms,DA47,-2.63745e-05,-2.20798e-04,-3.75155e-04,
uid___A002_Xca8fbf_X5733.ms,DA49,-3.67966e-05,-3.40138e-05,-1.81810e-04,
uid___A002_Xca8fbf_X5733.ms,DA50,4.44967e-05,-6.21555e-05,-3.29943e-04,
uid___A002_Xca8fbf_X5733.ms,DA51,-7.00033e-05,-1.77003e-04,-2.09113e-04,
uid___A002_Xca8fbf_X5733.ms,DA52,-7.74823e-05,-1.45007e-05,-1.21235e-04,
uid___A002_Xca8fbf_X5733.ms,DA53,1.95067e-04,-4.52641e-04,-5.08577e-05,
uid___A002_Xca8fbf_X5733.ms,DA54,-1.47680e-04,2.42910e-04,1.14313e-04,
uid___A002_Xca8fbf_X5733.ms,DA55,-1.62264e-04,2.22735e-05,-3.31404e-04,
uid___A002_Xca8fbf_X5733.ms,DA58,2.10611e-04,-3.27433e-04,-7.80367e-05,
uid___A002_Xca8fbf_X5733.ms,DA59,4.70094e-05,-5.74067e-05,-1.44642e-04,
uid___A002_Xca8fbf_X5733.ms,DA60,1.71910e-04,4.06828e-04,-4.65860e-04,
uid___A002_Xca8fbf_X5733.ms,DA62,-8.71466e-05,7.18571e-05,-1.87562e-04,
uid___A002_Xca8fbf_X5733.ms,DA64,-6.97952e-05,-9.69870e-05,-1.40777e-04,
uid___A002_Xca8fbf_X5733.ms,DA65,-1.25389e-05,-7.79228e-05,-1.55111e-04,
uid___A002_Xca8fbf_X5733.ms,DV01,4.04226e-04,-6.00860e-04,-2.94583e-04,
uid___A002_Xca8fbf_X5733.ms,DV02,3.10277e-04,-2.40413e-04,-3.90951e-04,
...
```

## `uid*flagtemplate.txt` & `uid*flagtsystemplate.txt` (both pipelines)

The extensive pipeline flagging heuristics may sometimes prove inadequate, and users may wish to add additional flagging commands to exclude these data from the calibration. These manually-identified flags can be introduced to any Pipeline reduction by editing the `uid*flagtemplate.txt` files that are provided with the archived pipeline products and rerunning the pipeline calibration steps. There should be one file for every MS that needs additional flagging, with a name matching the MS uid. The flag commands can be any valid CASA {func}`CASA/flagdata <casatasks.flagging.flagdata>` command. For interferometric data, use the `<AntID>` syntax to flag only cross-correlation data for `<AntID>`, while for single dish data use the "`<AntID>&&*`" syntax to flag both cross- and auto-correlation data for `<AntID>`, and the "`<AntID>&&&`" syntax to flag auto-correlation data for `<AntID>`. Examples of the syntax to use in editing these files are given at the top of the files `uid*flagtemplate.txt` (see the example below).

These flag files will be picked up by the {func}`hifa_flagdata <pipeline.hifa.cli.hifa_flagdata>`/{func}`hsd_flagdata <pipeline.hsd.cli.hsd_flagdata>` tasks which are run before the calibration tasks, therefore excluding the manually identified data from being used to generate the calibration tables.

Since the Tsys spectra are calculated from a different ASDM subtable, any commands that the user desires to flag the Tsys spectral windows have to be applied differently by the pipeline, and so have to be put into the separate `*.flagtsystemplate.txt` file. The flagging syntax is the same, only that those commands should refer to Tsys spectral windows in particular.

(fig-flagtemplatefile)=
**Example of a `uid*flagtemplate.txt` file used by both the interferometric and single-dish pipeline (one per ASDM)**

```python
#
# User flagging commands file for the calibration pipeline
#
# Examples
# Note: Do not put spaces inside the reason string !
#
# mode='manual' antenna='DV02;DV03&DA51' spw='22,24:150~175' reason='QA2:applycal_amplitude_frequency'
# 
# mode='manual' spw='22' field='1' timerange='2018/02/10/00:01:01.0959~2018/02/10/00:01:01.0961' reason='QA2:t...
# 
# TP flagging: The 'other' option is intended for bad TP pointing
# mode='manual' antenna='PM01&&PM01' reason='QA2:other_bad_pointing' 
#
# Tsys flagging: 
# mode='manual' antenna='DV02;DV03&DA51' spw='22,24' reason='QA2:tsysflag_tsys_frequency'
mode='manual' spw='25:230.513~230.525GHz,33:220.380~220.386GHz' field='J0542-0913' reason='QA2:applycal_amp...
```

## `uid*flagtargetstemplate.txt` (IF imaging pipeline)

Users should examine the science data (e.g. using the CASA task {func}`CASA/plotms <casaplotms.plotms>`, or examining the MS using the CASA viewer). If bad data are found, flagging commands can be added to the `uid*flagtargetstemplate.txt` files that are provided with the archived pipeline products to exclude these data from subsequent imaging. There should be one file for every MS that needs additional flagging, with a name matching the MS uid. As for the `uid*flagtemplate.txt` files, the flag commands can be any valid CASA {func}`CASA/flagdata <casatasks.flagging.flagdata>` command. If these files are found in the directory where the pipeline is run, they will be picked up by the {func}`hifa_flagtargets <pipeline.hifa.cli.hifa_flagtargets>` task and applied to the data before science target imaging.

```{admonition} Deprecation Warning
:class: warning

{func}`hifa_flagtargets <pipeline.hifa.cli.hifa_flagtargets>` is rarely used in operations and may be removed from the standard recipe, although it is expected to remain a supported pipeline task.
```

(sec-cont-dat)=
## `cont.dat` (IF imaging pipeline)

The pipeline-identified continuum frequency ranges, in LSRK units, for each spectral window of each source are entered into a file called `cont.dat` that is delivered with the pipeline products. This file lists the LSRK frequency ranges that were used to make the per-spw and aggregate continuum images, and for fitting and subtracting the continuum for the image cubes. When this file is in the directory where the pipeline is (re)run, the pipeline will use these entries directly instead of using its own heuristics (via the {func}`hif_findcont <pipeline.hif.cli.hif_findcont>` task) to determine them. Therefore, a user can edit this file (or create their own) in order to use a different continuum range. Alternatively, a user-defined file name can be passed as an argument to the {func}`hif_makeimlist <pipeline.hif.cli.hif_makeimlist>` task.

*The format of `cont.dat` changed between PL2023 and PL2024. PL2024 and later can read the earlier format, but not vice versa.*

An example `cont.dat` file is shown below.

(fig-contdatfile)=
**Example of a `cont.dat` file used by the interferometric pipeline (one per MOUS)**

This example is for an MOUS that has 4 spectral windows; the entry for spw 19 is empty and spw 27 is omitted, which will result in the {func}`hif_findcont <pipeline.hif.cli.hif_findcont>` task determining the frequency ranges for these spectral windows.

```text
Field: hh666

SpectralWindow: 19 X1913589666#ALMA_RB_06#BB_2#SW-01#FULL_RES

SpectralWindow: 25 X1913589666#ALMA_RB_06#BB_1#SW-01#FULL_RES
Flags: ALLCONT
219.3452433728~219.8069245935GHz LSRK

SpectralWindow: 29 X1913589666#ALMA_RB_06#BB_4#SW-01#FULL_RES
230.0866113521~230.0958888260GHz LSRK
230.1017482832~230.1100491809GHz LSRK
230.2062419366~230.4933553394GHz LSRK
230.5939426880~231.0177767588GHz LSRK
```

The behavior of {func}`hif_findcont <pipeline.hif.cli.hif_findcont>` and the subsequent continuum subtraction and continuum and line imaging commands is as follows:

1. If the SpectralWindow line in `cont.dat` is followed by one or more frequency ranges, {func}`hif_findcont <pipeline.hif.cli.hif_findcont>` will not run its heuristics on the spw. The task {func}`hif_uvcontsub <pipeline.hif.cli.hif_uvcontsub>` will use these frequency ranges to fit and subtract the continuum from this spw. Subsequent continuum images will include only these frequency ranges for this spw, and the spw line cubes will be made from the continuum subtracted data.
2. If the SpectralWindow line exists, but is not followed by any ranges, {func}`hif_findcont <pipeline.hif.cli.hif_findcont>` will not run its heuristics on the spw (if the delivered `cont.dat` file contains spw entries without ranges, this indicates that the {func}`hif_findcont <pipeline.hif.cli.hif_findcont>` task failed to find any continuum frequency ranges). The task {func}`hif_uvcontsub <pipeline.hif.cli.hif_uvcontsub>` will currently assume this is an all continuum case and fit using all channels. This is supposed to be changed in future pipeline versions to skip fitting and writing the spw to the line cube. Subsequent continuum images will include the full frequency range for this spw (logging a message in the WebLog), and the spw line cubes will have had a continuum subtraction performed using all channels which may offset any line emission. Cube imaging "FC" moment map computation will fail due to the missing continuum ranges.
3. If a spw is missing from `cont.dat` when {func}`hif_findcont <pipeline.hif.cli.hif_findcont>` is run, then it will try to find the frequency ranges, and these will be used to make subsequent continuum images, and for continuum subtraction.
