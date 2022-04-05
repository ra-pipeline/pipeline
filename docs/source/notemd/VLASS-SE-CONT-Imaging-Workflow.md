VLASS-SE-CONT imaging workflow
------------------------------

This document describes the implementation of the workflow presented in VLASS Memo 15 as a 
CASA script ("VIP script") to the pipeline codebase. The relevant recipe is found in the pipeline repository at `pipeline/recipes/procedure_vlassSEIP.xml`.

The major peculiarities in the workflow are: 
1) special masking procedure based on the pyBDSF blob finding algorithm,
2) widefield projection (awproject gridder) is used by default, additional step is required to compute PSFs without frequency dependent A-terms, 
3) self calibration is used,
4) imaging stages depend on the result of previous imaging stages (self-calibration and masking).

Furthermore, astropy is a hard requirement for pyBDSF (the package documentation say otherwise, but in practice it was found to be necessary) and is included in the tarball builds. The hif_vlassmasking() task and hifv_selfcal() task weblog renderer also take advantage of astropy.

### Imaging modes

The pipeline supports 3 VLASS-SE-CONT imaging modes (parameter used in hif_editimlist task). The modes differ in gridder related tclean parameters. 

- VLASS-SE-CONT: default imaging mode, short for VLASS-SE-CONT-AWP-P032.
- VLASS-SE-CONT-AWP-P032: applies widefield projection algorithms with 32 projection planes (i.e. tclean parameters `gridder='awproject'`, `wprojplanes=32`). This is a direct implements of the VLASS Memo 15 imaging workflow and script. Requires two sets of CFcaches; one with frequency dependent A-terms, one without. 
- VLASS-SE-CONT-AWP-P001: alternative widefield projection mode. It differs from the default mode by using one projection plane (i.e. `wprojplanes=1`), in order to speed up imaging.
- VLASS-SE-CONT-MOSAIC: mosaic gridder based mode`gridder='mosaic'`, similar to the Quick Look Imaging Project (QLIP) recipe. 

### Task level workflow

The Memo 15 workflow consists of 3 imaging steps: 1) compute image (with Tier-1 mask, derived from QL database) that is 
used for self-calibration, 2) image self calibrated (corrected) data column and use the result for creating the Tier-2 mask, and 3) 
compute the final image using self-calibrated (corrected) data column, Tier-1 mask and combined Tier-1 and Tier-2 masks.

The pipeline parameters are controlled via a parameter file, which is interpreted by the `hif_editimlist` task. An example: 

    # SEIP_parameter.list
    #
    # Necessary parameters:
    #    
    imagename='VLASS1.2.se.Txxxx.J133335+164400.v1'
    phasecenter='J2000 13:33:35.814 +16.44.04.255'
    imaging_mode='VLASS-SE-CONT'
    # Important: first with frequency dependent A-terms, second without 
    cfcache='/mnt/scratch/cfcache/cfcache_spw2-17_smaller_imsize1024_cell2.0arcsec_w32_conjT.cf, /mnt/scratch/cfcache/cfcache_spw2-17_smaller_imsize1024_cell2.0arcsec_w32_conjT_psf_wbawp_False.cf'
    #
    # Parameters for speeding up computation
    #
    imsize=[1024, 1024]
    cell=['2.0arcsec']
    niter=50

The strictly necessary parameters are `imaging_mode`, `imagename`, `phasecenter` and `cfcache`. Cfcaches must be computed with exactly the same imsize and cell size as used for imaging. Reducing the image size, resolution and iteration number speeds up computation and used during testing, but it is not expected to produce science ready data quality. The other parameters (if not set in parameter file) are determined by heuristics.

Note: the CFCaches should not be used from network storage drives (e.g. lustre) because it may lead slow 
and blocked file access. To circumvent the issue, CFCaches are provided from local disk storage on the NMPOST
cluster (`/mnt/scratch/cfcache/`). Cfcaches copied to `/lustre/aoc/projects/vlass/cfcache` are periodically synced to the local partitions.

The imaging cycle (stages) include a `hif_editimlist`, an optional `hifv_vlassmasking` and a `hif_makeimages` task call:

    # First imaging step
    hif_editimlist(parameter_file='SEIP_parameter.list')
    hifv_vlassmasking(maskingmode='vlass-se-tier-1')
    hif_makeimages( hm_masking='manual')

    # Self calibration steps

    # Second imaging cycle (after self-cal)
    hif_editimlist(parameter_file='SEIP_parameter.list')
    hif_makeimages( hm_masking='manual')

    # Final imaging step
    hif_editimlist(parameter_file='SEIP_parameter.list')
    hifv_vlassmasking(maskingmode='vlass-se-tier-2')
    hif_makeimages( hm_masking='manual')

##### hif_editimlist()

The `context.clean_list_pending` list is filled with a single imaging target (`imlist_entry`). The following changes occur compared to the 
normal task operation:

1. `"sSTAGENUMBER"` string is prepended to imagename parameter value, this will be replaced by stage numbers

2. `vlass_stage` attribute of the heuristics object (ImageParamsHeuristicsVlassSeCont) is counted by method `utils.get_task_result_count()`. This counts and returns the MakeImagesResult instances in `context.result` list. The imaging heuristics return values are determined by `vlass_stage` attribute together with the `iteration` number (method argument).
    
3. `imlist_entry['cfcache_nowb']` key is added in addition to the normal `imlist_entry['cfcache']` key. The heuristics method `get_cfcaches()` is used to parse the string provided in the parameter file to these two keys. Modes other than VLASS-CONT-SE(-AWP-0??) and VLASS-CONT-SE-MOSAIC always set`cfcache_nowb=None`.

4. `user_cycleniter_final_image_nomask` attribute of the heuristics object (ImageParamsHeuristicsVlassSeCont) is set according to the parameter file key `cycleniter_final_image_nomask`. The value is not None, then it is used instead of the default cycleniter value in the third imaging stage last clean interation (cleaning with pb mask only, i.e. without user mask). No other cycleniter values are affected. If cycleniter is set explicitly, then it is used in all tclean calls, except the above mentioned final one. The value set for `user_cycleniter_final_image_nomask` is stored in the heuristics class attribute (ImageParamsHeuristicsVlassSeCont.user_cycleniter_final_image_nomask).

5. `clean_no_mask_selfcal_image` if True, then perform a final clean iteration (iter2) in the first imaging stage with pb mask only (without user mask).

6. prepare `imlist_entry['mask']` string or list to be used in hifv_vlassmasking and hif_makeimages. 
    - First imaging step: 'mask' is either empty string or 'pb' (if `clean_no_mask_selfcal_image=True`). This is updated by hifv_vlassmasking(maskingmode='vlass-se-tier-1) with the appropriate Tier-1 mask name by replacing the empty string, or creating a 2 element list with 'pb' at the last place.
    - Second imaging step: the Tier-1 mask name is obtained from the hifv_vlassmasking result object (context.results) and set as the 'mask' value.
    - Third imaging step: the Tier-1 mask name is obtained from the hifv_vlassmasking result object and a two element list is created with 'pb' at the last place. This is updated by hifv_vlassmasking(maskingmode='vlass-se-tier-2) by inserting the name of the Tier-2 mask to the middle of the list, forming a 3 element list.

##### hifv_vlassmasking()

The task requires the `vlass_ql_database` parameter. If it is not defined, then the default 
`/home/vlass/packages/VLASS1Q.fits` is used (can be found on NMPOST machines). 

The details of how the constructed mask is added to `context.clean_list_pending['mask']` depends on the imaging mode and 
whether cleaning without mask (i.e. pbmask only) is used:

1. `maskingmode='vlass-se-tier-1'` and no cleaning without mask is requested, then `context.clean_list_pending['mask']` 
   is overwritten by the new mask name.
2. `maskingmode='vlass-se-tier-1'` and cleaning without mask is requested, then `context.clean_list_pending['mask']` 
   is a list with new mask name in first position and `'pb'` string in second (last) position.
3. `maskingmode='vlass-se-tier-2'`, no cleaning without mask is requested and `context.clean_list_pending['mask']` 
   is `''`, then key value is overwritten with new mask name. (Not used.)
4. `maskingmode='vlass-se-tier-2'`, cleaning without mask is requested (`context.clean_list_pending['mask']` 
   is `'pb'`), then list is returned with new mask in first place followed by `'pb'`. (Not used.)
5. `maskingmode='vlass-se-tier-2'`  and `context.clean_list_pending['mask']` is a list, then insert new mask name to 
   the second position. (this applies also when cleaning without mask is requested).

Note that the `context.clean_list_pending['mask']` key is a string in imaging stages 2 (`vlass_stage=2`, Tier-1 mask), list in stage 3 
(`vlass_stage=3`, first element is Tier-1 mask, second element is the combined Tier-1 and Tier-2 mask, third element is `'pb'`), and either string 
or list in imaging stage 1 (`vlass_stage=1`), depending on the `clean_no_mask_selfcal_image` `hif_editimlist` parameter. 
If `clean_no_mask_selfcal_image=True` then the `'mask'` key value is a list in imaging stage 1: first element is the Tier-1 mask, second element is `'pb'`.

##### hif_makeimages()

The following changes are implemented for the VLASS-SE-CONT mode:

 - New Tclean._do_iterative_vlass_se_imaging() method implements the VLASS-SE-CONT imaging sequence in awproject and mosaic
modes. This method is invoked only if image_heuristics.imaging_mode starts with the 'VLASS-SE-CONT' string. The sequence incorporates the following steps:
   
1. `vlass_stage=1`, using datacolumn='data'
    - (awproject only) compute PSF without frequency dependent A-terms, i.e. `cfcache=cfcache_noawbp` and `wbawp=False` tclean parameters
    - `iter0`: initialize clean using normal CFCache (`niter=0`, `calcpsf=True`, `calcres=True`)
    - (awproject only) replace `iter0` PSF with non-frequency dependent A-terms PSF
    - `iter1`: continue, clean with Tier-1 mask
    - `iter2`: (optional) clean with pbmask only
    - save model to `modelcolumn`, always in single threaded mode
    
2. `vlass_stage=2`, using datacolumn='corrected'
    - (awproject only) compute PSF without frequency dependent A-terms, i.e. `cfcache=cfcache_noawbp` and `wbawp=False` tclean parameters
    - `iter0`: initialize clean using normal CFCache (`niter=0`, `calcpsf=True`, `calcres=True`)
    - (awproject only) replace `iter0` PSF with non-frequency dependent A-terms PSF
    - `iter1`: continue, clean with Tier-1 mask

3. `vlass_stage=3`, using datacolumn='corrected'
    - (awproject only) compute PSF without frequency dependent A-terms, i.e. `cfcache=cfcache_noawbp` and `wbawp=False` tclean parameters
    - `iter0`: initialize clean using normal CFCache (`niter=0`, `calcpsf=True`, `calcres=True`)
    - (awproject only) replace `iter0` PSF with non-frequency dependent A-terms PSF
    - `iter1`: continue, clean with Tier-1 mask
    - `iter2`: continue, clean with combined Tier-1 and Tier-2 mask
    - `iter3`: clean with pbmask only
    
Steps including `iter1` and after is implemented as an iteration over the mask list (1 to 3 element). The mask list is constructed in hif_editimlist and hifv_vlassmasking tasks.

The imaging sequence is implemented as `_do_iterative_vlass_se_imaging` method and fullfils the same function as `_do_iterative_imaging` method, that is used for any other imaging mode then 'VLASS-SE-CONT'. The separate method was needed due to the PSF handling (needed for awproject gridder) and single threaded column saving requirements.

The Tclean result object is changed to store information contained in the tclean return dictionary. This include: number of minor cycle in per major cycle, total flux cleaned in per major cycle, peak residual in per major cycle, and total number of major cycles done.


### CASA 6.1 specific workaround

This section lists CASA issues that the pipeline needs to work around as of the release of 2021.1.1 (based on the CASA 6.1 series). With future CASA version these issues are expected to be fixed.

1. CAS-13338: Tclean phasecenter parameter conversion has limited precision (in parallel mode)
   - ImageParamsHeuristicsVlassSeCont.get_parallel_cont_synthesis_imager_csys() heuristic method (see docstring) works around this issue
   
2. CAS-13071: Write model column to MeasurementSet always in serial mode, due to potential performance issues (see also PIPE-1107 and VLASS Memo 15). 