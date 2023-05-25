
## Testing Prrocedures

* Examples of SRDP Json files for creating custom recipes
  * `test_hifa_cubeimage.json` # uid___A001_X1467_X256
  * `test_hifv_contimage.json`

* SRDP-like procedures:
    no data restorations; cube imaging created from `hif_makeimlist` rather than `hif_editimlist`
  * `test_procedure_hifa_cubeimage_selfcal.xml`
  * `test_procedure_hifv_contimage_selfcal.xml`

* Testing procedures for only testing the `hif_selfcal` task
  * `test_procedure_hifv_selfcal_only.xml`
  * `test_procedure_hifa_selfcal_only.xml`

* A standard "calimage" workflow with `hif_selfcal` stage

  * `test_procedure_hifa_calimage_selfcal.xml`
