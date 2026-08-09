# Imaging weights in cubes

Since CASA 5.6, the calculation of imaging weights for cubes can be performed either per-channel or for all channels, according to the `tclean`
<!--:py:func:`tclean <tclean>`-->
parameter `perchanweightdensity`. This can have significant effects on the image produced. Users should be aware of these effects when creating new images, either using pipeline tasks or with `tclean`. For a detailed description, see https://casadocs.readthedocs.io/en/stable/notebooks/synthesis_imaging.html.

## History of weighting parameter choices

* The `tclean` `perchanweightdensity` parameter was effectively False in CASA 5.4, the Cycle 6 pipeline, and all prior versions of CASA and pipeline (the parameter did not exist prior to CASA 5.5.0).
* As of CASA 5.6.0 (i.e. the version used for ALMA Cycle 7 data reduction), `perchanweightdensity=True` is the default in `tclean`.
* ALMA decided that the Cycle 7 and 2020.1 Imaging Pipelines would create cubes with `perchanweightdensity=False` (consistent with all previous versions of the imaging PL).
* For PL2021, PLWG developed the new `briggsbwtaper` weighting to be used with `perchanweightdensity=True`
* `briggsbwtaper` is only applicable to cube imaging, and `briggs` remains the default weighting scheme for mfs imaging.

| Pipeline version | weighting default | perchanweightdensity default |
| :--- | :--- | :--- |
| CASA<5.6 | natural | effectively False |
| C6 pipeline | briggs | effectively False |
| CASA≥5.6 | natural | True |
| C7 Pipeline <br> PL2020 | briggs | False |
| ≥PL2021 | briggsbwtaper | True |

##  Summary of the effects of weighting scheme choices

Different channels can span multiple cells in uv-space because of the frequency difference. This is the basis of multi-frequency-synthesis (mfs) continuum imaging, which takes advantage of this property to increase the *effective* uv-coverage. In CASA 5.5 onward, the `perchanweightdensity` parameter determines whether the imaging weights are calculated using only the (u,v) points for each channel of interest (`perchanweightdensity=True`), or using the points corresponding to all channels in the spw (`perchanweightdensity=False`) similar to an mfs continuum image.

* `perchanweightdensity=False` results in a systematic variation of the beam size across a spectral window, generally larger in the center, smaller on the edges.
* In general, cubes produced with `perchanweightdensity=False` will have higher noise on the edges than center of the spectral window, even after all channels are convolved to the same beam (as is standard for the Pipeline)
* In general, `perchanweightdensity=True` with `briggs` weighting results in a smaller dynamic range in uv density, and thus changing `briggs robust` will have less effect - one will find that all beams are larger for a given `robust` value, and the endpoint of Uniform weighting has changed to be larger than with `perchanweightdensity=False`.
* For a given `robust` value, `briggsbwtaper` weighting will recover with `perchanweightdensity=True` a similar beam to that achieved with `briggs` weighting and `perchanweightdensity=False` - i.e. the beam and noise are relatively constant across a spectral window, but reducing `robust` allows a significant reduction of the beam size.
* In addition, `briggsbwtaper` with `perchanweightdensity=True` results in a cube beam size very similar to the mfs beam size for the same `robust` value (so Pipeline continuum and line images will have similar beams).
