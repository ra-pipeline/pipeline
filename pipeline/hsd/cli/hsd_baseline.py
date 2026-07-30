import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hsd.tasks.baseline.baseline.SDBaselineInputs.__init__
@utils.cli_wrapper
def hsd_baseline(
        fitfunc=None, fitorder=None, switchpoly=None,
        linewindow=None, linewindowmode=None, edge=None, broadline=None,
        clusteringalgorithm=None, wave_number=None,
        deviationmask=None, deviationmask_sigma_threshold=None, parallel=None,
        infiles=None, field=None, antenna=None, spw=None, pol=None
):
    """Detect spectral line features and subtract the baseline from calibrated single-dish spectra.

    Generates baseline fitting tables and subtracts the baseline from the spectra by masking
    detected emission/absorption line regions. The WebLog shows three sections of spectral grid
    maps per source:

    1. Spectra **before** baseline subtraction (red fitted curve overlaid on each grid cell).
    2. **Averaged** spectra per grid cell (improves S/N to reveal line features).
    3. Spectra **after** baseline subtraction (red line at zero level per grid cell).

    Cyan-shaded regions indicate the sum of all emission-line channels identified across the
    entire map (not just the individual grid cell). A spatially integrated spectrum per ASDM,
    antenna, spw, and polarization is shown above each grid, with the magenta curve indicating
    atmospheric transmission and thick red bars marking channels excluded by the
    ``deviation mask`` algorithm.
    Representative spectra in each cell correspond to the valid pointing nearest the mean
    coordinates of all pointings in that grid cell.

    .. figure:: /figures/hsd_baseline_representative.png
       :scale: 60%
       :alt: Representative position determination

       Examples of how representative positions are determined. Blue points are all
       pointings; brown crosses are the averaged coordinates; green circles mark the
       representative positions (nearest valid pointing to the averaged coordinates).

    .. figure:: /figures/guide-img036.jpg
       :scale: 60%
       :alt: hsd_baseline WebLog page

       Example of the :py:func:`hsd_baseline <hsd_baseline>` WebLog page showing the first three spectral
       grid rows (before subtraction, averaged, after subtraction) for one spw.

    Detailed per-antenna spectral maps can be accessed from the detail pages by clicking the
    **Spectral Window** link on each summary page. Filters by antenna, field, spectral window,
    and polarization are available in the upper part of the detail pages.

    **Fitting order determination**: The default function is a cubic spline. The number of
    spline segments (``N_segment``) is determined via FFT analysis of the power spectrum of
    grouped spectra:

    1. ``1 < P_FFT < 3`` -- ``N_segment = 4``
    2. ``3 <= P_FFT < 5`` -- ``N_segment = 5``
    3. ``5 <= P_FFT < 10`` -- ``N_segment = 6``
    4. ``P_FFT >= 10`` -- ``N_segment = F_FFT * 2 + 2``

    The final ``N_segment`` is scaled by ``(Nch - N_mask) / Nch`` to account for masked channels.
    Specifying a non-negative integer for ``fitorder`` disables auto-determination.

    **Mask range determination**: Emission/absorption channels are identified by comparing
    spectral deviation from the median against an MAD-based threshold. Up to 10 iterations
    are performed to detect weak lines; each detected range is extended while the intensity is
    monotonically decreasing/increasing. Binned spectra (widths 1, 4, 16, 64 for 4096-channel
    spws) are also analyzed for broad features, with threshold ``3.5 + sqrt(binning_width) * MAD``.

    **Baseline flatness evaluation** (fourth section of the WebLog page): Emission-free channels
    are divided into 10 or 20 bins. ``MAX(mean) - MIN(mean)`` across bins is compared to the
    spectral rms ``sigma``.

    .. figure:: /figures/guide-image-new-baselineflatness.png
       :scale: 60%
       :alt: Baseline flatness evaluation

       Example of baseline flatness evaluation.

    **Clustering analysis** for spectral line detection (developer plots, hidden by default;
    enable with ``plotlevel='all'`` in ``h_init``):

    *Detection*: grid cells with emission exceeding the threshold are identified. Yellow cells
    have a single time-domain group with detected emission; cyan cells have more than one.

    .. figure:: /figures/guide-img037.png
       :scale: 60%
       :alt: Clustering detection

       Clustering detection step.

    *Validation*: for each grid cell the ratio of spectra containing detected emission lines
    (``Nmember``) to total spectra in the cell (``Nspectra``) is computed:

    - **Validated** if ``Nmember/Nspectra > 0.5``
    - **Marginally validated** if ``Nmember/Nspectra > 0.3``
    - **Questionable** if ``Nmember/Nspectra > 0.2``

    .. figure:: /figures/guide-img038.png
       :scale: 60%
       :alt: Clustering validation

       Clustering validation step.

    *Smoothing*: the per-cell ratio is convolved with a Gaussian-like grid function to suppress
    isolated single-line candidates and reinforce detections supported by neighboring cells.

    .. figure:: /figures/guide-img039.png
       :scale: 60%
       :alt: Clustering smoothing

       Clustering smoothing step.

    *Mask region determination*: in the validated area after smoothing, mask channel ranges are
    computed over the spatial domain by inter/extrapolating the mask ranges of the averaged
    spectra in validated cells and applied to each individual spectrum.

    .. figure:: /figures/guide-img040.png
       :scale: 60%
       :alt: Mask range calculation

       Mask range calculation — in blue squares the mask
       range is interpolated from validated cells.

    .. figure:: /figures/guide-img041.png
       :scale: 60%
       :alt: Clustering final

       Clustering final example.

    Notes:
        Three QA scores are computed:

        **Spectral line detection**:

        - QA = 1.0 if no edge-line and main line is narrow.
        - QA = 0.60 if no edge-line and main line is wide.
        - QA = 0.55 if edge-line detected (regardless of main line width).
        - QA = 0.80 if no spectral lines are detected.
        - QA = 0.88 if the deviation mask overlaps with spectral or atmospheric lines.

        **Baseline flatness** (MAX(mean) - MIN(mean) vs. sigma):

        - QA = 0.33 if MAX(mean) - MIN(mean) > 3.6 sigma.
        - QA = 0.33-1.0 if 1.8 sigma <= MAX(mean) - MIN(mean) < 3.6 sigma.
        - QA = 1.0 if MAX(mean) - MIN(mean) < 1.8 sigma.

        **Deviation from zero-baseline**: QA = 0.65 if significant deviation outside candidate
        line ranges is detected (triggering deviation masks).

    Warning:
        :py:func:`hsd_baseline <hsd_baseline>` overwrites results from previous runs. If processing spws separately,
        each spw must be taken through to the imaging stage before the next spw is processed::

            hsd_baseline(spw='0'); hsd_blflag(spw='0'); hsd_imaging(spw='0')
            hsd_baseline(spw='1'); hsd_blflag(spw='1'); hsd_imaging(spw='1')

    Examples:
        1. Basic usage with automatic line detection:

        >>> hsd_baseline(antenna='PM03', spw='17,19')

        2. Use pre-defined line windows instead of automatic detection:

        >>> hsd_baseline(linewindow=[[100, 200], [1200, 1400]], linewindowmode='replace', edge=[10, 10])

        3. Per-spw pre-defined line windows merged with automatic detection:

        >>> hsd_baseline(linewindow={19: [[390, 550]], 23: [[100, 200], [1200, 1400]]},
        ...             linewindowmode='merge')

    """
