import pipeline.h.cli.utils as utils


# docstring and type hints: inherits from hifa.tasks.gfluxscaleflag.gfluxscaleflag.GfluxscaleflagInputs.__init__
@utils.cli_wrapper
def hifa_gfluxscaleflag(vis=None, intent=None, phaseupsolint=None, solint=None, minsnr=None, refant=None,
                        antnegsig=None, antpossig=None, tmantint=None, tmint=None, tmbl=None, antblnegsig=None,
                        antblpossig=None, relaxed_factor=None, niter=None, parallel=None, examineCrossPolSum=None):
    """Flag outlier visibilities in the flux, diffgain, and phase calibrators and check source.

    Performs a temporary calibration using the spw mapping/combine parameters established in
    :py:func:`hifa_spwphaseup <hifa_spwphaseup>` (with ``solint`` always 'int' and ``gaintype`` always 'G' for the phase-up, and
    ``solint='inf'`` and ``gaintype='T'`` for the amplitude solutions), then identifies and flags outlier
    visibilities by statistically examining the scalar difference of calibrated amplitudes minus model
    amplitudes. Only amplitude outliers are flagged; the phase of the data is not assessed.

    The heuristics differ slightly between multi-scan calibrators (typically the phase calibrator and
    sometimes the check source) and single-scan calibrators.

    The workflow is:

    1. Snapshot the current flagging state.
    2. Solve and apply preliminary phase and amplitude calibration.
    3. Run flagging heuristics; identify outlier visibilities.
    4. Restore the flagging state from the snapshot.
    5. Apply any newly identified flags.

    The WebLog shows amplitude vs. uv-distance and amplitude vs. time plots before flagging and (if any
    flags were found) after flagging.

    Notes:
        For each intent, the QA sub-score = 1 - (fraction of data newly flagged). The final stage QA score
        is the product of all per-intent sub-scores. For example, if AMPLITUDE has 10% newly flagged and
        PHASE has 40% newly flagged, the total score is (1 - 0.1) x (1 - 0.4) = 0.54.

    Returns:
        The results object for the pipeline task is returned.

    Examples:
        1. Run with recommended settings to create flux scale calibration with flagging using recommended
        thresholds:

        >>> hifa_gfluxscaleflag()

    """
