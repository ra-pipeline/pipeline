import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hsd.tasks.imaging.imaging.SDImagingInputs.__init__
@utils.cli_wrapper
def hsd_imaging(mode=None, restfreq=None, infiles=None, field=None, spw=None):
    """Generate single-dish images per antenna and combined over all antennas.

    Creates images per antenna and combined images for each field and spw. Image parameters
    (cell size, number of pixels, etc.) are determined automatically from metadata (antenna
    diameter, map extent, etc.). Images are produced in LSRK frame, or REST frame for ephemeris
    sources.

    The WebLog for this stage includes:

    - **Image sensitivity table**: achieved sensitivity per spw/source and theoretical sensitivity accounting
      for the flagging fraction.
    - **Profile maps**: three types are shown in the WebLog — a simplified combined-image
      map per spw (front page), a simplified per-antenna map (click ``Spectral Window``), and
      a detailed map (one spectrum per pixel at 3-cell intervals, max 5x5 plots/page). Each
      spectrum in the simplified maps corresponds to the average over 1/8 of the image size,
      giving 8x8 spectra by default. Magenta lines show atmospheric transmission.

    .. figure:: /figures/guide-img043.png
       :width: 60%
       :alt: Example profile map

       Example of the profile map.

    - **Channel maps**: one map per identified emission line per spw, showing a velocity-axis
      zoom of the line, the full spectral range with line width marked (red vertical lines), total
      integrated intensity map (Jy/beam km/s), and channel maps within the identified line
      velocity range (15 bins by default).

    .. figure:: /figures/guide-img044.png
       :width: 60%
       :alt: Example channel map

       Example of a channel map.

    - **Baseline RMS map**: constructed from the baseline RMS in the baseline tables
      (emission-free channels); combined data only, not per antenna.
    - **Moment maps**: for each spw, three maps are generated: (1) maximum intensity map
      (moment-8) over all channels; (2) total intensity map (moment-0) over line-free channels;
      (3) maximum intensity map using line-free channels only.

    - **Diagnostic plots for possible missed line channels** (PL2025+): generated when line
      emission is detected outside the line ranges from
      :func:`~pipeline.hsd.cli.hsd_baseline` (SNR threshold = 7 for "single peak" and
      SNR threshold = 5 for "extended"). The cyan ranges and magenta lines indicate the detected line ranges at :func:`~pipeline.hsd.cli.hsd_baseline` and the deviation mask, respectively. 
      The channels exceeding the thresholds are highlighted with the red points. If there is no missed line emission, these plots will not appear in WebLog. Details are described in Appendix of this page.

    .. figure:: /figures/missedlines.png
       :width: 60%
       :alt: Diagnostic plot for possible missed line channels

       Example diagnostic plot for possible missed line channels.

    - **Contamination plots**: Peak S/N map, mask map (pixels with S/N < 10% of peak), and
      masked-averaged spectrum (red = masked-pixel average, grey = peak S/N position spectrum, light purple = edge or atmospheric line channels which are ignored).
      A warning is issued if the negative peak < -4 x standard deviation.
      
      .. figure:: /figures/contamination.png
       :width: 60%
       :alt: Contamination plot.

    Notes:
        Four QA scores are computed:

        - **Masking**: QA = 1.0 if no pixels in the pointing area are masked; QA = 0.5 if any
          pixels are masked; QA = 0.0 if >= 10% of pixels in the pointing area are masked
          (linearly interpolated between 0 and 0.5).
        - **Contamination**: QA = 0.65 if possible astronomical line contamination is detected
          in the continuum channel selection.
        - **Missed line channels**: QA = 0.60 if significant off-line-range emission
          is detected; QA = 1.0 otherwise.
        - **Comparison of observed and theoretical sensitivities**: QA = 1.0 if observed sensitivity agrees with theoretical senstiivity (0.9 < observed sensitivity/theoretical sensitivity < 1.6); QA = 0.5 if observed sensitivity deviates from theoretical sensitivity.

    Examples:
        1. Generate images with default settings:

        >>> hsd_imaging()

        2. Generate images for the amplitude calibrator with specific parameters:

        >>> hsd_imaging(mode='ampcal', field='*Sgr*,M100', spw='17,19')
        
        
       Appendix:
       There are two diagnostics methods: ``single peak'' analysis and ``extended'' analysis, which work per spw and per source at the imaging level, that is, on the image cube derived from combined-MS data.
       
       For the ``single peak'' analysis, the spatial location of the maximum value in the data cube is determined, and denoted as $(x_p,y_p)$. 
       The ``single peak'' spectrum is calculated by multiplying a weighted cube (``cube $\times$ weight'') by a beam pattern centered at $(x_p,y_p)$ and integrated along the spatial axes of the cube. 
       The noise level of this spectrum is determined by $\sigma=1.4826\times$ the median absolute deviation of the values outside the line ranges and masked regions. The heuristic detects possible missing line emission if the ``single peak'' spectrum is over the threshold of $7\sigma$.
       
       In the ``extended'' analysis, a cube mask with the same shape as the image cube is created with a value of zero or one depending on whether or not the value in the image cube is larger than ``Observed RMS'' $\times7$, respectively. 
       This mask is extended by convolving it at each channel with the beam and resetting it to one if the convolved mask is $> 0.5$; otherwise, it stays at 0. 
       This convolved cube mask is multiplied by the image cube, and the ``extended'' spectra is obtained by integrating in the spatial direction. 
       The noise levels of the ``extended'' spectra are determined by $\sigma=1.4826\times$ the median absolute deviation of the values outside the line ranges and masked regions. 
       The heuristic detects possible missing line emission if the ``extended'' spectrum is over the threshold of $5 \sigma$.
       For both the ``extended'' and ``single peak'' analysis, spectral features whose FWHM is narrower than 3 pixels are ignored.
       
        

    """
