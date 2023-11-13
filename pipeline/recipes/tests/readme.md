## Testing Procedures

* Examples of SRDP JSON files for creating custom recipes
  * `test_hifa_cubeimage.json` # uid___A001_X1467_X256
  * `test_hifv_contimage.json`

* SRDP-like procedures: no restoration / target-split / findcont for speeded-up testing; needs to be used with *_targets.ms, along with cont.dat
  * `test_procedure_hifa_image.xml` (with selfcal)
  * `test_procedure_hifv_contimage.xml` (with selfcal)

* Testing procedures for only testing the `hif_selfcal` task
  * `test_procedure_hifv_selfcal.xml`
  * `test_procedure_hifa_selfcal.xml`

## Uses of Testing Procedures

```python
import pipeline.recipereducer
pipeline.recipereducer.reduce(vis=['uid___A002_Xc46ab2_X15ae_repSPW_spw16_17_small.ms'], procedure='tests/test_hifa_calsplit.xml', loglevel='debug')
```
