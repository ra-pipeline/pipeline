import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hif.tasks.findcont.findcont.FindContInputs.__init__
@utils.cli_wrapper
def hif_findcont(vis=None, target_list=None, hm_mosweight=None,
                 hm_perchanweightdensity=None, hm_weighting=None,
                 hm_mode=None, field=None, datacolumn=None, parallel=None):
    """Identify line-free continuum frequency ranges for each science target and spw.

    Creates dirty image cubes at native channel resolution (using ``robust=1`` for optimal line
    sensitivity) for each science target and spw. The pipeline then runs the ``findContinuum``
    function to identify channel ranges likely free of line emission via the following steps:

    1. **Joint-mask mean spectrum**: SNR-based thresholds on the moment-0 (integrated) and
       moment-8 (peak) images define a 2-D joint mask. The mask is pruned to remove islands
       smaller than ``max(4, int(beamAreaInPixels * minbeamfrac))`` pixels (``minbeamfrac=0.3``;
       0.5 for ACA 7m if all islands are pruned). The mean spectrum over the mask is computed
       and analyzed to find line-free channels.
    2. **Pre-smoothing**: A boxcar smoothing kernel is applied to the mean spectrum prior to
       analysis. For Cycle 10+ data the kernel width is derived from the
       ``spectralDynamicRangeBandwidth`` ASDM attribute. For older data it is based on the
       ``nbin`` value in the imaging target list, which is either supplied through
       ``target_list`` or constructed internally using
       :func:`~pipeline.hif.cli.hif_makeimlist` heuristics, with additional heuristics
       to skip smoothing for wide + narrow spw combinations, already-labeled continuum spws,
       and cases of strong line emission (peak SNR > 10: nbin limited to 2 for 12m, 3 for 7m).
    3. **Moment-difference contamination check**: Line-free channels are used to form ``mom8fc``
       and ``mom0fc`` images; the scaled-subtracted ``momDiff`` image peak SNR is computed.
       If ``momDiffSNR > 8`` (or > 11.5 for high-atm-variation spws), contamination is likely.
       Two remediation paths are tried: **Amend Mask** (logic code starts with ``A``) or
       **Only Extra Mask** (code starts with ``E``). Further steps include channel intersection (code ``I``),
       extra-mask, and up to two rounds of ``autoLower`` (codes ``X`` and ``Y``) iterations. The final logic path code is
       shown in the plot legend, and the momDiffSNR is shown there and in the WebLog table.
    4. **AllContinuum check**: If a single range covers >= 92.5% of the channels (>= 91% for
       spws with < 75 channels), the spw is declared ``AllContinuum`` and no cube is subsequently
       cleaned. Note that the ``AllContinuum`` assessment is performed prior to the search for (and exclusion of) large gaps in the baseline (blue) points.
       Thus, results with a single range can be narrower than this threshold and still be labelled as ``AllContinuum``.

    If a ``cont.dat`` file already exists in the working directory, spws with pre-defined ranges
    are not re-analyzed; only spws not listed are processed. The resulting ``cont.dat`` file (LSRK
    frequency ranges) is used by subsequent :func:`~pipeline.hif.cli.hif_uvcontsub` and :func:`~pipeline.hif.cli.hif_makeimages` stages.

    Using ``hm_mode='coarse'`` applies fast-imaging overrides to reduce the
    cost of the continuum-finding dirty cubes. When the target list is
    constructed internally for ALMA data, coarse mode uses 3 pixels per beam
    for 12-m data or 4 pixels per beam when 7-m data are present, applies a
    uv taper, and enforces a minimum image size of 64 pixels. In all coarse
    mode runs, weighting is set to ``'briggs'``, and per-channel weight
    density and mosaic weighting are disabled, regardless of the corresponding
    ``hm_*`` parameters. The default mode is ``hm_mode='normal'``, which
    preserves the behavior prior to PL2026.

    .. note::
       Starting from ALMA Cycle 13, standard ALMA recipes use ``hm_mode='coarse'``
       by default at the recipe workflow level.

    .. figure:: /figures/guide-img029.png
       :width: 60%
       :alt: Example findContinuum plots

       Two examples: entire spectral window identified as continuum (left) and two
       continuum ranges identified (right). Cyan horizontal lines mark the identified
       frequency ranges.

    Notes:
        QA = 1.0 if continuum frequency ranges were found for all spws; otherwise QA = fraction
        of spws for which a range was identified. QA = 0.0 if size mitigation previously failed.

    Examples:
        1. Identify continuum frequency ranges for all science targets and spws:

        >>> hif_findcont()

        2. Perform continuum frequency range detection for a specific field:

        >>> hif_findcont(field='M51')

    """
